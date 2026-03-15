import logging
from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.services.risk_manager import check_risk

logger = logging.getLogger(__name__)


class RiskCheckAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if ctx.session.state.get("tick_error"):
            yield Event(author=self.name)
            return

        signal = ctx.session.state.get("signal")
        if not signal:
            yield Event(author=self.name)
            return

        features = ctx.session.state.get("features")
        portfolio = ctx.session.state.get("portfolio", {})
        agent_config = ctx.session.state.get("agent_config", {})
        recent_orders = ctx.session.state.get("recent_orders", [])

        risk_result = check_risk(signal, features, portfolio, agent_config, recent_orders)
        ctx.session.state["risk_approval"] = risk_result

        if risk_result["approved"]:
            logger.info("Risk check APPROVED")
        else:
            logger.info(f"Risk check REJECTED: {risk_result['rejection_reason']}")

        yield Event(author=self.name)
