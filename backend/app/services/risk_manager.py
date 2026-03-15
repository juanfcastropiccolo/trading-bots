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

    # 1. Data completeness
    if features is None or signal is None:
        checks["data_complete_ok"] = False
        reasons.append("Incomplete data: features or signal missing")

    # 2. Max trade size <= $10
    max_trade = agent_config.get("max_trade_usd", 10.0)
    if portfolio["cash"] < max_trade * 0.5:
        checks["max_trade_ok"] = False
        reasons.append(f"Insufficient cash ({portfolio['cash']:.2f}) for min trade")

    # 3. Max position <= 50% of budget
    budget = agent_config.get("budget_usd", 100.0)
    position_value = portfolio.get("position_value", 0.0)
    if signal["direction"] == "BUY" and position_value > budget * 0.5:
        checks["max_position_ok"] = False
        reasons.append(f"Position {position_value:.2f} exceeds 50% of budget")

    # 4. Drawdown < 20%
    equity = portfolio.get("equity", budget)
    drawdown = (budget - equity) / budget if budget > 0 else 0
    if drawdown >= 0.20:
        checks["drawdown_ok"] = False
        reasons.append(f"Drawdown {drawdown:.1%} exceeds 20% limit")

    # 5. Daily loss < 5%
    daily_pnl = portfolio.get("daily_pnl", 0.0)
    if daily_pnl < -(budget * 0.05):
        checks["daily_loss_ok"] = False
        reasons.append(f"Daily loss {daily_pnl:.2f} exceeds 5% limit")

    # 6. Cooldown > 5 min since last trade
    if recent_orders:
        last_order_time = recent_orders[-1].get("created_at")
        if last_order_time:
            if isinstance(last_order_time, str):
                last_order_time = datetime.fromisoformat(last_order_time)
            if datetime.now() - last_order_time < timedelta(minutes=5):
                checks["cooldown_ok"] = False
                reasons.append("Cooldown: less than 5 min since last trade")

    # 7. Consecutive losses < 3
    consecutive_losses = 0
    for order in reversed(recent_orders):
        if order.get("pnl", 0) < 0:
            consecutive_losses += 1
        else:
            break
    if consecutive_losses >= 3:
        checks["consecutive_loss_ok"] = False
        reasons.append(f"Consecutive losses: {consecutive_losses} >= 3")

    approved = all(checks.values())
    return {
        "approved": approved,
        "rejection_reason": "; ".join(reasons) if reasons else None,
        **checks,
    }
