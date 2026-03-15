from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Signal, LLMDecision, RiskCheck
from app.schemas.schemas import SignalResponse

router = APIRouter(prefix="/api/agents", tags=["signals"])


@router.get("/{agent_id}/signals", response_model=list[SignalResponse])
def get_signals(
    agent_id: int,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    signals = (
        db.query(Signal)
        .filter(Signal.agent_id == agent_id)
        .order_by(Signal.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for sig in signals:
        llm = db.query(LLMDecision).filter(LLMDecision.signal_id == sig.id).first()
        risk = db.query(RiskCheck).filter(RiskCheck.signal_id == sig.id).first()

        results.append(SignalResponse(
            id=sig.id,
            direction=sig.direction,
            confidence=sig.confidence,
            reason=sig.reason,
            llm_reasoning=llm.reasoning if llm else None,
            llm_recommendation=llm.recommendation if llm else None,
            risk_approved=risk.approved if risk else None,
            risk_reason=risk.rejection_reason if risk else None,
            created_at=sig.created_at,
        ))
    return results
