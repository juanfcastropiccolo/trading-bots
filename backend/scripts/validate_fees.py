"""Sensibilidad a comisiones: la misma validación 4-fold de rsi_meanrev 15m
bajo tres escenarios de costo por lado:
  - taker Binance base: 0.10% + 0.05% slippage = 0.15%
  - taker con descuento BNB: 0.075% + 0.05% = 0.125%
  - maker con descuento (orden límite, sin slippage): 0.075%
"""
import numpy as np
import pandas as pd

import research
from research import fetch_history, sig_rsi_mr
from validate_portfolio import SYMBOLS

N_FOLDS = 4
PARAMS = dict(lo=30, hi=55, regime=200, rsi_w=14)
SCENARIOS = {
    "taker_base_0.150%": 0.0015,
    "taker_bnb_0.125%": 0.00125,
    "maker_bnb_0.075%": 0.00075,
}


def strat_returns(df, params, cost):
    pos = sig_rsi_mr(df, **params).shift(1).fillna(0)
    ret = df["close"].pct_change().fillna(0)
    switches = pos.diff().abs().fillna(pos.iloc[0])
    return pos * ret - switches * cost


def main():
    data = {s: fetch_history("binance", s, "15m", 360) for s in SYMBOLS}
    n = min(len(df) for df in data.values())
    edges = [int(n * i / N_FOLDS) for i in range(N_FOLDS + 1)]

    for sname, cost in SCENARIOS.items():
        rets = []
        for k in range(N_FOLDS):
            a, b = edges[k], edges[k + 1]
            curves = []
            for s, df in data.items():
                dfk = df.iloc[-n:].reset_index(drop=True).iloc[a:b].reset_index(drop=True)
                curves.append(strat_returns(dfk, PARAMS, cost).reset_index(drop=True))
            port = pd.concat(curves, axis=1).fillna(0).mean(axis=1)
            rets.append(((1 + port).cumprod().iloc[-1] - 1) * 100)
        pos = sum(r > 0 for r in rets)
        print(f"{sname}: folds={['%+.2f%%' % r for r in rets]} → positivos {pos}/4, media {np.mean(rets):+.2f}%/90d")


if __name__ == "__main__":
    main()
