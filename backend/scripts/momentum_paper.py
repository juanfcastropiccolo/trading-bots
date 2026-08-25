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

# Lista de exchanges separada por comas; se intenta en orden hasta que uno
# devuelva las velas de todos los símbolos (binance geo-bloquea IPs de EE.UU.).
EXCHANGE_IDS = os.environ.get("EXCHANGE_ID", "binance").split(",")


def fetch_closes() -> tuple[dict, dict, str]:
    last_err = None
    for exid in [e.strip() for e in EXCHANGE_IDS if e.strip()]:
        try:
            ex = getattr(ccxt, exid)({"enableRateLimit": True})
            closes = {}
            for s in SYMBOLS:
                candles = ex.fetch_ohlcv(s, timeframe="1d", limit=TREND_W + 5)
                closes[s] = [c[4] for c in candles]
            prices = {s: series[-1] for s, series in closes.items()}
            return closes, prices, exid
        except Exception as e:
            last_err = e
            print(f"⚠️  {exid} falló ({type(e).__name__}: {str(e)[:100]}); pruebo el siguiente…")
    raise SystemExit(f"Ningún exchange disponible de {EXCHANGE_IDS}: {last_err}")


MIN_TRADE = 0.5  # USD; evita operaciones de centavos al ajustar pesos


def held(state: dict) -> dict:
    """Posiciones con cantidad positiva (una clave con qty 0 no es posición)."""
    return {s: q for s, q in state["holdings"].items() if q > 0}


def rebalance(state: dict, target: list, prices: dict) -> list[str]:
    """Lleva el portafolio a pesos iguales 1/TOP_K por pick, como el backtest
    (validate_momentum.py): si solo pasa un pick, la otra mitad queda en cash.

    Solo opera si el conjunto de posiciones difiere del target. Vende primero
    (salidas completas y recortes de las que quedan), después compra. Muta
    `state` y devuelve las líneas de log de las operaciones.
    """
    state["holdings"] = held(state)
    current = set(state["holdings"])
    if set(target) == current:
        return []

    log = []
    equity = state["cash"] + sum(q * prices[s] for s, q in state["holdings"].items())
    slot = equity / TOP_K

    # 1) ventas: lo que sale del target, y exceso de lo que queda
    for s in sorted(current):
        qty = state["holdings"][s]
        if s not in target:
            sell_qty = qty
        else:
            excess = qty * prices[s] - slot
            sell_qty = excess / prices[s] if excess > MIN_TRADE else 0.0
        if sell_qty <= 0:
            continue
        proceeds = sell_qty * prices[s] * (1 - COST)
        state["cash"] += proceeds
        if sell_qty >= qty:
            state["holdings"].pop(s)
            log.append(f"SELL {s}: {qty:.6f} @ {prices[s]:.4f} → +${proceeds:.2f}")
        else:
            state["holdings"][s] = qty - sell_qty
            log.append(f"TRIM {s}: -{sell_qty:.6f} @ {prices[s]:.4f} → +${proceeds:.2f}")

    # 2) compras: entrantes y faltantes de lo que queda, hasta 1 slot cada una
    for s in target:
        have = state["holdings"].get(s, 0.0) * prices[s]
        spend = min(slot - have, state["cash"])
        if spend <= MIN_TRADE:
            continue
        qty = spend * (1 - COST) / prices[s]
        state["holdings"][s] = state["holdings"].get(s, 0.0) + qty
        state["cash"] -= spend
        verb = "BUY " if have == 0 else "ADD "
        log.append(f"{verb} {s}: {qty:.6f} @ {prices[s]:.4f} (${spend:.2f})")

    if not log:
        log.append(f"Sin cambios: mantengo {sorted(current) or ['cash']}")
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

    print(f"=== Momentum rotation — {today} (datos: {exid}) ===")
    print(f"{'símbolo':10s} {'mom30d':>8s}  sobre_SMA100")
    for s, sc in ranked:
        mark = " ← TARGET" if s in target else ""
        print(f"{s:10s} {sc['momentum']*100:+7.2f}%  {str(sc['above_trend']):5s}{mark}")

    if args.check:
        current = set(held(state))
        if set(target) != current:
            print(f"\n⚠️  SEÑAL: target cambiaría de {sorted(current) or ['cash']} "
                  f"a {sorted(target) or ['cash']} (se aplica en el tick diario)")
        else:
            print(f"\nSin señales nuevas: target sigue {sorted(current) or ['cash']}")
        return

    for line in rebalance(state, target, prices):
        print(line)

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
