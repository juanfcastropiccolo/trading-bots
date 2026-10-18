"""Paper trading diario long-only con capital ficticio de $1000.

Segunda cuenta long-only, en paralelo a la de $100 (momentum_paper.py). La
configuración sale de la validación con lista cerrada de trials de
scripts/validate_momentum_1k.py (resultados en VALIDACION_1K.md); el motor
soporta todas las variantes declaradas (top-K, histéresis, vol targeting,
ensemble de lookbacks) y la config elegida se fija en las constantes.

Mecánica igual a producción: decisión diaria, se opera solo cuando cambia el
conjunto de posiciones (con vol targeting, además se reescala los lunes).
Costos simulados 0.15% por lado. Estado en backend/data/momentum_1k_state.json.
Idempotente por día.

Uso:  python scripts/momentum_1k_paper.py [--force] [--check]
"""
import argparse
import json
import os
from datetime import date, datetime

import ccxt

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
]

# --- Config elegida por VALIDACION_1K.md (no tocar sin re-validar) ---------
TOP_K = 2
LOOKBACKS = [30]        # ensemble: varios lookbacks promediados
HYST = None             # histéresis: una posición conserva su slot mientras
                        # siga en el top-HYST y sobre su SMA; None = sin banda
VOLTARGET = None        # vol anualizada objetivo por posición; None = sin overlay
# ---------------------------------------------------------------------------

TREND_W = 100
COST = 0.0015
BUDGET = 1000.0
MIN_TRADE = 5.0         # USD; min notional realista de spot con $1000

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_1k_state.json")
EXCHANGE_IDS = os.environ.get("EXCHANGE_ID", "binance").split(",")

N_CANDLES = max(TREND_W, max(LOOKBACKS), 31) + 5


def fetch_closes() -> tuple[dict, dict, str]:
    last_err = None
    for exid in [e.strip() for e in EXCHANGE_IDS if e.strip()]:
        try:
            ex = getattr(ccxt, exid)({"enableRateLimit": True})
            closes = {}
            for s in SYMBOLS:
                candles = ex.fetch_ohlcv(s, timeframe="1d", limit=N_CANDLES)
                closes[s] = [c[4] for c in candles]
            prices = {s: series[-1] for s, series in closes.items()}
            return closes, prices, exid
        except Exception as e:
            last_err = e
            print(f"⚠️  {exid} falló ({type(e).__name__}: {str(e)[:100]}); pruebo el siguiente…")
    raise SystemExit(f"Ningún exchange disponible de {EXCHANGE_IDS}: {last_err}")


def signals(closes: dict) -> tuple[dict, list]:
    """Score de momentum, filtro de tendencia y vol 30d por símbolo."""
    scores = {}
    for s, series in closes.items():
        if len(series) < max(TREND_W, max(LOOKBACKS)) + 1:
            continue
        mom = sum(series[-1] / series[-1 - lb] - 1 for lb in LOOKBACKS) / len(LOOKBACKS)
        sma = sum(series[-TREND_W:]) / TREND_W
        rets = [series[i] / series[i - 1] - 1 for i in range(-30, 0)]
        mean = sum(rets) / len(rets)
        vol = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 * (365 ** 0.5)
        scores[s] = {"momentum": mom, "above_trend": series[-1] > sma, "vol30": vol}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1]["momentum"])
    return scores, ranked


def pick_targets(ranked: list, held_syms: set) -> list:
    """Top-K con banda de histéresis opcional (réplica de validate_momentum_1k)."""
    order = [s for s, _ in ranked]
    above = {s: sc["above_trend"] for s, sc in ranked}
    if HYST:
        band = set(order[:HYST])
        picks = [s for s in order if s in held_syms and s in band and above[s]]
    else:
        picks = [s for s in order[:TOP_K] if s in held_syms and above[s]]
    for s in order[:TOP_K]:
        if len(picks) >= TOP_K:
            break
        if s not in picks and above[s]:
            picks.append(s)
    return picks


def target_weights(picks: list, scores: dict) -> dict:
    weights = {}
    for s in picks:
        w = 1.0 / TOP_K
        if VOLTARGET:
            v = scores[s]["vol30"]
            if v > 0:
                w *= min(1.0, VOLTARGET / v)
        weights[s] = w
    return weights


