"""Framework de investigación de estrategias con validación out-of-sample.

Para cada estrategia: optimiza parámetros en el 70% inicial de la historia
(in-sample) y evalúa el mejor set en el 30% final (out-of-sample), con los
mismos costos que execution_engine (fee 0.1% + slippage 0.05% por lado).

Incluye un modelo ML entrenable (GradientBoosting) con features técnicos.

Uso:
    python scripts/research.py                # barrido completo
    python scripts/research.py --quick        # solo 1h para iterar rápido
"""
import argparse
import itertools
import os
from dataclasses import dataclass

import ccxt
import numpy as np
import pandas as pd

COST_PER_SIDE = 0.0015  # 0.1% fee + 0.05% slippage
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")


# ---------------------------------------------------------------- data

def fetch_history(exchange_id: str, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = f"{exchange_id}_{symbol.replace('/', '-')}_{timeframe}_{days}d.csv"
    path = os.path.join(CACHE_DIR, key)
    if os.path.exists(path):
        df = pd.read_csv(path, parse_dates=["timestamp"])
        return df

    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    since = ex.milliseconds() - days * 86_400_000
    candles = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        candles.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    df.to_csv(path, index=False)
    return df


# ---------------------------------------------------------------- indicadores

def ema(s: pd.Series, w: int) -> pd.Series:
    return s.ewm(span=w, adjust=False).mean()


def rsi(close: pd.Series, w: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / w, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / w, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, w: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / w, adjust=False).mean()


# ---------------------------------------------------------------- motor vectorizado

@dataclass
class Metrics:
    ret_pct: float
    bh_pct: float
    trades: int
    win_rate: float
    max_dd_pct: float
    sharpe: float
    bars: int

    def row(self) -> str:
        return (f"ret={self.ret_pct:+7.2f}%  b&h={self.bh_pct:+7.2f}%  "
                f"trades={self.trades:4d}  wr={self.win_rate:5.1f}%  "
                f"maxDD={self.max_dd_pct:5.2f}%  sharpe={self.sharpe:+5.2f}")


def simulate(df: pd.DataFrame, position: pd.Series, bars_per_year: float) -> Metrics:
    """position: serie 0/1 decidida al cierre de cada vela; se ejecuta en la
    vela siguiente (shift 1) para no mirar el futuro."""
    pos = position.shift(1).fillna(0)
    ret = df["close"].pct_change().fillna(0)
    switches = pos.diff().abs().fillna(pos.iloc[0])
    strat_ret = pos * ret - switches * COST_PER_SIDE
    equity = (1 + strat_ret).cumprod()

    peak = equity.cummax()
    max_dd = ((peak - equity) / peak).max() * 100

    # trades: cada entrada (0->1)
    entries = ((pos.diff() == 1)).sum()
    # win rate por trade
    wins = losses = 0
    in_pos = False
    entry_eq = 1.0
    for p, eq in zip(pos.values, equity.values):
        if p == 1 and not in_pos:
            in_pos, entry_eq = True, eq
        elif p == 0 and in_pos:
            in_pos = False
            wins += eq >= entry_eq
            losses += eq < entry_eq
    closed = wins + losses
    std = strat_ret.std()
    sharpe = (strat_ret.mean() / std * np.sqrt(bars_per_year)) if std > 0 else 0.0
    return Metrics(
        ret_pct=(equity.iloc[-1] - 1) * 100,
        bh_pct=(df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100,
        trades=int(entries),
        win_rate=wins / closed * 100 if closed else 0.0,
        max_dd_pct=max_dd,
        sharpe=sharpe,
        bars=len(df),
    )


BARS_PER_YEAR = {"15m": 365 * 96, "1h": 365 * 24, "4h": 365 * 6}


# ---------------------------------------------------------------- estrategias (reglas)

def sig_trend(df, fast=9, slow=21, regime=0):
    """EMA cross; con regime>0 solo opera si close > EMA(regime)."""
    f, s = ema(df["close"], fast), ema(df["close"], slow)
    pos = (f > s).astype(int)
    if regime:
        pos &= (df["close"] > ema(df["close"], regime)).astype(int)
    return pos


def sig_rsi_mr(df, lo=30, hi=55, regime=200, rsi_w=14):
    """Mean reversion: entra RSI<lo, sale RSI>hi. Solo long, filtro de régimen."""
    r = rsi(df["close"], rsi_w)
    pos = pd.Series(0, index=df.index)
    holding = False
    reg = df["close"] > ema(df["close"], regime) if regime else pd.Series(True, index=df.index)
    r_vals, reg_vals = r.values, reg.values
    out = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if not holding and r_vals[i] < lo and reg_vals[i]:
            holding = True
        elif holding and r_vals[i] > hi:
            holding = False
        out[i] = holding
    return pd.Series(out, index=df.index)


def sig_donchian(df, entry_n=40, exit_n=20, regime=0):
    """Breakout: entra en máximo de entry_n velas, sale en mínimo de exit_n."""
    upper = df["high"].rolling(entry_n).max().shift(1)
    lower = df["low"].rolling(exit_n).min().shift(1)
    reg = df["close"] > ema(df["close"], regime) if regime else pd.Series(True, index=df.index)
    out = np.zeros(len(df), dtype=int)
    holding = False
    for i in range(len(df)):
        if not holding and df["close"].iloc[i] > (upper.iloc[i] or np.inf) and reg.iloc[i]:
            holding = True
        elif holding and df["close"].iloc[i] < (lower.iloc[i] or -np.inf):
            holding = False
        out[i] = holding
    return pd.Series(out, index=df.index)


def sig_bollinger(df, w=20, k=2.0, regime=200):
    """Compra bajo banda inferior, sale en la media."""
    mid = df["close"].rolling(w).mean()
    std = df["close"].rolling(w).std()
    lower = mid - k * std
    reg = df["close"] > ema(df["close"], regime) if regime else pd.Series(True, index=df.index)
    out = np.zeros(len(df), dtype=int)
    holding = False
    for i in range(len(df)):
        if not holding and df["close"].iloc[i] < (lower.iloc[i] or -np.inf) and reg.iloc[i]:
            holding = True
        elif holding and df["close"].iloc[i] > (mid.iloc[i] or np.inf):
            holding = False
        out[i] = holding
    return pd.Series(out, index=df.index)


STRATEGIES = {
    "trend_ema": (sig_trend, {
        "fast": [9, 12, 20], "slow": [21, 50], "regime": [0, 200],
    }),
    "rsi_meanrev": (sig_rsi_mr, {
        "lo": [25, 30, 35], "hi": [50, 55, 65], "regime": [0, 200],
    }),
    "donchian": (sig_donchian, {
        "entry_n": [20, 40, 55], "exit_n": [10, 20], "regime": [0, 200],
    }),
    "bollinger": (sig_bollinger, {
        "w": [20], "k": [2.0, 2.5], "regime": [0, 200],
    }),
}


# ---------------------------------------------------------------- ML

def ml_features(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    c = df["close"]
    for lag in [1, 2, 4, 8, 24]:
        X[f"ret_{lag}"] = c.pct_change(lag)
    X["rsi"] = rsi(c) / 100
    X["ema_ratio_9_21"] = ema(c, 9) / ema(c, 21) - 1
    X["ema_ratio_21_50"] = ema(c, 21) / ema(c, 50) - 1
    X["dist_ema200"] = c / ema(c, 200) - 1
    X["atr_norm"] = atr(df) / c
    X["vol_z"] = (df["volume"] - df["volume"].rolling(48).mean()) / df["volume"].rolling(48).std()
    X["hl_range"] = (df["high"] - df["low"]) / c
    return X


def run_ml(df: pd.DataFrame, timeframe: str, horizon: int = 4, thresh: float = 0.55):
    from sklearn.ensemble import GradientBoostingClassifier

    X = ml_features(df)
    fwd_ret = df["close"].shift(-horizon) / df["close"] - 1
    y = (fwd_ret > 2 * COST_PER_SIDE).astype(int)  # sube más que el costo round-trip

    valid = X.dropna().index.intersection(y.dropna().index)
    X, y = X.loc[valid], y.loc[valid]
    dfv = df.loc[valid].reset_index(drop=True)
    X, y = X.reset_index(drop=True), y.reset_index(drop=True)

    split = int(len(X) * 0.7)
    model = GradientBoostingClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=42
    )
    model.fit(X.iloc[:split], y.iloc[:split])

    proba_is = pd.Series(model.predict_proba(X.iloc[:split])[:, 1])
    proba_oos = pd.Series(model.predict_proba(X.iloc[split:])[:, 1]).reset_index(drop=True)

    pos_is = (proba_is > thresh).astype(int)
    pos_oos = (proba_oos > thresh).astype(int)

    m_is = simulate(dfv.iloc[:split].reset_index(drop=True), pos_is, BARS_PER_YEAR[timeframe])
    m_oos = simulate(dfv.iloc[split:].reset_index(drop=True), pos_oos, BARS_PER_YEAR[timeframe])
    importances = sorted(zip(X.columns, model.feature_importances_), key=lambda t: -t[1])[:5]
    return m_is, m_oos, importances


# ---------------------------------------------------------------- walk-forward reglas

def optimize_and_validate(df: pd.DataFrame, timeframe: str, name: str, fn, grid: dict):
    split = int(len(df) * 0.7)
    df_is = df.iloc[:split].reset_index(drop=True)
    df_oos = df.iloc[split:].reset_index(drop=True)
    bpy = BARS_PER_YEAR[timeframe]

    best, best_params, best_metric = None, None, -np.inf
    for combo in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), combo))
        m = simulate(df_is, fn(df_is, **params), bpy)
        if m.trades >= 5 and m.sharpe > best_metric:
            best, best_params, best_metric = m, params, m.sharpe
    if best is None:
        return None

    m_oos = simulate(df_oos, fn(df_oos, **best_params), bpy)
    return best_params, best, m_oos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    datasets = [("1h", 365)] if args.quick else [("15m", 120), ("1h", 365), ("4h", 730)]
    symbols = ["BTC/USDT", "ETH/USDT"]

    for symbol in symbols:
        for timeframe, days in datasets:
            df = fetch_history(args.exchange, symbol, timeframe, days)
            print(f"\n=== {symbol} {timeframe} ({days}d, {len(df)} velas) — split 70/30 ===")
            for name, (fn, grid) in STRATEGIES.items():
                res = optimize_and_validate(df, timeframe, name, fn, grid)
                if res is None:
                    print(f"  {name:12s} sin combinación válida (mín. 5 trades IS)")
                    continue
                params, m_is, m_oos = res
                print(f"  {name:12s} params={params}")
                print(f"     IS : {m_is.row()}")
                print(f"     OOS: {m_oos.row()}")
            try:
                m_is, m_oos, imp = run_ml(df, timeframe)
                print(f"  {'ml_gboost':12s} horizon=4 thresh=0.55")
                print(f"     IS : {m_is.row()}")
                print(f"     OOS: {m_oos.row()}")
                print(f"     top features: {[(f, round(w, 3)) for f, w in imp]}")
            except Exception as e:
                print(f"  ml_gboost falló: {e}")


if __name__ == "__main__":
    main()
