import logging
from typing import AsyncGenerator
import pandas as pd
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.services.feature_engine import calculate_features

logger = logging.getLogger(__name__)


class FeatureCalcAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if ctx.session.state.get("tick_error"):
            yield Event(author=self.name)
            return

        ohlcv_data = ctx.session.state.get("ohlcv_data")
        if not ohlcv_data:
            ctx.session.state["tick_error"] = "No OHLCV data available"
            yield Event(author=self.name)
            return

        df = pd.DataFrame(ohlcv_data)
        features = calculate_features(df)

        if features is None:
            ctx.session.state["tick_error"] = "Not enough candles for feature calculation"
            yield Event(author=self.name)
            return

        # Carry forward previous features for crossover detection
        current_features = ctx.session.state.get("features")
        if current_features:
            ctx.session.state["prev_features"] = current_features

        ctx.session.state["features"] = features
        logger.info(
            f"Features: EMA9={features['ema_fast']}, EMA21={features['ema_slow']}, RSI={features['rsi']}"
        )

        yield Event(author=self.name)
