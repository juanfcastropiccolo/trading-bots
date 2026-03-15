import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


def calculate_features(df: pd.DataFrame) -> dict | None:
    if len(df) < 30:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]

    ema_fast = EMAIndicator(close=close, window=9).ema_indicator().iloc[-1]
    ema_slow = EMAIndicator(close=close, window=21).ema_indicator().iloc[-1]
    rsi = RSIIndicator(close=close, window=14).rsi().iloc[-1]
    atr = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1]

    return {
        "ema_fast": round(ema_fast, 2),
        "ema_slow": round(ema_slow, 2),
        "rsi": round(rsi, 2),
        "atr": round(atr, 2),
        "close": round(close.iloc[-1], 2),
    }
