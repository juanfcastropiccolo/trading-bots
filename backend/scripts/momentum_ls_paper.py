"""Paper trading diario de momentum long/short sobre perpetuos USDT-M.

Dos estrategias en paralelo, $100 simulados cada una (Fase 3 de PLAN_FUTUROS.md):
  - v4_voltarget: gate de régimen (BTC>SMA-200 → top-2 long sobre SMA-100;
    bear → short BTC/ETH a media máquina si bajo SMA-100 y mom<0) + vol
    targeting 50% anualizado. ÚNICA config que pasó los criterios ex-ante.
  - v4_ensemble: mismo gate, momentum ensemble 15/30/60/90d, sin voltarget.
    EXPERIMENTO SECUNDARIO: falló el criterio (c) (pata short break-even).
    La decisión de pasar a real usa los criterios de VALIDACION_LS.md, no
    el retorno de este paper.

Mecánica idéntica al backtest (validate_ls_momentum.py): pesos decididos al
cierre del día d aplicados al retorno del día d+1, rebalanceo semanal anclado
(lunes UTC), funding real como PnL diario, costos 0.05% por lado. Procesa
todos los días pendientes desde el último tick (robusto a corridas perdidas).

Datos: ccxt sobre perps lineales (PERP_EXCHANGE_ID, default "bybit,okx" —
accesibles desde EE.UU.; Binance geo-bloquea).

Uso:  python scripts/momentum_ls_paper.py [--check]
"""
import argparse
import json
import math
import os
from datetime import date, datetime, timedelta, timezone

import ccxt
import numpy as np
import pandas as pd

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
]
BTC = "BTC/USDT"
SHORTABLE = ["BTC/USDT", "ETH/USDT"]
COST = 0.0005
BUDGET = 100.0
LOOKBACK, TREND_W, REGIME_W = 30, 100, 200
ENSEMBLE_LBS = [15, 30, 60, 90]
VOL_TARGET_ANN = 0.50
REBAL_ANCHOR = date(2026, 7, 20)  # lunes: fase del rebalanceo semanal
HISTORY_DAYS = 320                # REGIME_W + margen

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "momentum_ls_state.json")
EXCHANGE_IDS = os.environ.get("PERP_EXCHANGE_ID", "bybit,okx").split(",")

STRATEGIES = ["v4_voltarget", "v4_ensemble"]


# ---------------------------------------------------------------- datos

def _perp(sym: str) -> str:
    return f"{sym}:USDT"