def held(state: dict) -> dict:
    return {s: q for s, q in state["holdings"].items() if q > 0}


def rebalance(state: dict, weights: dict, prices: dict) -> list[str]:
    """Lleva el portafolio a los pesos objetivo. Vende primero, después compra."""
    state["holdings"] = held(state)
    log = []
    equity = state["cash"] + sum(q * prices[s] for s, q in state["holdings"].items())

    # 1) ventas: lo que sale del target y el exceso de lo que queda
    for s in sorted(state["holdings"]):
        qty = state["holdings"][s]
        goal = weights.get(s, 0.0) * equity
        excess = qty * prices[s] - goal
        if excess <= MIN_TRADE:
            continue
        sell_qty = qty if goal == 0.0 else excess / prices[s]
        proceeds = sell_qty * prices[s] * (1 - COST)
        state["cash"] += proceeds
        if sell_qty >= qty:
            state["holdings"].pop(s)
            log.append(f"SELL {s}: {qty:.6f} @ {prices[s]:.4f} → +${proceeds:.2f}")
        else:
            state["holdings"][s] = qty - sell_qty
            log.append(f"TRIM {s}: -{sell_qty:.6f} @ {prices[s]:.4f} → +${proceeds:.2f}")

    # 2) compras: hasta el peso objetivo, limitado por el cash disponible
    for s, w in weights.items():
        have = state["holdings"].get(s, 0.0) * prices[s]
        spend = min(w * equity - have, state["cash"])
        if spend <= MIN_TRADE:
            continue
        qty = spend * (1 - COST) / prices[s]
        state["holdings"][s] = state["holdings"].get(s, 0.0) + qty
        state["cash"] -= spend
        verb = "BUY " if have == 0 else "ADD "
        log.append(f"{verb} {s}: {qty:.6f} @ {prices[s]:.4f} (${spend:.2f})")
    return log


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"cash": BUDGET, "holdings": {}, "history": [], "last_run": None}


def save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="correr aunque ya haya corrido hoy")
    ap.add_argument("--check", action="store_true",
                    help="solo mostrar ranking y señales; no modifica el estado")
    args = ap.parse_args()

    state = load_state()
    today = date.today().isoformat()
    if state["last_run"] == today and not (args.force or args.check):
        print(f"Ya corrió hoy ({today}). Usá --force para repetir.")
        return

    closes, prices, exid = fetch_closes()
    scores, ranked = signals(closes)
    current = held(state)
    picks = pick_targets(ranked, set(current))

    print(f"=== Momentum $1000 — {today} (datos: {exid}) ===")
    print(f"{'símbolo':10s} {'score':>8s}  sobre_SMA100  vol30")
    for s, sc in ranked:
        mark = " ← TARGET" if s in picks else ""
        print(f"{s:10s} {sc['momentum']*100:+7.2f}%  {str(sc['above_trend']):5s}        "
              f"{sc['vol30']*100:5.1f}%{mark}")

    if args.check:
        if set(picks) != set(current):
            print(f"\n⚠️  SEÑAL: target cambiaría de {sorted(current) or ['cash']} "
                  f"a {sorted(picks) or ['cash']} (se aplica en el tick diario)")
        else:
            print(f"\nSin señales nuevas: target sigue {sorted(current) or ['cash']}")
        return

    # se opera solo si cambió el conjunto; con voltarget también se reescala los lunes
    is_monday = date.today().weekday() == 0
    if set(picks) != set(current) or (VOLTARGET and is_monday):
        for line in rebalance(state, target_weights(picks, scores), prices):
            print(line)
    else:
        print(f"Sin cambios: mantengo {sorted(current) or ['cash']}")

    equity = state["cash"] + sum(q * prices[s] for s, q in state["holdings"].items())
    state["history"].append({
        "date": today,
        "equity": round(equity, 2),
        "cash": round(state["cash"], 2),
        "holdings": {s: round(q, 8) for s, q in state["holdings"].items()},
        "target": picks,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    state["last_run"] = today
    save_state(state)

    ret = (equity / BUDGET - 1) * 100
    print(f"\nEquity: ${equity:.2f} ({ret:+.2f}% desde inicio) | cash ${state['cash']:.2f} | "
          f"posiciones: {sorted(held(state)) or 'ninguna (100% cash)'}")


if __name__ == "__main__":
    main()
