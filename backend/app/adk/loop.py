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
_agent_tasks: dict[int, asyncio.Task] = {}


def request_shutdown():
    global _shutdown
    _shutdown = True


def _build_agent_config(agent: AgentConfig) -> dict:
    """Build the agent_config dict from DB model."""
    return {
        "id": agent.id,
        "name": agent.name,
        "symbol": agent.symbol,
        "strategy": agent.strategy,
        "budget_usd": agent.budget_usd,
        "max_trade_usd": agent.max_trade_usd,
        "mode": agent.mode,
        "timeframe": settings.default_timeframe,
        "llm_model": settings.llm_model,
        # Risk profile
        "max_position_pct": agent.max_position_pct or 0.50,
        "drawdown_limit_pct": agent.drawdown_limit_pct or 0.20,
        "daily_loss_limit_pct": agent.daily_loss_limit_pct or 0.05,
        "cooldown_minutes": agent.cooldown_minutes or 5,
        "max_consecutive_losses": agent.max_consecutive_losses or 3,
        "rsi_buy_max": agent.rsi_buy_max or 70.0,
        "rsi_sell_min": agent.rsi_sell_min or 30.0,
    }


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
            logger.info(f"[{symbol}] Historical data already exists ({existing} candles), skipping download")
            return

        logger.info(f"[{symbol}] Downloading 7 days of historical data...")
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
            logger.info(f"[{symbol}] Stored {len(df)} historical {timeframe} candles")
    except Exception as e:
        db.rollback()
        logger.error(f"[{symbol}] Historical data download failed: {e}")
    finally:
        db.close()


def _seed_agents():
    """Seed BTC and ETH protected agents if they don't exist."""
    db = SessionLocal()
    try:
        existing = db.query(AgentConfig).filter(AgentConfig.is_deleted.is_(False)).all()
        existing_symbols = {a.symbol for a in existing}

        if "BTC/USDT" not in existing_symbols:
            btc = AgentConfig(
                name="BTC Trend Follower",
                symbol="BTC/USDT",
                strategy="trend_following",
                budget_usd=100.0,
                max_trade_usd=10.0,
                mode="paper",
                is_active=True,
                is_protected=True,
                max_position_pct=0.50,
                drawdown_limit_pct=0.20,
                daily_loss_limit_pct=0.05,
                cooldown_minutes=5,
                max_consecutive_losses=3,
                rsi_buy_max=70.0,
                rsi_sell_min=30.0,
            )
            db.add(btc)
            logger.info("Seeded BTC Trend Follower (protected, mid-risk)")

        if "ETH/USDT" not in existing_symbols:
            eth = AgentConfig(
                name="ETH High-Risk",
                symbol="ETH/USDT",
                strategy="trend_following",
                budget_usd=100.0,
                max_trade_usd=20.0,
                mode="paper",
                is_active=True,
                is_protected=True,
                max_position_pct=0.75,
                drawdown_limit_pct=0.30,
                daily_loss_limit_pct=0.10,
                cooldown_minutes=2,
                max_consecutive_losses=5,
                rsi_buy_max=80.0,
                rsi_sell_min=20.0,
            )
            db.add(eth)
            logger.info("Seeded ETH High-Risk (protected, aggressive)")

        db.commit()
    finally:
        db.close()


async def _run_single_agent_loop(agent_id: int):
    """Independent loop for a single agent."""
    global _shutdown

    db = SessionLocal()
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent:
        db.close()
        logger.error(f"Agent {agent_id} not found")
        return
    db.close()

    agent_config = _build_agent_config(agent)
    symbol = agent.symbol
    app_name = f"trading_bot_agent_{agent_id}"

    logger.info(f"[{symbol}] Starting agent loop (id={agent_id})")

    # Download historical data
    _download_historical_data(agent_id, symbol)

    # Restore state
    portfolio = _restore_portfolio_from_db(agent_id, agent.budget_usd)
    prev_features = _restore_prev_features_from_db(agent_id)
    if prev_features:
        logger.info(f"[{symbol}] Restored prev_features: EMA9={prev_features['ema_fast']}, EMA21={prev_features['ema_slow']}")

    pipeline = create_trading_pipeline()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=pipeline,
        app_name=app_name,
        session_service=session_service,
    )

    recent_orders: list[dict] = []
    tick_count = 0

    while not _shutdown:
        tick_count += 1
        logger.info(f"[{symbol}] === Tick #{tick_count} @ {datetime.now().isoformat()} ===")

        try:
            session = await session_service.create_session(
                app_name=app_name,
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

            updated_session = await session_service.get_session(
                app_name=app_name,
                user_id="system",
                session_id=session.id,
            )
            state = updated_session.state if updated_session else {}

            if state.get("features"):
                prev_features = state["features"]
            if state.get("portfolio"):
                portfolio = state["portfolio"]

            trade = state.get("trade_result")
            if trade:
                recent_orders.append(trade)
                recent_orders = recent_orders[-10:]

        except asyncio.CancelledError:
            logger.info(f"[{symbol}] Agent loop cancelled")
            return
        except Exception as e:
            logger.error(f"[{symbol}] Tick #{tick_count} failed: {e}", exc_info=True)

        if not _shutdown:
            try:
                await asyncio.sleep(settings.trading_loop_interval_seconds)
            except asyncio.CancelledError:
                logger.info(f"[{symbol}] Agent loop cancelled during sleep")
                return

    logger.info(f"[{symbol}] Agent loop stopped.")


async def run_trading_loop():
    """Orchestrator: launches all active agents."""
    global _shutdown
    _shutdown = False

    logger.info("Starting multi-agent trading loop...")

    # Seed BTC + ETH if they don't exist
    _seed_agents()

    # Query active, non-deleted agents
    db = SessionLocal()
    agents = (
        db.query(AgentConfig)
        .filter(AgentConfig.is_active.is_(True), AgentConfig.is_deleted.is_(False))
        .all()
    )
    agent_ids = [a.id for a in agents]
    logger.info(f"Found {len(agents)} active agents: {[a.symbol for a in agents]}")
    db.close()

    # Launch all agent tasks
    for agent_id in agent_ids:
        _agent_tasks[agent_id] = asyncio.create_task(_run_single_agent_loop(agent_id))

    # Wait for all tasks (they run until shutdown)
    if _agent_tasks:
        await asyncio.gather(*_agent_tasks.values(), return_exceptions=True)

    logger.info("Multi-agent trading loop stopped.")


async def add_agent_to_loop(agent_id: int):
    """Hot-add: start loop for a new agent without restarting server."""
    if agent_id not in _agent_tasks or _agent_tasks[agent_id].done():
        _agent_tasks[agent_id] = asyncio.create_task(_run_single_agent_loop(agent_id))
        logger.info(f"Hot-added agent {agent_id} to loop")


async def remove_agent_from_loop(agent_id: int):
    """Hot-remove: cancel the agent's task."""
    task = _agent_tasks.pop(agent_id, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"Hot-removed agent {agent_id} from loop")


def start_loop():
    global _loop_task
    _loop_task = asyncio.create_task(run_trading_loop())
    return _loop_task
