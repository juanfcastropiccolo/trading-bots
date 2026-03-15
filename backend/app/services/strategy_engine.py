def evaluate_trend_following(
    features: dict, prev_features: dict | None
) -> dict:
    if prev_features is None:
        return {
            "direction": "HOLD",
            "confidence": 0.0,
            "reason": "No previous features available for crossover detection",
        }

    ema_fast = features["ema_fast"]
    ema_slow = features["ema_slow"]
    rsi = features["rsi"]
    prev_ema_fast = prev_features["ema_fast"]
    prev_ema_slow = prev_features["ema_slow"]

    # Bullish crossover: EMA-9 crosses above EMA-21
    bullish_cross = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow
    # Bearish crossover: EMA-9 crosses below EMA-21
    bearish_cross = prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow

    if bullish_cross and rsi < 70:
        spread = abs(ema_fast - ema_slow) / ema_slow * 100
        confidence = min(0.9, 0.5 + spread * 10)
        return {
            "direction": "BUY",
            "confidence": round(confidence, 2),
            "reason": f"Bullish EMA crossover (9>{21}) with RSI={rsi:.1f} (<70). Spread={spread:.4f}%",
        }
    elif bearish_cross and rsi > 30:
        spread = abs(ema_fast - ema_slow) / ema_slow * 100
        confidence = min(0.9, 0.5 + spread * 10)
        return {
            "direction": "SELL",
            "confidence": round(confidence, 2),
            "reason": f"Bearish EMA crossover (9<21) with RSI={rsi:.1f} (>30). Spread={spread:.4f}%",
        }
    else:
        return {
            "direction": "HOLD",
            "confidence": 0.0,
            "reason": f"No crossover. EMA9={ema_fast}, EMA21={ema_slow}, RSI={rsi:.1f}",
        }
