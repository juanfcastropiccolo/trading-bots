import logging
import json
from datetime import datetime
from typing import AsyncGenerator
from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from app.database import SessionLocal
from app.models import (
    MarketSnapshot, Feature, Signal, LLMDecision,
    RiskCheck, Order, Position, PortfolioSnapshot,
)
from app.services.portfolio_manager import calculate_portfolio_snapshot

logger = logging.getLogger(__name__)

# Will be set by main.py startup
ws_manager = None


def set_ws_manager(manager):
    global ws_manager
    ws_manager = manager


class PersistenceAgent(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        agent_config = state.get("agent_config", {})
        agent_id = agent_config.get("id", 1)

        if state.get("tick_error"):
            await self._broadcast({
                "type": "error",
                "data": {"error": state["tick_error"], "agent_id": agent_id},
            })
            yield Event(author=self.name)
            return

        db = SessionLocal()
        try:
            # Save market snapshot (latest candle)
            ohlcv = state.get("ohlcv_data", {})
            if ohlcv and ohlcv.get("close"):
                idx = len(ohlcv["close"]) - 1
                timestamps = state.get("ohlcv_timestamps", [])
                ts = datetime.fromisoformat(timestamps[idx]) if timestamps else datetime.now()
                snapshot = MarketSnapshot(
                    agent_id=agent_id,
                    timestamp=ts,
                    open=ohlcv["open"][idx],
                    high=ohlcv["high"][idx],
                    low=ohlcv["low"][idx],
                    close=ohlcv["close"][idx],
                    volume=ohlcv["volume"][idx],
                )
                db.add(snapshot)

            # Save features
            features = state.get("features")
            if features:
                db.add(Feature(
                    agent_id=agent_id,
                    ema_fast=features["ema_fast"],
                    ema_slow=features["ema_slow"],
                    rsi=features["rsi"],
                    atr=features["atr"],
                    close=features["close"],
                ))

            # Save signal
            signal = state.get("signal")
            signal_id = None
            if signal:
                sig = Signal(
                    agent_id=agent_id,
                    direction=signal["direction"],
                    confidence=signal["confidence"],
                    reason=signal["reason"],
                )
                db.add(sig)
                db.flush()
                signal_id = sig.id

            # Save LLM decision
            llm_raw = state.get("llm_reasoning")
            if llm_raw and signal_id:
                llm_data = {}
                if isinstance(llm_raw, str):
                    try:
                        llm_data = json.loads(llm_raw)
                    except json.JSONDecodeError:
                        llm_data = {"reasoning": llm_raw}
                elif isinstance(llm_raw, dict):
                    llm_data = llm_raw

                db.add(LLMDecision(
                    agent_id=agent_id,
                    signal_id=signal_id,
                    model_used=agent_config.get("llm_model", "unknown"),
                    reasoning=llm_data.get("reasoning", str(llm_raw)),
                    recommendation=llm_data.get("recommendation", ""),
                ))

            # Save risk check
            risk = state.get("risk_approval")
            if risk and signal_id:
                db.add(RiskCheck(
                    agent_id=agent_id,
                    signal_id=signal_id,
                    approved=risk["approved"],
                    max_trade_ok=risk.get("max_trade_ok", True),
                    max_position_ok=risk.get("max_position_ok", True),
                    drawdown_ok=risk.get("drawdown_ok", True),
                    daily_loss_ok=risk.get("daily_loss_ok", True),
                    cooldown_ok=risk.get("cooldown_ok", True),
                    consecutive_loss_ok=risk.get("consecutive_loss_ok", True),
                    data_complete_ok=risk.get("data_complete_ok", True),
                    rejection_reason=risk.get("rejection_reason"),
                ))

            # Save trade / order
            trade = state.get("trade_result")
            if trade and signal_id:
                db.add(Order(
                    agent_id=agent_id,
                    signal_id=signal_id,
                    side=trade["side"],
                    quantity=trade["quantity"],
                    price=trade["price"],
                    fee=trade["fee"],
                    slippage=trade["slippage"],
                    total_cost=trade["total_cost"],
                    status=trade["status"],
                    mode=trade["mode"],
                ))

            # Update position
            portfolio = state.get("portfolio", {})
            pos = db.query(Position).filter(Position.agent_id == agent_id).first()
            current_price = state.get("current_price", 0)
            if pos:
                pos.side = portfolio.get("side", "flat")
                pos.entry_price = portfolio.get("entry_price", 0)
                pos.quantity = portfolio.get("position_qty", 0)
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity if pos.quantity > 0 else 0
            else:
                db.add(Position(
                    agent_id=agent_id,
                    side=portfolio.get("side", "flat"),
                    entry_price=portfolio.get("entry_price", 0),
                    quantity=portfolio.get("position_qty", 0),
                ))

            # Save portfolio snapshot
            budget = agent_config.get("budget_usd", 100.0)
            snap = calculate_portfolio_snapshot(portfolio, current_price, budget)
            # Update state with calculated values
            portfolio["max_drawdown"] = snap["max_drawdown"]
            portfolio["peak_equity"] = snap["peak_equity"]
            state["portfolio"] = portfolio

            db.add(PortfolioSnapshot(
                agent_id=agent_id,
                cash=snap["cash"],
                equity=snap["equity"],
                total_pnl=snap["total_pnl"],
                total_pnl_pct=snap["total_pnl_pct"],
                win_count=snap["win_count"],
                loss_count=snap["loss_count"],
                total_trades=snap["total_trades"],
                max_drawdown=snap["max_drawdown"],
            ))

            db.commit()

            # Broadcast WebSocket update
            ws_data = {
                "type": "tick",
                "data": {
                    "agent_id": agent_id,
                    "price": current_price,
                    "features": features,
                    "signal": signal,
                    "risk": risk,
                    "trade": trade,
                    "portfolio": snap,
                    "llm_reasoning": state.get("llm_reasoning"),
                    "timestamp": datetime.now().isoformat(),
                },
            }
            await self._broadcast(ws_data)

        except Exception as e:
            db.rollback()
            logger.error(f"Persistence failed: {e}")
        finally:
            db.close()

        yield Event(author=self.name)

    async def _broadcast(self, data: dict):
        if ws_manager:
            await ws_manager.broadcast(json.dumps(data))
