"""Feeds de bloques: mercado sintético con latentes conocidos, replay de
grabaciones y grabador de datos reales vía ccxt.

Todos producen la misma secuencia de `BlockEvent`, así el loop, el venue de
papel y la calibración no distinguen de dónde viene el dato.

Mercado sintético
-----------------
Modela lo que hace o deshace a un market maker de cadencia por bloque:
  - régimen de volatilidad (calmo / alto) como cadena de Markov;
  - episodios de flujo informado ("tóxico"): el mid deriva `toxic_drift` ticks
    por bloque en una dirección y el flujo agresor se sesga hacia ella. Quien
    cotiza durante el episodio queda llenado del lado equivocado (selección
    adversa) y marcado en contra después;
  - episodios de estrés de liquidez: profundidad × 0.3 y spread × 2;
  - huellas observables: el lado hacia el que va el flujo informado queda más
    fino (imbalance), la intensidad de trades sube. El juez de reglas ve eso;
    el oráculo ve el latente con ruido controlado por `a`.
Es un modelo, no un mercado: sirve para medir la estructura de costos y qué
calidad de juicio hace falta, no para estimar el PnL esperado en un venue real.
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field

from .state import BlockEvent


@dataclass
class MarketParams:
    mid0: float = 0.0226            # MON-USDC del demo
    tick_bps: float = 0.44          # tamaño del tick en bps del mid
    block_s: float = 0.3
    spread_ticks_calm: int = 16     # ~7 bps
    spread_ticks_vol: int = 24
    sigma_calm_ticks: float = 1.0   # ruido por bloque
    sigma_vol_ticks: float = 3.0
    p_calm_to_vol: float = 1 / 3000
    p_vol_to_calm: float = 1 / 1000
    # episodios de flujo informado sostenido ("tóxico")
    toxic_start_p: float = 1 / 900
    toxic_len_mean: float = 60.0
    toxic_drift_ticks: float = 1.5
    toxic_flow_bias: float = 0.35
    # prints informados aislados: cada print agresor es informado con prob
    # p_informed y empuja el mid `impact_ticks` en su dirección a lo largo de
    # `impact_blocks` bloques. Es el mecanismo básico por el que un maker
    # ingenuo pierde: el spread que cobra tiene que pagar este mark-out.
    p_informed_calm: float = 0.35
    p_informed_vol: float = 0.5
    impact_ticks: float = 12.0
    impact_blocks: int = 20
    informed_size_mult: float = 1.0  # los prints informados son más grandes (barren la cola: winner's curse)
    # estrés de liquidez
    stress_start_p: float = 1 / 2000
    stress_len_mean: float = 200.0
    depth_l1: float = 1000.0        # unidades del activo por nivel (L1); L2 = 2×, L3 = 3×
    depth_stress_mult: float = 0.3
    trades_per_block_calm: float = 0.3
    trades_per_block_vol: float = 0.8
    trades_per_block_toxic_extra: float = 0.5
    trade_size_mean: float = 300.0
    # outcomes (misma regla que loop.py)
    horizon_blocks: int = 100
    neutral_ticks: float = 2.0
    toxic_move_ticks: float = 8.0
    flow_window: int = 100
    flow_threshold: float = 0.1
    stress_frac: float = 0.6
    depth_norm_window: int = 48000


class SyntheticMarket:
    def __init__(self, params: MarketParams, n_blocks: int, seed: int = 0):
        self.p = params
        self.n = n_blocks
        self.seed = seed
        self.events: list[BlockEvent] = []
        self._priors: dict = {}

    @property
    def tick(self) -> float:
        return self.p.mid0 * self.p.tick_bps / 1e4

    def generate(self) -> list[BlockEvent]:
        p, rng = self.p, random.Random(self.seed)
        tick = self.tick
        total = self.n + p.horizon_blocks + 1
        base = p.mid0 / tick
        mid_t = [0.0] * total
        rows: list[tuple] = []
        v, tox_left, tox_dir, st_left = False, 0, 0, 0
        m = 0.0
        impact = [0.0] * (total + p.impact_blocks + 1)   # deriva pendiente por bloque
        prev_bid = prev_ask = None
        depth3: list[float] = []
        flow_buy: list[float] = []
        flow_sell: list[float] = []
        for i in range(total):
            v = (not v) if rng.random() < (p.p_vol_to_calm if v else p.p_calm_to_vol) else v
            if tox_left > 0:
                tox_left -= 1
            elif rng.random() < p.toxic_start_p:
                tox_left = max(1, int(rng.expovariate(1 / p.toxic_len_mean)))
                tox_dir = rng.choice((-1, 1))
            if st_left > 0:
                st_left -= 1
            elif rng.random() < p.stress_start_p:
                st_left = max(1, int(rng.expovariate(1 / p.stress_len_mean)))
            d = tox_dir if tox_left > 0 else 0
            st = st_left > 0
            sig = p.sigma_vol_ticks if v else p.sigma_calm_ticks
            # prints del bloque, al touch del bloque anterior
            lam = (p.trades_per_block_vol if v else p.trades_per_block_calm) + (p.trades_per_block_toxic_extra if d else 0)
            p_inf = p.p_informed_vol if v else p.p_informed_calm
            prints = []
            spread_prev = (p.spread_ticks_vol if v else p.spread_ticks_calm) * (2 if st else 1)
            pb = prev_bid if prev_bid is not None else (base + m - spread_prev / 2) * tick
            pa = prev_ask if prev_ask is not None else (base + m + spread_prev / 2) * tick
            for _ in range(_poisson(rng, lam)):
                buy = rng.random() < 0.5 + p.toxic_flow_bias * d
                informed = rng.random() < p_inf
                size = rng.lognormvariate(math.log(p.trade_size_mean), 0.8) * (p.informed_size_mult if informed else 1.0)
                prints.append(("buy", pa, size) if buy else ("sell", pb, size))
                if informed:
                    per = p.impact_ticks / p.impact_blocks * (1 if buy else -1)
                    for j in range(i + 1, i + 1 + p.impact_blocks):
                        impact[j] += per
            m += d * p.toxic_drift_ticks + impact[i] + rng.gauss(0, sig)
            mid_t[i] = m
            spread = (p.spread_ticks_vol if v else p.spread_ticks_calm) * (2 if st else 1)
            half = spread / 2
            mid_ticks = base + m
            bb = math.floor(mid_ticks - half)
            ba = math.ceil(mid_ticks + half)
            if ba <= bb:
                ba = bb + 1
            dmult = p.depth_stress_mult if st else 1.0
            bids, asks = [], []
            for lvl in range(3):
                dep = p.depth_l1 * (lvl + 1) * dmult
                bids.append(((bb - lvl) * tick, dep * rng.lognormvariate(0, 0.35) * (1 + 0.3 * d)))
                asks.append(((ba + lvl) * tick, dep * rng.lognormvariate(0, 0.35) * (1 - 0.3 * d)))
            prev_bid, prev_ask = bb * tick, ba * tick
            if i < self.n:
                rows.append((v, d, st, bids, asks, prints))
                depth3.append(sum(s for _, s in bids) + sum(s for _, s in asks))
                flow_buy.append(sum(s for side, _, s in prints if side == "buy"))
                flow_sell.append(sum(s for side, _, s in prints if side == "sell"))

        events: list[BlockEvent] = []
        run_depth = 0.0
        for i, (v, d, st, bids, asks, prints) in enumerate(rows):
            fwd = mid_t[i + p.horizon_blocks] - mid_t[i]
            direction = "up" if fwd > p.neutral_ticks else "down" if fwd < -p.neutral_ticks else "neutral"
            regime = "crisis" if (v and st) else "high_vol" if v else "trending" if d else "mean_reverting"
            quiet = abs(fwd) <= p.neutral_ticks
            qe = 0 if d else 1 if (v or st) else 3 if quiet else 2
            lo = max(0, i - p.flow_window + 1)
            b, s = sum(flow_buy[lo:i + 1]), sum(flow_sell[lo:i + 1])
            flow = (b - s) / (b + s) if b + s else 0.0
            fsign = 1 if flow > p.flow_threshold else -1 if flow < -p.flow_threshold else 0
            run_depth += depth3[i]
            if i >= p.depth_norm_window:
                run_depth -= depth3[i - p.depth_norm_window]
            norm = run_depth / min(i + 1, p.depth_norm_window)
            fut = depth3[i:i + p.horizon_blocks + 1]
            truth = {"latent_toxic": int(d != 0), "latent_stressed": int(st), "direction": direction,
                     "regime": regime, "quote_env": qe, "vol": int(v), "fwd_ticks": fwd,
                     "toxic": int(fsign != 0 and fsign * fwd >= p.toxic_move_ticks),
                     "stressed": int(min(fut) < p.stress_frac * norm)}
            events.append(BlockEvent(i, i * p.block_s, bids, asks, prints, truth))
        self.events = events
        self._priors = _priors(events)
        return events

    @property
    def priors(self) -> dict:
        return self._priors


def _priors(events: list[BlockEvent]) -> dict:
    n = len(events)
    out: dict = {"toxic": {}, "stressed": {}, "direction": {}, "regime": {}, "quote_env": {}}
    for k in ("toxic", "stressed"):
        r = sum(e.truth[k] for e in events) / n
        out[k] = {1: r, 0: 1 - r}
    for k in ("direction", "regime", "quote_env"):
        cnt: dict = {}
        for e in events:
            cnt[e.truth[k]] = cnt.get(e.truth[k], 0) + 1
        out[k] = {c: v / n for c, v in cnt.items()}
    return out


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


# ------------------------------------------------------------------ grabado
def write_jsonl(events: list[BlockEvent], path: str) -> None:
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps({"block": e.block, "ts": e.ts, "bids": e.bids, "asks": e.asks,
                                 "prints": e.prints}) + "\n")


def read_jsonl(path: str):
    """Replay de una grabación (`jev_record.py`) o de un sintético exportado."""
    with open(path) as fh:
        for line in fh:
            if line.strip():
                d = json.loads(line)
                yield BlockEvent(d["block"], d["ts"], [tuple(x) for x in d["bids"]],
                                 [tuple(x) for x in d["asks"]], [tuple(x) for x in d.get("prints", [])])


def record(exchange_id: str, symbol: str, seconds: float, out_path: str, interval_s: float = 1.0,
           levels: int = 5) -> int:
    """Graba libro L2 + prints con ccxt a `interval_s` (un "bloque" por muestra).

    Los prints se deduplican por id de trade. Devuelve la cantidad de bloques.
    Nota: un CEX no expone bloques; el intervalo de muestreo hace de cadencia.
    """
    import ccxt

    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    seen: set = set()
    n = 0
    t_end = time.time() + seconds
    with open(out_path, "w") as fh:
        while time.time() < t_end:
            t0 = time.time()
            ob = ex.fetch_order_book(symbol, limit=levels)
            trades = ex.fetch_trades(symbol, limit=50)
            prints = []
            for t in trades:
                key = t.get("id") or (t["timestamp"], t["price"], t["amount"])
                if key in seen:
                    continue
                seen.add(key)
                if t.get("side") in ("buy", "sell"):
                    prints.append((t["side"], float(t["price"]), float(t["amount"])))
            fh.write(json.dumps({"block": n, "ts": t0, "bids": ob["bids"][:levels],
                                 "asks": ob["asks"][:levels], "prints": prints}) + "\n")
            fh.flush()
            n += 1
            time.sleep(max(0.0, interval_s - (time.time() - t0)))
    return n


# ------------------------------------------------------------------ presets
@dataclass
class MarketPreset:
    """Un mercado sintético + el nivel de competencia por el interior del spread
    (que vive en VenueCosts porque es el venue quien asigna la cola)."""
    params: MarketParams
    inside_queue_p: float = 0.0
    inside_queue_mean: float = 0.0
    note: str = ""


MARKETS: dict[str, MarketPreset] = {
    # Flujo mayormente no informado y nadie compite por el interior del spread:
    # el mejor caso posible para un maker ingenuo.
    "benigno": MarketPreset(
        MarketParams(sigma_calm_ticks=0.7, sigma_vol_ticks=2.0, trades_per_block_calm=0.4,
                     p_informed_calm=0.35, p_informed_vol=0.5, impact_ticks=8.0),
        note="35-50% de prints informados con impacto de ~3.5 bps; sin competencia adentro del spread"),
    # Winner's curse: los prints informados son 4× más grandes y barren la
    # cola; 70% de las veces hay otros makers adentro del spread antes que
    # nosotros, así que el flujo chico (no informado) rara vez nos llega.
    "hostil": MarketPreset(
        MarketParams(sigma_calm_ticks=0.7, sigma_vol_ticks=2.0, trades_per_block_calm=0.4,
                     p_informed_calm=0.5, p_informed_vol=0.7, impact_ticks=24.0,
                     informed_size_mult=4.0, trade_size_mean=150.0),
        inside_queue_p=0.7, inside_queue_mean=250.0,
        note="50-70% de prints informados 4× más grandes con impacto de ~10 bps; competencia adentro del spread"),
}
