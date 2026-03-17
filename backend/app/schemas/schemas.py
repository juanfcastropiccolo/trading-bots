from pydantic import BaseModel
from datetime import datetime


class AgentResponse(BaseModel):
    id: int
    name: str
    symbol: str
    strategy: str
    budget_usd: float
    max_trade_usd: float
    mode: str
    is_active: bool
    is_protected: bool
    cash: float | None = None
    equity: float | None = None
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    win_count: int | None = None
    loss_count: int | None = None
    total_trades: int | None = None
    max_drawdown: float | None = None
    # Position info
    position_qty: float | None = None
    position_side: str | None = None
    entry_price: float | None = None
    # Risk profile
    max_position_pct: float | None = None
    drawdown_limit_pct: float | None = None
    daily_loss_limit_pct: float | None = None
    cooldown_minutes: int | None = None
    max_consecutive_losses: int | None = None
    rsi_buy_max: float | None = None
    rsi_sell_min: float | None = None

    model_config = {"from_attributes": True}


class AgentCreateRequest(BaseModel):
    name: str
    symbol: str
    budget_usd: float = 100.0
    max_trade_usd: float = 10.0
    risk_profile: str = "moderate"
    # Optional overrides
    max_position_pct: float | None = None
    drawdown_limit_pct: float | None = None
    daily_loss_limit_pct: float | None = None
    cooldown_minutes: int | None = None
    max_consecutive_losses: int | None = None
    rsi_buy_max: float | None = None
    rsi_sell_min: float | None = None


class AddFundsRequest(BaseModel):
    amount: float


class TradeResponse(BaseModel):
    id: int
    side: str
    quantity: float
    price: float
    fee: float
    total_cost: float
    status: str
    mode: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalResponse(BaseModel):
    id: int
    direction: str
    confidence: float
    reason: str | None
    llm_reasoning: str | None = None
    llm_recommendation: str | None = None
    risk_approved: bool | None = None
    risk_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class SnapshotResponse(BaseModel):
    id: int
    cash: float
    equity: float
    total_pnl: float
    total_pnl_pct: float
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    version: str


class WSMessage(BaseModel):
    type: str  # tick, trade, signal, error
    data: dict
