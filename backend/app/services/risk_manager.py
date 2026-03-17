from datetime import datetime, timedelta


def check_risk(
    signal: dict,
    features: dict | None,
    portfolio: dict,
    agent_config: dict,
    recent_orders: list[dict],
) -> dict:
    checks = {
        "max_trade_ok": True,
        "max_position_ok": True,
        "drawdown_ok": True,
        "daily_loss_ok": True,
        "cooldown_ok": True,
        "consecutive_loss_ok": True,
        "data_complete_ok": True,
    }
    reasons = []

    if signal["direction"] == "HOLD":
        return {
            "approved": False,
            "rejection_reason": "Signal is HOLD, no trade needed",
            **checks,
        }

    # Read configurable thresholds from agent_config
    max_position_pct = agent_config.get("max_position_pct", 0.50)
    drawdown_limit_pct = agent_config.get("drawdown_limit_pct", 0.20)
    daily_loss_limit_pct = agent_config.get("daily_loss_limit_pct", 0.05)
    cooldown_minutes = agent_config.get("cooldown_minutes", 2)
    max_consecutive_losses = agent_config.get("max_consecutive_losses", 3)

    # 1. Data completeness
    if features is None or signal is None:
        checks["data_complete_ok"] = False
        reasons.append("Incomplete data: features or signal missing")

    # 2. Max trade size
    max_trade = agent_config.get("max_trade_usd", 10.0)
    if portfolio["cash"] < max_trade * 0.5:
        checks["max_trade_ok"] = False
        reasons.append(f"Insufficient cash ({portfolio['cash']:.2f}) for min trade")

    # 3. Max position
    budget = agent_config.get("budget_usd", 100.0)
    position_value = portfolio.get("position_value", 0.0)
    if signal["direction"] == "BUY" and position_value > budget * max_position_pct:
        checks["max_position_ok"] = False
        reasons.append(f"Position {position_value:.2f} exceeds {max_position_pct:.0%} of budget")

    # 4. Drawdown limit
    equity = portfolio.get("equity", budget)
    drawdown = (budget - equity) / budget if budget > 0 else 0
    if drawdown >= drawdown_limit_pct:
        checks["drawdown_ok"] = False
        reasons.append(f"Drawdown {drawdown:.1%} exceeds {drawdown_limit_pct:.0%} limit")

    # 5. Daily loss limit
    daily_pnl = portfolio.get("daily_pnl", 0.0)
    if daily_pnl < -(budget * daily_loss_limit_pct):
        checks["daily_loss_ok"] = False
        reasons.append(f"Daily loss {daily_pnl:.2f} exceeds {daily_loss_limit_pct:.0%} limit")

    # 6. Cooldown
    if recent_orders:
        last_order_time = recent_orders[-1].get("created_at")
        if last_order_time:
            if isinstance(last_order_time, str):
                last_order_time = datetime.fromisoformat(last_order_time)
            if datetime.now() - last_order_time < timedelta(minutes=cooldown_minutes):
                checks["cooldown_ok"] = False
                reasons.append(f"Cooldown: less than {cooldown_minutes} min since last trade")

    # 7. Consecutive losses
    consecutive_losses = 0
    for order in reversed(recent_orders):
        if order.get("pnl", 0) < 0:
            consecutive_losses += 1
        else:
            break
    if consecutive_losses >= max_consecutive_losses:
        checks["consecutive_loss_ok"] = False
        reasons.append(f"Consecutive losses: {consecutive_losses} >= {max_consecutive_losses}")

    approved = all(checks.values())
    return {
        "approved": approved,
        "rejection_reason": "; ".join(reasons) if reasons else None,
        **checks,
    }
