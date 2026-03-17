from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentConfig, PortfolioSnapshot, Order, Position
from app.schemas.schemas import AgentResponse, AgentCreateRequest, AddFundsRequest
from app.adk.loop import add_agent_to_loop, remove_agent_from_loop

router = APIRouter(prefix="/api/agents", tags=["agents"])

RISK_PROFILES = {
    "conservative": dict(
        max_position_pct=0.30, drawdown_limit_pct=0.10,
        daily_loss_limit_pct=0.03, cooldown_minutes=10,
        max_consecutive_losses=2, rsi_buy_max=65.0, rsi_sell_min=35.0,
    ),
    "moderate": dict(
        max_position_pct=0.50, drawdown_limit_pct=0.20,
        daily_loss_limit_pct=0.05, cooldown_minutes=2,
        max_consecutive_losses=3, rsi_buy_max=70.0, rsi_sell_min=30.0,
    ),
    "aggressive": dict(
        max_position_pct=0.75, drawdown_limit_pct=0.30,
        daily_loss_limit_pct=0.10, cooldown_minutes=2,
        max_consecutive_losses=5, rsi_buy_max=80.0, rsi_sell_min=20.0,
    ),
}


def _agent_to_response(agent: AgentConfig, db: Session) -> AgentResponse:
    snap = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.agent_id == agent.id)
        .order_by(PortfolioSnapshot.id.desc())
        .first()
    )
    # Use actual Order count from DB (authoritative, survives restarts)
    actual_total_trades = db.query(Order).filter(Order.agent_id == agent.id).count()
    # Position info
    pos = db.query(Position).filter(Position.agent_id == agent.id).first()
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        symbol=agent.symbol,
        strategy=agent.strategy,
        budget_usd=agent.budget_usd,
        max_trade_usd=agent.max_trade_usd,
        mode=agent.mode,
        is_active=agent.is_active,
        is_protected=agent.is_protected or False,
        cash=snap.cash if snap else agent.budget_usd,
        equity=snap.equity if snap else agent.budget_usd,
        total_pnl=snap.total_pnl if snap else 0,
        total_pnl_pct=snap.total_pnl_pct if snap else 0,
        win_count=snap.win_count if snap else 0,
        loss_count=snap.loss_count if snap else 0,
        total_trades=actual_total_trades,
        max_drawdown=snap.max_drawdown if snap else 0,
        position_qty=pos.quantity if pos else 0,
        position_side=pos.side if pos else "flat",
        entry_price=pos.entry_price if pos else 0,
        max_position_pct=agent.max_position_pct,
        drawdown_limit_pct=agent.drawdown_limit_pct,
        daily_loss_limit_pct=agent.daily_loss_limit_pct,
        cooldown_minutes=agent.cooldown_minutes,
        max_consecutive_losses=agent.max_consecutive_losses,
        rsi_buy_max=agent.rsi_buy_max,
        rsi_sell_min=agent.rsi_sell_min,
    )


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(AgentConfig).filter(AgentConfig.is_deleted.is_(False)).all()
    return [_agent_to_response(a, db) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent or agent.is_deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(agent, db)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(req: AgentCreateRequest, db: Session = Depends(get_db)):
    # Get risk profile defaults
    profile = RISK_PROFILES.get(req.risk_profile, RISK_PROFILES["moderate"])

    agent = AgentConfig(
        name=req.name,
        symbol=req.symbol,
        strategy="trend_following",
        budget_usd=req.budget_usd,
        max_trade_usd=req.max_trade_usd,
        mode="paper",
        is_active=True,
        is_protected=False,
        is_deleted=False,
        max_position_pct=req.max_position_pct if req.max_position_pct is not None else profile["max_position_pct"],
        drawdown_limit_pct=req.drawdown_limit_pct if req.drawdown_limit_pct is not None else profile["drawdown_limit_pct"],
        daily_loss_limit_pct=req.daily_loss_limit_pct if req.daily_loss_limit_pct is not None else profile["daily_loss_limit_pct"],
        cooldown_minutes=req.cooldown_minutes if req.cooldown_minutes is not None else profile["cooldown_minutes"],
        max_consecutive_losses=req.max_consecutive_losses if req.max_consecutive_losses is not None else profile["max_consecutive_losses"],
        rsi_buy_max=req.rsi_buy_max if req.rsi_buy_max is not None else profile["rsi_buy_max"],
        rsi_sell_min=req.rsi_sell_min if req.rsi_sell_min is not None else profile["rsi_sell_min"],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    # Hot-add to running loop
    await add_agent_to_loop(agent.id)

    return _agent_to_response(agent, db)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent or agent.is_deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_protected:
        raise HTTPException(status_code=403, detail="Protected agents cannot be deleted")

    # Soft delete
    agent.is_deleted = True
    agent.is_active = False
    db.commit()

    # Hot-remove from running loop
    await remove_agent_from_loop(agent_id)


@router.post("/{agent_id}/add-funds", response_model=AgentResponse)
def add_funds(agent_id: int, req: AddFundsRequest, db: Session = Depends(get_db)):
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent or agent.is_deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    agent.budget_usd += req.amount
    db.commit()
    db.refresh(agent)

    # Also update the latest portfolio snapshot cash
    snap = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.agent_id == agent_id)
        .order_by(PortfolioSnapshot.id.desc())
        .first()
    )
    if snap:
        snap.cash += req.amount
        snap.equity += req.amount
        db.commit()

    return _agent_to_response(agent, db)


@router.patch("/{agent_id}/toggle", response_model=AgentResponse)
async def toggle_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent or agent.is_deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = not agent.is_active
    db.commit()
    db.refresh(agent)
    if agent.is_active:
        await add_agent_to_loop(agent_id)
    else:
        await remove_agent_from_loop(agent_id)
    return _agent_to_response(agent, db)
