"""Motor de riesgo: vetos duros que el modelo nunca anula (Sección VII.A).

Cada límite se verifica con una medición independiente, no con lo que el
modelo dice de sí mismo. Jev provee juicios blandos que ajustan tamaño y
postura; el riesgo provee vetos duros que frenan. Si chocan, gana el veto.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Limits:
    max_position: float          # unidades del activo (inventario absoluto)
    max_order: float             # unidades por orden
    max_daily_loss: float        # USD
    max_dd: float = 0.10         # fracción del equity inicial
    max_inventory_age_s: float = 600.0
    max_stale_s: float = 2.0
    max_error_rate: float = 0.2
    max_latency_ms: float = 250.0


@dataclass
class RiskVerdict:
    ok: bool
    kill: bool = False
    reason: str = ""


class RiskEngine:
    def __init__(self, lim: Limits):
        self.lim = lim
        self.vetoes = 0

    def check(self, *, inventory: float, daily_pnl: float, drawdown: float, stale_s: float,
              error_rate: float, latency_ms: float, pos_age_s: float,
              bid: tuple[float, float] | None, ask: tuple[float, float] | None) -> RiskVerdict:
        lim = self.lim
        if daily_pnl < -lim.max_daily_loss:
            return self._veto(True, "max_daily_loss")
        if drawdown > lim.max_dd:
            return self._veto(True, "max_dd")
        if stale_s > lim.max_stale_s:
            return self._veto(False, "stale_data")
        if error_rate > lim.max_error_rate:
            return self._veto(False, "api_error_rate")
        if latency_ms > lim.max_latency_ms:
            return self._veto(False, "decision_latency")
        for side, o in (("bid", bid), ("ask", ask)):
            if o is None:
                continue
            _, size = o
            if size > lim.max_order + 1e-12:
                return self._veto(False, f"max_order:{side}")
            after = inventory + size if side == "bid" else inventory - size
            if abs(after) > lim.max_position + 1e-12 and abs(after) > abs(inventory):
                return self._veto(False, f"max_position:{side}")
        if pos_age_s > lim.max_inventory_age_s and abs(inventory) > 0:
            return RiskVerdict(True, False, "inventory_age")  # no veta: la política ya skewea; se loguea
        return RiskVerdict(True)

    def _veto(self, kill: bool, reason: str) -> RiskVerdict:
        self.vetoes += 1
        return RiskVerdict(False, kill, reason)

    def clip_orders(self, inventory: float, bid, ask):
        """Recorta (en vez de vetar) una orden que llevaría el inventario por
        encima del límite: cotizar solo el lado que reduce es válido."""
        lim = self.lim
        if bid is not None:
            room = lim.max_position - inventory
            size = min(bid[1], lim.max_order, max(room, 0.0))
            bid = (bid[0], size) if size > 0 else None
        if ask is not None:
            room = lim.max_position + inventory
            size = min(ask[1], lim.max_order, max(room, 0.0))
            ask = (ask[0], size) if size > 0 else None
        return bid, ask
