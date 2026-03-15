import logging
from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.services.exchange import exchange_service

logger = logging.getLogger(__name__)


class DataIngestionAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        config = ctx.session.state.get("agent_config", {})
        symbol = config.get("symbol", "BTC/USDT")
        timeframe = config.get("timeframe", "1m")

        try:
            df = exchange_service.fetch_ohlcv(symbol, timeframe, limit=50)
            ticker = exchange_service.fetch_ticker(symbol)

            # Store serializable data in state
            ctx.session.state["ohlcv_data"] = df.to_dict(orient="list")
            ctx.session.state["ohlcv_timestamps"] = [
                t.isoformat() for t in df["timestamp"]
            ]
            ctx.session.state["current_price"] = ticker["last"]
            ctx.session.state["tick_error"] = None

            logger.info(f"Ingested {len(df)} candles for {symbol}, price={ticker['last']}")

        except Exception as e:
            logger.error(f"Data ingestion failed: {e}")
            ctx.session.state["tick_error"] = str(e)

        yield Event(author=self.name)
