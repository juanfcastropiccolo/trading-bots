def calculate_portfolio_snapshot(
    portfolio: dict, current_price: float, budget: float
) -> dict:
    cash = portfolio.get("cash", budget)
    position_qty = portfolio.get("position_qty", 0.0)
    entry_price = portfolio.get("entry_price", 0.0)

    position_value = position_qty * current_price
    unrealized_pnl = (current_price - entry_price) * position_qty if position_qty > 0 else 0.0
    equity = cash + position_value
    total_pnl = equity - budget
    total_pnl_pct = (total_pnl / budget * 100) if budget > 0 else 0.0
    max_drawdown = portfolio.get("max_drawdown", 0.0)
    peak_equity = portfolio.get("peak_equity", budget)

    if equity > peak_equity:
        peak_equity = equity
    current_drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
    if current_drawdown > max_drawdown:
        max_drawdown = current_drawdown

    return {
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "position_value": round(position_value, 2),
        "position_qty": round(position_qty, 8),
        "position_side": portfolio.get("side", "flat"),
        "entry_price": round(entry_price, 2),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "total_pnl": round(total_pnl, 4),
        "total_pnl_pct": round(total_pnl_pct, 4),
        "max_drawdown": round(max_drawdown, 4),
        "peak_equity": round(peak_equity, 2),
        "win_count": portfolio.get("win_count", 0),
        "loss_count": portfolio.get("loss_count", 0),
        "total_trades": portfolio.get("total_trades", 0),
        "daily_pnl": portfolio.get("daily_pnl", 0.0),
    }
