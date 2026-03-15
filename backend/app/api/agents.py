from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AgentConfig, PortfolioSnapshot
from app.schemas.schemas import AgentResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(AgentConfig).all()
    results = []
    for agent in agents:
        snap = (
            db.query(PortfolioSnapshot)
            .filter(PortfolioSnapshot.agent_id == agent.id)
            .order_by(PortfolioSnapshot.id.desc())
            .first()
        )
        data = AgentResponse(
            id=agent.id,
            name=agent.name,
            symbol=agent.symbol,
            strategy=agent.strategy,
            budget_usd=agent.budget_usd,
            mode=agent.mode,
            is_active=agent.is_active,
            cash=snap.cash if snap else agent.budget_usd,
            equity=snap.equity if snap else agent.budget_usd,
            total_pnl=snap.total_pnl if snap else 0,
            total_pnl_pct=snap.total_pnl_pct if snap else 0,
            win_count=snap.win_count if snap else 0,
            loss_count=snap.loss_count if snap else 0,
            total_trades=snap.total_trades if snap else 0,
            max_drawdown=snap.max_drawdown if snap else 0,
        )
        results.append(data)
    return results


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(AgentConfig).filter(AgentConfig.id == agent_id).first()
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found")

    snap = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.agent_id == agent_id)
        .order_by(PortfolioSnapshot.id.desc())
        .first()
    )
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        symbol=agent.symbol,
        strategy=agent.strategy,
        budget_usd=agent.budget_usd,
        mode=agent.mode,
        is_active=agent.is_active,
        cash=snap.cash if snap else agent.budget_usd,
        equity=snap.equity if snap else agent.budget_usd,
        total_pnl=snap.total_pnl if snap else 0,
        total_pnl_pct=snap.total_pnl_pct if snap else 0,
        win_count=snap.win_count if snap else 0,
        loss_count=snap.loss_count if snap else 0,
        total_trades=snap.total_trades if snap else 0,
        max_drawdown=snap.max_drawdown if snap else 0,
    )