def fetch_data() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Matrices diarias (close, funding) de los últimos HISTORY_DAYS días
    completos UTC. Excluye la vela del día en curso (incompleta)."""
    last_err = None
    for exid in [e.strip() for e in EXCHANGE_IDS if e.strip()]:
        try:
            ex = getattr(ccxt, exid)({"enableRateLimit": True})
            today = datetime.now(timezone.utc).date()
            closes, fundings = {}, {}
            since_f = int((datetime.now(timezone.utc) - timedelta(days=50)).timestamp() * 1000)
            for s in SYMBOLS:
                candles = ex.fetch_ohlcv(_perp(s), timeframe="1d", limit=HISTORY_DAYS + 2)
                ser = pd.Series({datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).date(): c[4]
                                 for c in candles})
                closes[s] = ser[ser.index < today]

                rates = ex.fetch_funding_rate_history(_perp(s), since=since_f, limit=200)
                fs = pd.Series(dtype=float)
                if rates:
                    fr = pd.DataFrame(rates)
                    day = fr["timestamp"].apply(
                        lambda t: datetime.fromtimestamp(t / 1000, tz=timezone.utc).date())
                    fs = fr["fundingRate"].astype(float).groupby(day).sum()
                fundings[s] = fs
            px = pd.DataFrame(closes).dropna()
            fund = pd.DataFrame(fundings).reindex(px.index).fillna(0.0)
            if len(px) < REGIME_W + 10:
                raise RuntimeError(f"historia insuficiente: {len(px)} días")
            return px, fund, exid
        except Exception as e:
            last_err = e
            print(f"⚠️  {exid} falló ({type(e).__name__}: {str(e)[:100]}); pruebo el siguiente…")
    raise SystemExit(f"Ningún exchange de perps disponible de {EXCHANGE_IDS}: {last_err}")


# ---------------------------------------------------------------- señales

def target_weights(px: pd.DataFrame, strategy: str) -> dict:
    """Pesos objetivo con signo, decididos al cierre de la última fila de px.
    Réplica exacta de make_weights() de validate_ls_momentum.py."""
    use_ensemble = strategy == "v4_ensemble"
    use_voltarget = strategy == "v4_voltarget"

    if use_ensemble:
        score = sum(px.pct_change(lb).iloc[-1] for lb in ENSEMBLE_LBS) / len(ENSEMBLE_LBS)
    else:
        score = px.pct_change(LOOKBACK).iloc[-1]
    above = px.iloc[-1] > px.rolling(TREND_W).mean().iloc[-1]
    bull = px[BTC].iloc[-1] > px[BTC].rolling(REGIME_W).mean().iloc[-1]

    w = {s: 0.0 for s in px.columns}
    if bull:
        ranked = score.dropna().sort_values(ascending=False)
        for s in [s for s in ranked.index[:2] if above[s]]:
            w[s] = 0.5
    else:
        for s in SHORTABLE:
            if not above[s] and score.get(s, 0) < 0:
                w[s] = -0.25

    if use_voltarget:
        vol_ann = px.pct_change().rolling(30).std().iloc[-1] * np.sqrt(365)
        for s in w:
            if w[s] and not math.isnan(vol_ann[s]) and vol_ann[s] > 0:
                w[s] *= min(1.0, VOL_TARGET_ANN / vol_ann[s])
    return {s: round(v, 6) for s, v in w.items() if v != 0.0}


# ---------------------------------------------------------------- estado

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_run": None,
            "strategies": {n: {"equity": BUDGET, "weights": {}, "history": []}
                           for n in STRATEGIES}}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------- tick

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="mostrar señales del día sin modificar el estado")
    args = ap.parse_args()

    px, fund, exid = fetch_data()
    last_close = px.index[-1]
    print(f"=== Momentum L/S perps — datos hasta {last_close} ({exid}) ===")
    bull = px[BTC].iloc[-1] > px[BTC].rolling(REGIME_W).mean().iloc[-1]
    print(f"Régimen: {'BULL (longs habilitados)' if bull else 'BEAR (solo shorts BTC/ETH o cash)'}")
    for name in STRATEGIES:
        print(f"  {name:13s} target hoy: {target_weights(px, name) or 'cash'}")

    if args.check:
        return

    state = load_state()
    if state["last_run"] is None:
        # bootstrap: pesos iniciales al cierre más reciente, sin PnL
        for name in STRATEGIES:
            st = state["strategies"][name]
            st["weights"] = target_weights(px, name)
            st["history"].append({"date": last_close.isoformat(), "equity": st["equity"],
                                  "weights": st["weights"],
                                  "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        state["last_run"] = last_close.isoformat()
        save_state(state)
        print(f"\nBootstrap {last_close}: ambas estrategias arrancan con ${BUDGET:.2f}")
        return

    last_run = date.fromisoformat(state["last_run"])
    pending = [d for d in px.index if d > last_run]
    if not pending:
        print(f"\nYa corrió hasta {last_run}; sin días pendientes.")
        return

    for d in pending:
        pos = list(px.index).index(d)
        ret_d = px.iloc[pos] / px.iloc[pos - 1] - 1
        fund_d = fund.iloc[pos]
        px_upto = px.iloc[: pos + 1]
        rebal = (d - REBAL_ANCHOR).days % 7 == 0
        for name in STRATEGIES:
            st = state["strategies"][name]
            w_prev = st["weights"]
            price_pnl = sum(w * ret_d[s] for s, w in w_prev.items())
            funding_pnl = -sum(w * fund_d[s] for s, w in w_prev.items())
            w_new = target_weights(px_upto, name) if rebal else w_prev
            turnover = sum(abs(w_new.get(s, 0) - w_prev.get(s, 0))
                           for s in set(w_new) | set(w_prev))
            st["equity"] = round(st["equity"] * (1 + price_pnl + funding_pnl - turnover * COST), 4)
            st["weights"] = w_new
            st["history"].append({"date": d.isoformat(), "equity": st["equity"],
                                  "weights": w_new,
                                  "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    state["last_run"] = last_close.isoformat()
    save_state(state)

    print(f"\nProcesados {len(pending)} día(s) hasta {last_close}:")
    for name in STRATEGIES:
        st = state["strategies"][name]
        ret_total = (st["equity"] / BUDGET - 1) * 100
        print(f"  {name:13s} equity ${st['equity']:.2f} ({ret_total:+.2f}%) "
              f"posiciones: {st['weights'] or 'cash'}")


if __name__ == "__main__":
    main()
