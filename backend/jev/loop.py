"""El loop por bloque (Sección VI) con regla de deadline, escalera de
fallback (Tabla V) y log de triples para calibración.

    on_block:  fills del bloque → estado → snapshot válido → batería →
               compose → precios A-S → riesgo → post-only → log

Escalera:
    sano + alta confianza      operación normal
    sano + baja confianza      reduce tamaño (QUOTE_WIDE)
    tarde (pasado el deadline) HOLD: no se repostea sobre estado viejo
    modelo no disponible       solo juicios del fallback determinístico
    límite duro                KILL: aplanar, alertar, parar
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from .battery import RulesJudge
from .calibration import summarize
from .policy import Action, PricingParams, Thresholds, compose, price_quotes
from .risk import Limits, RiskEngine
from .state import BlockEvent, PortfolioView, StateEngine, approx_tokens
from .venue import Fill, PaperVenue, VenueCosts


@dataclass
class LoopConfig:
    tick: float
    base_size: float
    limits: Limits
    costs: VenueCosts = field(default_factory=VenueCosts)
    pricing: PricingParams = field(default_factory=PricingParams)
    thresholds: Thresholds = field(default_factory=Thresholds)
    policy_mode: str = "gated"          # gated | argmax | always
    block_s: float = 0.3
    deadline_ms: float = 250.0
    enforce_deadline: bool = True
    horizon_blocks: int = 100           # resolución de outcomes
    markout_blocks: int = 20
    min_repost_ticks: float = 1.0       # no re-postear por movimientos menores (ahorra gas)
    toxic_move_ticks: float = 8.0       # outcome de toxic_flow: el flujo anticipó ≥ esto (= feeds.MarketParams)
    neutral_ticks: float = 2.0          # outcome de direction
    stress_frac: float = 0.6            # outcome de liquidity_stressed
    initial_equity_usd: float = 100.0
    flatten_at_end: bool = True
    state_engine_kwargs: dict = field(default_factory=dict)


@dataclass
class RunResult:
    name: str = ""
    blocks: int = 0
    net_pnl: float = 0.0
    gross_spread: float = 0.0       # spread capturado en fills maker (a mid del fill)
    markout: float = 0.0            # PnL de los fills maker `markout_blocks` después (−: selección adversa)
    fees: float = 0.0
    gas: float = 0.0
    judge_cost: float = 0.0
    fills: int = 0
    maker_volume_usd: float = 0.0
    txs: int = 0
    blocks_quoted: int = 0
    pulls: int = 0
    stand_downs: int = 0
    holds: int = 0
    invalid_snapshots: int = 0
    vetoes: int = 0
    killed: bool = False
    max_dd: float = 0.0
    end_inventory: float = 0.0
    max_tokens: int = 0
    calibration: dict = field(default_factory=dict)
    equity_curve: list = field(default_factory=list)
    triples: list = field(default_factory=list)
    actions: dict = field(default_factory=dict)

    @property
    def hours(self) -> float:
        return self.blocks * 0.3 / 3600

    def row(self) -> dict:
        return {"name": self.name, "net_pnl": round(self.net_pnl, 4), "spread": round(self.gross_spread, 4),
                "markout": round(self.markout, 4), "fees": round(self.fees, 4), "gas": round(self.gas, 4),
                "judge": round(self.judge_cost, 5), "fills": self.fills, "txs": self.txs,
                "quoted%": round(100 * self.blocks_quoted / max(self.blocks, 1), 1),
                "pulls": self.pulls, "stand": self.stand_downs, "holds": self.holds,
                "max_dd%": round(100 * self.max_dd, 2), "killed": self.killed,
                "inv": round(self.end_inventory, 2)}


def run(events: Iterable[BlockEvent], judge, cfg: LoopConfig, name: str = "") -> RunResult:
    engine = StateEngine(block_s=cfg.block_s, **cfg.state_engine_kwargs)
    venue = PaperVenue(cfg.costs, cfg.tick)
    risk = RiskEngine(cfg.limits)
    fallback = RulesJudge(cfg.limits.max_position)
    res = RunResult(name=name)
    cash = cfg.initial_equity_usd
    inv = 0.0
    avg_cost = 0.0
    peak = cfg.initial_equity_usd
    charged_gas = charged_fees = 0.0
    pos_since: float | None = None
    quotes_sent = fills_seen = 0
    slip_acc = 0.0
    errors = 0
    pending_markout: deque[tuple[int, Fill]] = deque()
    pending_triples: deque[dict] = deque()
    depth_hist: list[float] = []
    mids: list[float] = []
    last_evt: BlockEvent | None = None
    desired_bid = desired_ask = None

    for evt in events:
        res.blocks += 1
        last_evt = evt
        mid = evt.mid
        mids.append(mid)
        depth_hist.append(sum(s for _, s in evt.bids[:3]) + sum(s for _, s in evt.asks[:3]))

        # 1) fills que produjo el bloque sobre lo que ya descansaba
        for f in venue.on_block(evt):
            fills_seen += 1
            q = f.size if f.side == "bid" else -f.size
            if f.side == "bid":
                cash -= f.price * f.size
                res.gross_spread += (f.mid_at_fill - f.price) * f.size
            else:
                cash += f.price * f.size
                res.gross_spread += (f.price - f.mid_at_fill) * f.size
            res.maker_volume_usd += f.price * f.size
            if inv == 0 or (inv > 0) == (q > 0):
                avg_cost = (avg_cost * abs(inv) + f.price * abs(q)) / (abs(inv) + abs(q))
            inv += q
            if abs(inv) < 1e-9:
                inv, avg_cost, pos_since = 0.0, 0.0, None
            elif pos_since is None:
                pos_since = evt.ts
            pending_markout.append((evt.block + cfg.markout_blocks, f))
        while pending_markout and pending_markout[0][0] <= evt.block:
            _, f = pending_markout.popleft()
            sign = 1.0 if f.side == "bid" else -1.0
            res.markout += sign * (mid - f.mid_at_fill) * f.size

        # costos cobrados por el venue desde el último bloque
        cash -= venue.gas_usd - charged_gas
        cash -= venue.fees_usd - charged_fees
        charged_gas, charged_fees = venue.gas_usd, venue.fees_usd

        # 2) estado y contabilidad
        engine.update(evt)
        equity = cash + inv * mid
        peak = max(peak, equity)
        dd = (peak - equity) / cfg.initial_equity_usd
        res.max_dd = max(res.max_dd, dd)
        if res.blocks % 100 == 0:
            res.equity_curve.append((evt.block, round(equity, 6)))
        if res.killed:
            continue

        port = PortfolioView(
            inventory=inv, upnl=inv * (mid - avg_cost) if inv else 0.0, drawdown=dd,
            pos_age_s=(evt.ts - pos_since) if pos_since is not None else 0.0,
            queue_pos=int(venue.bid.queue_ahead > 0) + int(venue.ask.queue_ahead > 0) if (venue.bid and venue.ask) else 0,
            fill_ratio=fills_seen / quotes_sent if quotes_sent else 0.0,
            slippage_bps=slip_acc / max(fills_seen, 1), latency_ms=getattr(judge, "latency_ms", 0.0))

        # 3) resolver triples cuyo horizonte ya llegó
        while pending_triples and pending_triples[0]["resolve_at"] <= evt.block:
            t = pending_triples.popleft()
            i = t["idx"]
            fwd = (mid - mids[i]) / cfg.tick
            flow = t["flow"]
            t["outcome"] = {
                "direction": "up" if fwd > cfg.neutral_ticks else "down" if fwd < -cfg.neutral_ticks else "neutral",
                "toxic_flow": int(flow != 0 and flow * fwd >= cfg.toxic_move_ticks),
                "liquidity_stressed": int(min(depth_hist[i:i + cfg.horizon_blocks + 1]) < cfg.stress_frac * t["depth_norm"]),
            }
            del t["resolve_at"], t["idx"], t["flow"], t["depth_norm"]
            res.triples.append(t)

        # 4) snapshot válido o HOLD
        snap = engine.snapshot(port)
        if snap is None:
            res.invalid_snapshots += 1
            res.holds += 1
            continue
        res.max_tokens = max(res.max_tokens, approx_tokens(snap))

        # 5) batería (con escalera de fallback)
        if cfg.policy_mode == "always":
            ans = None
        else:
            e0 = getattr(judge, "errors", 0)
            ans = judge.judge(snap, evt.truth)
            if ans is None:
                if getattr(judge, "errors", 0) > e0:
                    errors += 1
                    ans = fallback.judge(snap, evt.truth)     # modelo no disponible → reglas
                else:
                    res.holds += 1                              # tarde: HOLD, sin repostear
                    continue
            if cfg.enforce_deadline and getattr(judge, "latency_ms", 0.0) > cfg.deadline_ms:
                res.holds += 1
                continue
            if evt.truth or cfg.policy_mode != "always":
                pending_triples.append({
                    "resolve_at": evt.block + cfg.horizon_blocks, "idx": len(mids) - 1,
                    "flow": _sign(snap["aggr_buy"] - snap["aggr_sell"], 0.1), "depth_norm": snap["depth_norm"],
                    "block": evt.block, "truth": dict(evt.truth) if evt.truth else {},
                    "answers": {"toxic_flow": ans["toxic_flow"].p, "liquidity_stressed": ans["liquidity_stressed"].p,
                                "direction": ans["direction"].choice,
                                "direction_p": ans["direction"].dist.get(ans["direction"].choice, 0.0),
                                "quote_env": ans["quote_env"].score},
                })

        # 6) política
        dec = compose(ans, snap, cfg.limits.max_dd, cfg.thresholds, cfg.policy_mode)
        res.actions[dec.action.value] = res.actions.get(dec.action.value, 0) + 1
        if dec.action == Action.KILL:
            f = venue.flatten(evt.block, inv, evt)
            if f is not None:
                cash += (f.price * f.size) if f.side == "ask" else -(f.price * f.size)
                inv = 0.0
            res.killed = True
            continue
        if dec.action in (Action.PULL_QUOTES, Action.STAND_DOWN):
            res.pulls += dec.action == Action.PULL_QUOTES
            res.stand_downs += dec.action == Action.STAND_DOWN
            venue.cancel_all(evt.block)
            desired_bid = desired_ask = None
            continue

        # 7) precios + riesgo
        bid, ask = price_quotes(snap, dec, cfg.tick, inv, cfg.base_size, cfg.pricing,
                                evt.bids[0][0], evt.asks[0][0])
        bid, ask = risk.clip_orders(inv, bid, ask)
        verdict = risk.check(inventory=inv, daily_pnl=equity - cfg.initial_equity_usd, drawdown=dd,
                             stale_s=0.0, error_rate=errors / max(res.blocks, 1),
                             latency_ms=getattr(judge, "latency_ms", 0.0) if cfg.enforce_deadline else 0.0,
                             pos_age_s=port.pos_age_s, bid=bid, ask=ask)
        if not verdict.ok:
            res.vetoes += 1
            if verdict.kill:
                f = venue.flatten(evt.block, inv, evt)
                if f is not None:
                    cash += (f.price * f.size) if f.side == "ask" else -(f.price * f.size)
                    inv = 0.0
                res.killed = True
            else:
                venue.cancel_all(evt.block)
            continue

        # 8) post-only, evitando transacciones por movimientos < min_repost_ticks
        bid = _reuse(venue.bid, bid, cfg.min_repost_ticks * cfg.tick)
        ask = _reuse(venue.ask, ask, cfg.min_repost_ticks * cfg.tick)
        if venue.replace(evt.block, bid, ask, evt):
            quotes_sent += 1
        if venue.bid is not None or venue.ask is not None:
            res.blocks_quoted += 1

    # fin de sesión
    if last_evt is not None and cfg.flatten_at_end and not res.killed:
        f = venue.flatten(last_evt.block, inv, last_evt)
        if f is not None:
            cash += (f.price * f.size) if f.side == "ask" else -(f.price * f.size)
            inv = 0.0
        cash -= venue.gas_usd - charged_gas
        cash -= venue.fees_usd - charged_fees
    if last_evt is not None:
        res.net_pnl = cash + inv * last_evt.mid - cfg.initial_equity_usd
    res.fees = venue.fees_usd
    res.gas = venue.gas_usd
    res.judge_cost = getattr(judge, "cost_usd", 0.0) if cfg.policy_mode != "always" else 0.0
    res.fills = len([f for f in venue.fills if f.maker])
    res.txs = venue.txs
    res.end_inventory = inv
    res.calibration = summarize(res.triples) if res.triples else {}
    return res


def _sign(x: float, thr: float) -> int:
    return 1 if x > thr else -1 if x < -thr else 0


def _reuse(current, desired, tol: float):
    if current is None or desired is None:
        return desired
    if abs(current.price - desired[0]) < tol and abs(current.size - desired[1]) < 1e-12:
        return (current.price, current.size)
    return desired
