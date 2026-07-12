"""Paper trading diario de la estrategia de rotación por momentum.

Regla (validada en scripts/validate_momentum.py):
  - Universo: 10 majors spot USDT.
  - Cada día se rankea por retorno de 30 días.
  - Target: top-2 en partes iguales, solo si cotizan sobre su SMA-100.
  - Rebalanceo efectivo solo si el target cambió (cadencia natural ~semanal).
  - Costos simulados: 0.15% por lado.

Estado en backend/data/momentum_state.json. Idempotente por día.

Uso:  python scripts/momentum_paper.py [--force]
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
TOP_K = 2
LOOKBACK = 30
TREND_W = 100
COST = 0.0015
BUDGET = 100.0

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_state.json")


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

    ex = ccxt.binance({"enableRateLimit": True})
    closes, prices = {}, {}
    for s in SYMBOLS:
        candles = ex.fetch_ohlcv(s, timeframe="1d", limit=TREND_W + 5)
        series = [c[4] for c in candles]
        closes[s] = series
        prices[s] = series[-1]

    # ranking por momentum 30d + filtro SMA100
    scores = {}
    for s, series in closes.items():
        if len(series) < TREND_W + 1:
            continue
        mom = series[-1] / series[-1 - LOOKBACK] - 1
        sma = sum(series[-TREND_W:]) / TREND_W
        scores[s] = {"momentum": mom, "above_trend": series[-1] > sma}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1]["momentum"])
    target = [s for s, sc in ranked[:TOP_K] if sc["above_trend"]]

    print(f"=== Momentum rotation — {today} ===")
    print(f"{'símbolo':10s} {'mom30d':>8s}  sobre_SMA100")
    for s, sc in ranked:
        mark = " ← TARGET" if s in target else ""
        print(f"{s:10s} {sc['momentum']*100:+7.2f}%  {str(sc['above_trend']):5s}{mark}")

    if args.check:
        current = set(state["holdings"].keys())
        if set(target) != current:
            print(f"\n⚠️  SEÑAL: target cambiaría de {sorted(current) or ['cash']} "
                  f"a {sorted(target) or ['cash']} (se aplica en el tick diario)")
        else:
            print(f"\nSin señales nuevas: target sigue {sorted(current) or ['cash']}")
        return

    current = set(state["holdings"].keys())
    if set(target) == current:
        print(f"\nSin cambios: mantengo {sorted(current) or ['cash']}")
    else:
        # vender lo que sale
        for s in list(current - set(target)):
            qty = state["holdings"].pop(s)
            proceeds = qty * prices[s] * (1 - COST)
            state["cash"] += proceeds
            print(f"\nSELL {s}: {qty:.6f} @ {prices[s]:.4f} → +${proceeds:.2f}")
        # comprar lo que entra, repartiendo el cash disponible
        entrants = [s for s in target if s not in state["holdings"]]
        if entrants:
            per_slot = state["cash"] / len(entrants) if len(target) <= len(entrants) else \
                state["cash"] * (len(entrants) / TOP_K) / len(entrants)
            for s in entrants:
                spend = min(per_slot, state["cash"])
                qty = spend * (1 - COST) / prices[s]
                state["holdings"][s] = qty
                state["cash"] -= spend
                print(f"BUY  {s}: {qty:.6f} @ {prices[s]:.4f} (${spend:.2f})")

    equity = state["cash"] + sum(q * prices[s] for s, q in state["holdings"].items())
    state["history"].append({
        "date": today,
        "equity": round(equity, 2),
        "cash": round(state["cash"], 2),
        "holdings": {s: round(q, 8) for s, q in state["holdings"].items()},
        "target": target,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    state["last_run"] = today
    save_state(state)

    ret = (equity / BUDGET - 1) * 100
    print(f"\nEquity: ${equity:.2f} ({ret:+.2f}% desde inicio) | cash ${state['cash']:.2f} | "
          f"posiciones: {sorted(state['holdings']) or 'ninguna (100% cash)'}")


if __name__ == "__main__":
    main()
