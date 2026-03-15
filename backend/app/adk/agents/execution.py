import logging
from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.services.execution_engine import simulate_trade

logger = logging.getLogger(__name__)


class ExecutionAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if ctx.session.state.get("tick_error"):
            yield Event(author=self.name)
            return

        risk_approval = ctx.session.state.get("risk_approval", {})
        if not risk_approval.get("approved"):
            ctx.session.state["trade_result"] = None
            yield Event(author=self.name)
            return

        signal = ctx.session.state.get("signal", {})
        current_price = ctx.session.state.get("current_price", 0)
        portfolio = ctx.session.state.get("portfolio", {})
        agent_config = ctx.session.state.get("agent_config", {})

        trade = simulate_trade(signal, current_price, portfolio, agent_config)

        if trade:
            # Update portfolio in state
            update = trade.pop("portfolio_update")
            portfolio.update(update)

            # Track wins/losses
            if trade.get("realized_pnl") is not None:
                portfolio["total_trades"] = portfolio.get("total_trades", 0) + 1
                if trade["realized_pnl"] >= 0:
                    portfolio["win_count"] = portfolio.get("win_count", 0) + 1
                else:
                    portfolio["loss_count"] = portfolio.get("loss_count", 0) + 1
                portfolio["daily_pnl"] = portfolio.get("daily_pnl", 0) + trade["realized_pnl"]
            elif trade["side"] == "buy":
                portfolio["total_trades"] = portfolio.get("total_trades", 0) + 1

            ctx.session.state["portfolio"] = portfolio
            ctx.session.state["trade_result"] = trade
            logger.info(f"Trade executed: {trade['side']} {trade['quantity']} @ {trade['price']}")
        else:
            ctx.session.state["trade_result"] = None

        yield Event(author=self.name)
