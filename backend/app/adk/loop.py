import asyncio
import logging
from datetime import datetime

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.adk.pipeline import create_trading_pipeline
from app.config import settings
from app.database import SessionLocal
from app.models import AgentConfig, PortfolioSnapshot, Position, Feature, MarketSnapshot
from app.services.exchange import exchange_service

logger = logging.getLogger(__name__)

_shutdown = False
_loop_task = None


def request_shutdown():
    global _shutdown
    _shutdown = True


def _restore_portfolio_from_db(agent_id: int, budget: float) -> dict:
    """Restore portfolio state from DB so we survive restarts."""
    db = SessionLocal()
    try:
        snap = (
            db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.agent_id == agent_id)
            .order_by(PortfolioSnapshot.id.desc())
            .first()
        )
        pos = db.query(Position).filter(Position.agent_id == agent_id).first()

        if snap:
            logger.info(f"Restoring portfolio from DB: cash={snap.cash}, equity={snap.equity}, trades={snap.total_trades}")
            return {
                "cash": snap.cash,
                "position_qty": pos.quantity if pos else 0.0,
                "entry_price": pos.entry_price if pos else 0.0,
                "side": pos.side if pos else "flat",
                "win_count": snap.win_count,
                "loss_count": snap.loss_count,
                "total_trades": snap.total_trades,
                "max_drawdown": snap.max_drawdown,
                "peak_equity": max(snap.equity, budget),
                "daily_pnl": 0.0,
            }
    finally:
        db.close()

    # Fresh start
    return {
        "cash": budget,
        "position_qty": 0.0,
        "entry_price": 0.0,
        "side": "flat",
        "win_count": 0,
        "loss_count": 0,
        "total_trades": 0,
        "max_drawdown": 0.0,
        "peak_equity": budget,
        "daily_pnl": 0.0,
    }


def _restore_prev_features_from_db(agent_id: int) -> dict | None:
    """Restore last features from DB for crossover detection."""
    db = SessionLocal()
    try:
        feat = (
            db.query(Feature)
            .filter(Feature.agent_id == agent_id)
            .order_by(Feature.id.desc())
            .first()
        )
        if feat:
            return {
                "ema_fast": feat.ema_fast,
                "ema_slow": feat.ema_slow,
                "rsi": feat.rsi,
                "atr": feat.atr,
                "close": feat.close,
            }
    finally:
        db.close()
    return None


def _download_historical_data(agent_id: int, symbol: str):
    """Download 7 days of historical candles and store in DB."""
    db = SessionLocal()
    try:
        existing = db.query(MarketSnapshot).filter(MarketSnapshot.agent_id == agent_id).count()
        if existing > 100:
            logger.info(f"Historical data already exists ({existing} candles), skipping download")
            return

        logger.info(f"Downloading 7 days of historical data for {symbol}...")
        for timeframe in ["1h"]:
            df = exchange_service.fetch_ohlcv_history(symbol, timeframe=timeframe, days=7)
            for _, row in df.iterrows():
                db.add(MarketSnapshot(
                    agent_id=agent_id,
                    timestamp=row["timestamp"].to_pydatetime(),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                ))
            db.commit()
            logger.info(f"Stored {len(df)} historical {timeframe} candles")
    except Exception as e:
        db.rollback()
        logger.error(f"Historical data download failed: {e}")
    finally:
        db.close()


async def run_trading_loop():
    global _shutdown
    _shutdown = False

    logger.info("Starting trading loop...")

    # Get or create agent config from DB
    db = SessionLocal()
    agent = db.query(AgentConfig).filter(AgentConfig.is_active.is_(True)).first()
    if not agent:
        agent = AgentConfig(
            name="BTC Trend Follower",
            symbol=settings.default_symbol,
            strategy="trend_following",
            budget_usd=settings.initial_budget_usd,
            max_trade_usd=10.0,
            mode="paper",
            is_active=True,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
    db.close()

    agent_config = {
        "id": agent.id,
        "name": agent.name,
        "symbol": agent.symbol,
        "strategy": agent.strategy,
        "budget_usd": agent.budget_usd,
        "max_trade_usd": agent.max_trade_usd,
        "mode": agent.mode,
        "timeframe": settings.default_timeframe,
        "llm_model": settings.llm_model,
    }

    # Download historical data (runs once)
    _download_historical_data(agent.id, agent.symbol)

    # Restore portfolio from DB (survives restarts)
    portfolio = _restore_portfolio_from_db(agent.id, agent.budget_usd)

    # Restore prev_features from DB (so crossover detection works from tick 1)
    prev_features = _restore_prev_features_from_db(agent.id)
    if prev_features:
        logger.info(f"Restored prev_features from DB: EMA9={prev_features['ema_fast']}, EMA21={prev_features['ema_slow']}")

    pipeline = create_trading_pipeline()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=pipeline,
        app_name="trading_bot",
        session_service=session_service,
    )

    recent_orders: list[dict] = []
    tick_count = 0

    while not _shutdown:
        tick_count += 1
        logger.info(f"=== Tick #{tick_count} @ {datetime.now().isoformat()} ===")

        try:
            # Create a fresh session each tick with current state
            # This avoids ADK session state sync issues
            session = await session_service.create_session(
                app_name="trading_bot",
                user_id="system",
                state={
                    "agent_config": agent_config,
                    "portfolio": portfolio,
                    "prev_features": prev_features,
                    "recent_orders": recent_orders,
                    "tick_error": None,
                    "signal": None,
                    "risk_approval": None,
                    "trade_result": None,
                    "llm_reasoning": None,
                },
            )

            # Run the pipeline
            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"Execute trading tick #{tick_count}")],
            )
            async for event in runner.run_async(
                user_id="system",
                session_id=session.id,
                new_message=content,
            ):
                pass

            # Read back updated state from session
            updated_session = await session_service.get_session(
                app_name="trading_bot",
                user_id="system",
                session_id=session.id,
            )
            state = updated_session.state if updated_session else {}

            # Carry forward persistent state
            if state.get("features"):
                prev_features = state["features"]

            if state.get("portfolio"):
                portfolio = state["portfolio"]

            trade = state.get("trade_result")
            if trade:
                recent_orders.append(trade)
                recent_orders = recent_orders[-10:]

        except Exception as e:
            logger.error(f"Tick #{tick_count} failed: {e}", exc_info=True)

        if not _shutdown:
            await asyncio.sleep(settings.trading_loop_interval_seconds)

    logger.info("Trading loop stopped.")


def start_loop():
    global _loop_task
    _loop_task = asyncio.create_task(run_trading_loop())
    return _loop_task
