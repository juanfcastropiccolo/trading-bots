"""Policy engine determinístico (Sección V.B), Kelly fraccional (V.C) y
precios de Avellaneda-Stoikov (VI.A).

Tres principios: los vetos preceden a las señales; los umbrales son por
acción, no globales (un stand-down equivocado no cuesta nada, una cotización
equivocada cuesta capital); el tamaño deriva de la probabilidad calibrada vía
Kelly fraccional, y eso solo es defendible con un modelo calibrado.

Los umbrales viven acá, en código, y se cambian editando un coeficiente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .battery import Judgment


class Action(str, Enum):
    KILL = "KILL"                  # límite duro: aplanar y parar
    PULL_QUOTES = "PULL_QUOTES"    # flujo tóxico: sacar las órdenes
    WIDEN = "WIDEN"                # liquidez estresada: cotizar ancho
    QUOTE_BOTH = "QUOTE_BOTH"      # operación normal, con skew de inventario
    QUOTE_WIDE = "QUOTE_WIDE"      # entorno marginal: ancho y a mitad de tamaño
    STAND_DOWN = "STAND_DOWN"      # sin cotizar
    HOLD = "HOLD"                  # sin decisión nueva (deadline / snapshot inválido)


@dataclass
class Thresholds:
    toxic_pull: float = 0.60
    liquidity_widen: float = 0.70
    quote_env_min_score: int = 2
    quote_env_min_conf: float = 0.80
    kelly_cap: float = 0.25
    wide_mult: float = 2.0
    wide_size_mult: float = 0.5
    # Desvío opcional del paper: al hacer PULL_QUOTES, mantener la cotización
    # del lado que reduce inventario (la literal saca ambos lados y deja el
    # inventario expuesto durante todo el episodio tóxico).
    pull_keep_reducing: bool = False


@dataclass
class Decision:
    action: Action
    width_mult: float = 1.0
    size_bid: float = 1.0          # multiplicadores sobre el tamaño base
    size_ask: float = 1.0
    skew_ticks: float = 0.0        # > 0 desplaza ambas cotizaciones hacia arriba
    reason: str = ""


def kelly_fraction(p: float, c: float = 0.25) -> float:
    """f = c · max(0, 2p − 1) (eq. 7). Solo tiene sentido con p calibrada."""
    return c * max(0.0, 2 * p - 1)


def skew_of(inventory_pressure, inventory: float) -> tuple[float, str | None]:
    """Score 0..3 → (skew en ticks hacia el lado que reduce inventario, lado único).
    3 = "Reduce now": solo se cotiza el lado que reduce."""
    lvl = inventory_pressure.score or 0
    toward = -1.0 if inventory > 0 else 1.0 if inventory < 0 else 0.0
    if lvl == 0:
        return 0.0, None
    if lvl == 1:
        return 0.5 * toward, None
    if lvl == 2:
        return 1.0 * toward, None
    return 1.5 * toward, ("ask" if inventory > 0 else "bid")


def compose(a: Judgment | None, snap: dict, max_dd: float, th: Thresholds = Thresholds(),
            mode: str = "gated") -> Decision:
    """Compone la batería en una acción.

    mode:
      gated   la política del paper: vetos, umbrales por acción, Kelly.
      argmax  ignora la calibración: cada pregunta vale por su argmax (p > 0.5),
              tamaño fijo. Aísla el "valor de la calibración" (Tabla VI).
      always  sin juicio: cotiza ambos lados siempre (piso mecánico del A-S).
    """
    if snap["drawdown"] > max_dd:
        return Decision(Action.KILL, reason="max_dd")
    if mode == "always" or a is None:
        return Decision(Action.QUOTE_BOTH, reason="no_judgment")

    if mode == "argmax":
        if a["toxic_flow"].p > 0.5:
            return Decision(Action.PULL_QUOTES, reason="toxic")
        if a["liquidity_stressed"].p > 0.5:
            return Decision(Action.WIDEN, width_mult=th.wide_mult, reason="liquidity")
        if (a["quote_env"].score or 0) == 0:
            return Decision(Action.STAND_DOWN, reason="quote_env=0")
        skew, only = skew_of(a["inventory_pressure"], snap["inventory"])
        return Decision(Action.QUOTE_BOTH, skew_ticks=skew,
                        size_bid=0.0 if only == "ask" else 1.0,
                        size_ask=0.0 if only == "bid" else 1.0, reason="argmax")

    # ---- gated (paper)
    if a["toxic_flow"].p > th.toxic_pull:
        inv = snap["inventory"]
        if th.pull_keep_reducing and inv != 0:
            return Decision(Action.QUOTE_BOTH, size_bid=0.0 if inv > 0 else 1.0,
                            size_ask=1.0 if inv > 0 else 0.0, reason="toxic:reduce_only")
        return Decision(Action.PULL_QUOTES, reason="toxic")
    if a["liquidity_stressed"].p > th.liquidity_widen:
        return Decision(Action.WIDEN, width_mult=th.wide_mult, reason="liquidity")
    q = a["quote_env"]
    if (q.score or 0) >= th.quote_env_min_score and q.confidence > th.quote_env_min_conf:
        skew, only = skew_of(a["inventory_pressure"], snap["inventory"])
        d = a["direction"]
        f = kelly_fraction(d.dist.get(d.choice, 0.0), th.kelly_cap)
        size_bid, size_ask = 1.0, 1.0
        if d.choice == "up":
            size_bid, size_ask = 1 + f, max(1 - f, 0.0)
        elif d.choice == "down":
            size_bid, size_ask = max(1 - f, 0.0), 1 + f
        if only == "ask":
            size_bid = 0.0
        elif only == "bid":
            size_ask = 0.0
        return Decision(Action.QUOTE_BOTH, skew_ticks=skew, size_bid=size_bid, size_ask=size_ask,
                        reason=f"quote_env={q.score} conf={q.confidence:.2f}")
    if (q.score or 0) >= 1:
        return Decision(Action.QUOTE_WIDE, width_mult=th.wide_mult,
                        size_bid=th.wide_size_mult, size_ask=th.wide_size_mult, reason="quote_env=1")
    return Decision(Action.STAND_DOWN, reason="quote_env=0")


# ------------------------------------------------------------ Avellaneda-Stoikov
def avellaneda_stoikov(mid: float, q: float, gamma: float, sigma: float, horizon: float,
                       kappa: float) -> tuple[float, float]:
    """Eq. (8) y (9): precio de reserva r y spread óptimo total δ (bid = r − δ/2,
    ask = r + δ/2). σ en unidades de precio por √unidad de `horizon`; q en
    unidades del activo; γ aversión al riesgo; κ intensidad de llegada."""
    var_t = sigma * sigma * horizon
    r = mid - q * gamma * var_t
    delta = gamma * var_t + (2 / gamma) * math.log(1 + gamma / kappa)
    return r, delta


@dataclass
class PricingParams:
    """A-S se evalúa en unidades de tick, con el inventario normalizado por el
    tamaño base (q = inventario / base_size): así γ y κ son adimensionales y
    los mismos valores sirven para MON a $0.02 o BTC a $100k."""
    gamma: float = 0.05
    kappa: float = 1.5
    horizon_s: float = 3.0      # horizonte efectivo de re-cotización a cadencia de bloque
    min_half_spread_ticks: float = 1.0
    floor_frac_market: float = 0.75  # nunca cotizar más adentro que esta fracción del half-spread del mercado


def price_quotes(snap: dict, dec: Decision, tick: float, inventory: float, base_size: float,
                 pp: PricingParams, best_bid: float, best_ask: float) -> tuple[tuple[float, float] | None,
                                                                              tuple[float, float] | None]:
    """Devuelve ((bid_px, bid_sz) | None, (ask_px, ask_sz) | None), redondeadas
    al tick y con la restricción post-only: nunca se cruza el touch."""
    if dec.action not in (Action.QUOTE_BOTH, Action.QUOTE_WIDE, Action.WIDEN):
        return None, None
    mid = snap["mid"]
    sigma_ticks = snap["rvol_5m"] * mid / tick / math.sqrt(300.0)     # ticks por √segundo
    r_t, delta_t = avellaneda_stoikov(mid / tick, inventory / base_size, pp.gamma, sigma_ticks,
                                      pp.horizon_s, pp.kappa)
    market_half = (best_ask - best_bid) / 2 / tick
    half = max(delta_t / 2, pp.min_half_spread_ticks, pp.floor_frac_market * market_half) * dec.width_mult
    r_t += dec.skew_ticks
    bid = math.floor(r_t - half) * tick
    ask = math.ceil(r_t + half) * tick
    bid = min(bid, best_ask - tick)      # post-only: por debajo del mejor ask
    ask = max(ask, best_bid + tick)
    b = (bid, base_size * dec.size_bid) if dec.size_bid > 0 else None
    a = (ask, base_size * dec.size_ask) if dec.size_ask > 0 else None
    return b, a
