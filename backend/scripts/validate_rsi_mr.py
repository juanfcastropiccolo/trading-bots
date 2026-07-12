"""Validación de robustez de rsi_meanrev: parámetros FIJOS (sin optimizar)
evaluados en todos los datasets, período completo y último 30%.

Si la mayoría de los combos vecinos son positivos en la mayoría de los
datasets, la señal es robusta. Si solo brilla un combo aislado, es ruido.
"""
import itertools
import numpy as np
import pandas as pd

from research import fetch_history, sig_rsi_mr, simulate, BARS_PER_YEAR

DATASETS = [
    ("BTC/USDT", "15m", 120),
    ("BTC/USDT", "1h", 365),
    ("BTC/USDT", "4h", 730),
    ("ETH/USDT", "15m", 120),
    ("ETH/USDT", "1h", 365),
    ("ETH/USDT", "4h", 730),
]

GRID = {
    "lo": [25, 30, 35],
    "hi": [50, 55, 60],
    "regime": [200],
}


def main():
    combos = [dict(zip(GRID.keys(), c)) for c in itertools.product(*GRID.values())]
    rows = []
    data = {(s, tf): fetch_history("binance", s, tf, d) for s, tf, d in DATASETS}

    for params in combos:
        oos_rets, full_rets, oos_pos, n_sets = [], [], 0, 0
        for (symbol, tf, days) in DATASETS:
            df = data[(symbol, tf)]
            bpy = BARS_PER_YEAR[tf]
            split = int(len(df) * 0.7)
            df_oos = df.iloc[split:].reset_index(drop=True)

            m_full = simulate(df, sig_rsi_mr(df, **params), bpy)
            m_oos = simulate(df_oos, sig_rsi_mr(df_oos, **params), bpy)
            full_rets.append(m_full.ret_pct)
            oos_rets.append(m_oos.ret_pct)
            oos_pos += m_oos.ret_pct > 0
            n_sets += 1
            rows.append({
                "lo": params["lo"], "hi": params["hi"],
                "dataset": f"{symbol} {tf}",
                "full_ret": round(m_full.ret_pct, 2),
                "full_trades": m_full.trades,
                "oos_ret": round(m_oos.ret_pct, 2),
                "oos_trades": m_oos.trades,
                "oos_dd": round(m_oos.max_dd_pct, 2),
            })
        print(f"lo={params['lo']} hi={params['hi']}: "
              f"OOS mediana={np.median(oos_rets):+.2f}%  media={np.mean(oos_rets):+.2f}%  "
              f"positivos={oos_pos}/{n_sets}  |  "
              f"FULL mediana={np.median(full_rets):+.2f}%")

    print("\nDetalle por dataset (combo lo=30 hi=55):")
    det = pd.DataFrame([r for r in rows if r["lo"] == 30 and r["hi"] == 55])
    print(det.to_string(index=False))


if __name__ == "__main__":
    main()
