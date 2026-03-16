import logging
from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.services.strategy_engine import evaluate_trend_following

logger = logging.getLogger(__name__)


class StrategyEvalAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if ctx.session.state.get("tick_error"):
            yield Event(author=self.name)
            return

        features = ctx.session.state.get("features")
        prev_features = ctx.session.state.get("prev_features")

        if not features:
            ctx.session.state["tick_error"] = "No features available"
            yield Event(author=self.name)
            return

        agent_config = ctx.session.state.get("agent_config", {})
        signal = evaluate_trend_following(features, prev_features, params=agent_config)
        ctx.session.state["signal"] = signal

        logger.info(f"Signal: {signal['direction']} (confidence={signal['confidence']})")

        yield Event(author=self.name)
