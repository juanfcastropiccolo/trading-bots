"""Rotación por momentum cross-sectional (diario, long-only, spot).

Regla: cada `rebal_days` días se rankean los símbolos por retorno de
`lookback` días. Se mantiene el top-K en partes iguales, pero solo los que
cotizan por encima de su SMA `trend_w`; el resto queda en cash (USDT).

Validación: 3 años de velas 1d, 4 folds secuenciales de ~9 meses, parámetros
fijos (sin optimización por fold). Costos: 0.15% por lado (taker base).
"""
import numpy as np
import pandas as pd

from research import fetch_history

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
]
COST = 0.0015
N_FOLDS = 4

VARIANTS = {
    "top1_lb30_reb7": dict(top_k=1, lookback=30, rebal_days=7, trend_w=100),
    "top2_lb30_reb7": dict(top_k=2, lookback=30, rebal_days=7, trend_w=100),
    "top2_lb90_reb7": dict(top_k=2, lookback=90, rebal_days=7, trend_w=100),
    "top2_lb30_reb7_sinfiltro": dict(top_k=2, lookback=30, rebal_days=7, trend_w=0),
}


def build_closes() -> pd.DataFrame:
    closes = {}
    for s in SYMBOLS:
        df = fetch_history("binance", s, "1d", 1095)
        closes[s] = df.set_index("timestamp")["close"]
    px = pd.DataFrame(closes).dropna()
    return px


def run(px: pd.DataFrame, top_k: int, lookback: int, rebal_days: int, trend_w: int):
    """Devuelve la serie diaria de retornos del portfolio."""
    mom = px.pct_change(lookback)
    trend_ok = px > px.rolling(trend_w).mean() if trend_w else px.notna()
    ret = px.pct_change().fillna(0)

    weights = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    current = pd.Series(0.0, index=px.columns)
    for i, ts in enumerate(px.index):
        if i % rebal_days == 0 and i >= max(lookback, trend_w or 1):
            ranked = mom.iloc[i].dropna().sort_values(ascending=False)
            picks = [s for s in ranked.index[:top_k] if trend_ok.iloc[i][s]]
            current = pd.Series(0.0, index=px.columns)
            for s in picks:
                current[s] = 1.0 / top_k
        weights.iloc[i] = current

    w_prev = weights.shift(1).fillna(0)
    turnover = (weights - w_prev).abs().sum(axis=1)
    port_ret = (w_prev * ret).sum(axis=1) - turnover * COST
    return port_ret


def metrics(port_ret: pd.Series) -> str:
    eq = (1 + port_ret).cumprod()
    peak = eq.cummax()
    dd = ((peak - eq) / peak).max() * 100
    std = port_ret.std()
    sharpe = port_ret.mean() / std * np.sqrt(365) if std > 0 else 0
    return f"ret={(eq.iloc[-1]-1)*100:+7.2f}%  maxDD={dd:5.2f}%  sharpe={sharpe:+5.2f}"


def main():
    px = build_closes()
    print(f"Matriz de precios: {px.shape[0]} días × {px.shape[1]} símbolos "
          f"({px.index[0].date()} → {px.index[-1].date()})")
    bh = px.pct_change().fillna(0).mean(axis=1)

    edges = [int(len(px) * i / N_FOLDS) for i in range(N_FOLDS + 1)]
    for vname, params in VARIANTS.items():
        full = run(px, **params)
        print(f"\n=== {vname} ===")
        print(f"  período completo: {metrics(full)}   [b&h equiponderado: {metrics(bh)}]")
        pos = 0
        for k in range(N_FOLDS):
            a, b = edges[k], edges[k + 1]
            seg = run(px.iloc[a:b], **params)
            bh_seg = bh.iloc[a:b]
            r = ((1 + seg).cumprod().iloc[-1] - 1) * 100
            rb = ((1 + bh_seg).cumprod().iloc[-1] - 1) * 100
            pos += r > 0
            print(f"  fold {k+1} (~9m): portfolio={r:+7.2f}%  b&h={rb:+7.2f}%")
        print(f"  → folds positivos: {pos}/{N_FOLDS}")


if __name__ == "__main__":
    main()
