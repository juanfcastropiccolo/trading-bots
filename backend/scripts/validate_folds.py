"""Test decisivo: rsi_meanrev 15m con parámetros fijos sobre 360 días
divididos en 4 folds secuenciales de ~90 días, portfolio de 6 símbolos.

Ningún fold participa en optimización: todos son out-of-sample puros.
"""
import numpy as np
import pandas as pd

from research import fetch_history, sig_rsi_mr, simulate, BARS_PER_YEAR
from validate_portfolio import strat_returns, SYMBOLS

N_FOLDS = 4
VARIANTS = {
    "rsi14_30_55": dict(lo=30, hi=55, regime=200, rsi_w=14),
    "rsi14_35_60": dict(lo=35, hi=60, regime=200, rsi_w=14),
}


def main():
    data = {}
    for s in SYMBOLS:
        df = fetch_history("binance", s, "15m", 360)
        data[s] = df
        print(f"{s}: {len(df)} velas 15m")

    n = min(len(df) for df in data.values())
    fold_edges = [int(n * i / N_FOLDS) for i in range(N_FOLDS + 1)]

    for vname, params in VARIANTS.items():
        print(f"\n=== {vname} (params fijos, regime=EMA200) ===")
        fold_results = []
        for k in range(N_FOLDS):
            a, b = fold_edges[k], fold_edges[k + 1]
            curves, bh, trades = [], [], 0
            for s, df in data.items():
                dfk = df.iloc[-n:].reset_index(drop=True).iloc[a:b].reset_index(drop=True)
                curves.append(strat_returns(dfk, params).reset_index(drop=True))
                bh.append((dfk["close"].iloc[-1] / dfk["close"].iloc[0] - 1) * 100)
                trades += simulate(dfk, sig_rsi_mr(dfk, **params), BARS_PER_YEAR["15m"]).trades
            port_ret = pd.concat(curves, axis=1).fillna(0).mean(axis=1)
            eq = (1 + port_ret).cumprod()
            peak = eq.cummax()
            dd = ((peak - eq) / peak).max() * 100
            std = port_ret.std()
            sharpe = port_ret.mean() / std * np.sqrt(BARS_PER_YEAR["15m"]) if std > 0 else 0
            ret = (eq.iloc[-1] - 1) * 100
            fold_results.append(ret)
            print(f"  fold {k+1} (~90d): portfolio={ret:+6.2f}%  b&h_medio={np.mean(bh):+7.2f}%  "
                  f"maxDD={dd:4.2f}%  sharpe={sharpe:+5.2f}  trades={trades}")
        pos = sum(r > 0 for r in fold_results)
        print(f"  → folds positivos: {pos}/{N_FOLDS}, retorno medio por fold: {np.mean(fold_results):+.2f}%")


if __name__ == "__main__":
    main()
