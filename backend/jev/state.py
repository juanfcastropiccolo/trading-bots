"""Motor de estado determinístico (Sección IV del paper).

Corre en cada bloque y emite un snapshot numérico compacto con las siete
familias de features. Tres reglas lo mantienen válido:
  1. < 400 tokens: denso y numérico, sin prosa.
  2. Causalidad estricta: cada campo usa solo información con timestamp
     anterior al instante de decisión (eq. 6).
  3. Cada snapshot se loguea con la decisión y el resultado (calibración).

Además es la primera línea de defensa ("bottleneck guard"): un campo que no
se puede calcular, un feed viejo o un valor fuera de rango se rechaza acá y
nunca llega a Jev.
"""
from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class BlockEvent:
    """Lo que el venue publica por bloque. `prints` son los trades agresores
    ocurridos en el bloque (lado del agresor, precio, tamaño); `bids`/`asks`
    son el libro al cierre del bloque, mejor nivel primero."""
    block: int
    ts: float
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    prints: list[tuple[str, float, float]] = field(default_factory=list)
    # Solo en el mercado sintético: latentes verdaderos para el juez oráculo.
    truth: dict = field(default_factory=dict)

    @property
    def mid(self) -> float:
        return (self.bids[0][0] + self.asks[0][0]) / 2


@dataclass
class PortfolioView:
    """Familias 'portfolio' y 'execution health' que el loop conoce y el motor
    de estado solo copia al snapshot."""
    inventory: float = 0.0
    upnl: float = 0.0
    drawdown: float = 0.0
    pos_age_s: float = 0.0
    queue_pos: int = 0
    fill_ratio: float = 0.0
    slippage_bps: float = 0.0
    latency_ms: float = 0.0


