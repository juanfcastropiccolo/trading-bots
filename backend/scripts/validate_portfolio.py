"""Validación ampliada: rsi_meanrev (RSI-14 y RSI-2 estilo Connors) con
parámetros fijos sobre 6 símbolos × 2 timeframes, período completo y OOS 30%.

Además simula un portfolio equiponderado (1/N del capital por símbolo) para
estimar qué rendiría el conjunto con $100.
"""
import numpy as np
import pandas as pd

from research import fetch_history, sig_rsi_mr, simulate, BARS_PER_YEAR, COST_PER_SIDE

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]
DATASETS = [("15m", 120), ("1h", 365)]

VARIANTS = {
    "rsi14_30_55": dict(lo=30, hi=55, regime=200, rsi_w=14),
    "rsi14_35_60": dict(lo=35, hi=60, regime=200, rsi_w=14),
    "rsi2_10_70": dict(lo=10, hi=70, regime=200, rsi_w=2),
    "rsi2_15_80": dict(lo=15, hi=80, regime=200, rsi_w=2),
}


def strat_returns(df: pd.DataFrame, params: dict) -> pd.Series:
    pos = sig_rsi_mr(df, **params).shift(1).fillna(0)
    ret = df["close"].pct_change().fillna(0)
    switches = pos.diff().abs().fillna(pos.iloc[0])
    return pos * ret - switches * COST_PER_SIDE


def main():
    for tf, days in DATASETS:
        data = {}
        for s in SYMBOLS:
            try:
                data[s] = fetch_history("binance", s, tf, days)
            except Exception as e:
                print(f"{s} {tf}: descarga falló ({e})")
        print(f"\n================ timeframe {tf} ({days}d) ================")

        for vname, params in VARIANTS.items():
            oos_rets, oos_trades_total, pos_count = [], 0, 0
            port_oos_curves = []
            for s, df in data.items():
                split = int(len(df) * 0.7)
                df_oos = df.iloc[split:].reset_index(drop=True)
                m = simulate(df_oos, sig_rsi_mr(df_oos, **params), BARS_PER_YEAR[tf])
                oos_rets.append(m.ret_pct)
                oos_trades_total += m.trades
                pos_count += m.ret_pct > 0
                port_oos_curves.append(strat_returns(df_oos, params).reset_index(drop=True))

            # portfolio equiponderado OOS
            aligned = pd.concat(port_oos_curves, axis=1).fillna(0)
            port_ret = aligned.mean(axis=1)
            port_equity = (1 + port_ret).cumprod()
            peak = port_equity.cummax()
            port_dd = ((peak - port_equity) / peak).max() * 100
            std = port_ret.std()
            port_sharpe = port_ret.mean() / std * np.sqrt(BARS_PER_YEAR[tf]) if std > 0 else 0
            oos_days = days * 0.3

            print(f"  {vname:14s} OOS por símbolo: mediana={np.median(oos_rets):+5.2f}% "
                  f"positivos={pos_count}/{len(oos_rets)} trades_tot={oos_trades_total:3d} | "
                  f"PORTFOLIO OOS ({oos_days:.0f}d): ret={(port_equity.iloc[-1]-1)*100:+5.2f}% "
                  f"maxDD={port_dd:4.2f}% sharpe={port_sharpe:+4.2f}")


if __name__ == "__main__":
    main()