class StateEngine:
    """Ventanas rodantes O(1) por bloque. Todas las ventanas están en bloques."""

    def __init__(self, block_s: float = 0.3, w_1m: int | None = None, w_5m: int | None = None,
                 w_30m: int | None = None, w_regime: int | None = None, w_flow: int = 100,
                 max_gap_blocks: int = 5, levels: int = 3):
        per_min = round(60 / block_s)
        self.block_s = block_s
        self.w_1m = w_1m or per_min
        self.w_5m = w_5m or 5 * per_min
        self.w_30m = w_30m or 30 * per_min
        self.w_regime = w_regime or 240 * per_min      # "norma" de vol y profundidad
        self.w_flow = w_flow
        self.max_gap_blocks = max_gap_blocks
        self.levels = levels

        self.mids: deque[float] = deque(maxlen=self.w_regime + 1)
        self.rets: deque[float] = deque(maxlen=self.w_regime)
        self._sq5 = _RollingSumSq(self.w_5m)
        self._sq30 = _RollingSumSq(self.w_30m)
        self._sqreg = _RollingSumSq(self.w_regime)
        self._depth_hist: deque[float] = deque(maxlen=self.w_regime)
        self._depth_sum = 0.0
        self._flow: deque[tuple[float, float, int]] = deque(maxlen=self.w_flow)  # (buy, sell, n)
        self._flow_buy = self._flow_sell = 0.0
        self._flow_n = 0
        self._cancel: deque[float] = deque(maxlen=self.w_flow)
        self._cancel_sum = 0.0
        self._prev_depth: float | None = None
        self.last: BlockEvent | None = None
        self.n = 0
        self.rejections = 0

    # ---------------------------------------------------------------- update
    def update(self, evt: BlockEvent) -> None:
        if self.last is not None and evt.block - self.last.block > self.max_gap_blocks:
            # feed con hueco: reiniciar ventanas cortas es más honesto que interpolar
            self._flow.clear(); self._flow_buy = self._flow_sell = 0.0; self._flow_n = 0
        mid = evt.mid
        if self.mids:
            r = math.log(mid / self.mids[-1])
            self.rets.append(r)
            self._sq5.push(r); self._sq30.push(r); self._sqreg.push(r)
        self.mids.append(mid)

        depth = sum(s for _, s in evt.bids[:self.levels]) + sum(s for _, s in evt.asks[:self.levels])
        if len(self._depth_hist) == self._depth_hist.maxlen:
            self._depth_sum -= self._depth_hist[0]
        self._depth_hist.append(depth); self._depth_sum += depth
        if self._prev_depth is not None:
            c = abs(depth - self._prev_depth) / max(self._prev_depth, 1e-12)
            if len(self._cancel) == self._cancel.maxlen:
                self._cancel_sum -= self._cancel[0]
            self._cancel.append(c); self._cancel_sum += c
        self._prev_depth = depth

        b = sum(s for side, _, s in evt.prints if side == "buy")
        s = sum(s for side, _, s in evt.prints if side == "sell")
        if len(self._flow) == self._flow.maxlen:
            ob, os_, on = self._flow[0]
            self._flow_buy -= ob; self._flow_sell -= os_; self._flow_n -= on
        self._flow.append((b, s, len(evt.prints)))
        self._flow_buy += b; self._flow_sell += s; self._flow_n += len(evt.prints)
        self.last = evt
        self.n += 1

    # -------------------------------------------------------------- snapshot
    @property
    def warm(self) -> bool:
        return self.n > self.w_5m

    def ret(self, w: int) -> float:
        if len(self.mids) <= w:
            return 0.0
        return self.mids[-1] / self.mids[-1 - w] - 1

    def rvol(self, roll: "_RollingSumSq") -> float:
        """Vol realizada sobre el horizonte de la ventana (fracción)."""
        return roll.std() * math.sqrt(roll.n) if roll.n > 1 else 0.0

    def depth_norm(self) -> float:
        return self._depth_sum / len(self._depth_hist) if self._depth_hist else 0.0

    def snapshot(self, port: PortfolioView) -> dict | None:
        """Devuelve el snapshot o None si no es válido (nunca se manda un
        snapshot malformado). Las causas se cuentan en `rejections`."""
        evt = self.last
        if evt is None or not self.warm or len(evt.bids) < 1 or len(evt.asks) < 1:
            self.rejections += 1
            return None
        bb, bs = evt.bids[0]
        ba, as_ = evt.asks[0]
        if not (bb > 0 and ba > bb and bs > 0 and as_ > 0):
            self.rejections += 1
            return None
        mid = (bb + ba) / 2
        micro = (bb * as_ + ba * bs) / (bs + as_)
        depth_b = sum(s for _, s in evt.bids[:self.levels])
        depth_a = sum(s for _, s in evt.asks[:self.levels])
        tot = self._flow_buy + self._flow_sell
        rv5, rv30, rvreg = self.rvol(self._sq5), self.rvol(self._sq30), self.rvol(self._sqreg)
        snap = {
            # precio
            "mid": mid, "microprice": micro,
            "ret_1m": self.ret(self.w_1m), "ret_5m": self.ret(self.w_5m),
            # libro
            "spread_bps": (ba - bb) / mid * 1e4,
            "imbalance": (depth_b - depth_a) / (depth_b + depth_a),
            "depth_3": depth_b + depth_a,
            "depth_norm": self.depth_norm(),
            "queue_pos": port.queue_pos,
            # flujo
            "aggr_buy": self._flow_buy / tot if tot else 0.5,
            "aggr_sell": self._flow_sell / tot if tot else 0.5,
            "trade_intensity": self._flow_n / (len(self._flow) * self.block_s) if self._flow else 0.0,
            "cancel_intensity": self._cancel_sum / len(self._cancel) if self._cancel else 0.0,
            # volatilidad
            "rvol_5m": rv5, "rvol_30m": rv30,
            "vol_regime": rv5 / rvreg * math.sqrt(self.w_regime / self.w_5m) if rvreg > 0 else 1.0,
            # portafolio
            "inventory": port.inventory, "upnl": port.upnl,
            "drawdown": port.drawdown, "pos_age_s": port.pos_age_s,
            # salud de ejecución
            "fill_ratio": port.fill_ratio, "slippage_bps": port.slippage_bps,
            "latency_ms": port.latency_ms,
        }
        for k, v in snap.items():
            if not math.isfinite(v):
                self.rejections += 1
                return None
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in snap.items()}


def approx_tokens(snap: dict) -> int:
    """~4 caracteres por token sobre el JSON compacto: la métrica del budget de 400."""
    return math.ceil(len(json.dumps(snap, separators=(",", ":"))) / 4)


class _RollingSumSq:
    def __init__(self, w: int):
        self.buf: deque[float] = deque(maxlen=w)
        self.s = 0.0
        self.s2 = 0.0

    def push(self, x: float) -> None:
        if len(self.buf) == self.buf.maxlen:
            o = self.buf[0]; self.s -= o; self.s2 -= o * o
        self.buf.append(x); self.s += x; self.s2 += x * x

    @property
    def n(self) -> int:
        return len(self.buf)

    def std(self) -> float:
        n = self.n
        if n < 2:
            return 0.0
        var = max(self.s2 / n - (self.s / n) ** 2, 0.0)
        return math.sqrt(var)
