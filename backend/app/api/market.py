import time
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MarketSnapshot, PortfolioSnapshot
from app.schemas.schemas import CandleResponse, SnapshotResponse
from app.services.exchange import exchange_service

router = APIRouter(prefix="/api", tags=["market"])


# Timeframe → how many days of history + CCXT limit
_TF_CONFIG = {
    "1m": {"days": 1, "limit": 500, "cache_ttl": 30},
    "1h": {"days": 7, "limit": 168, "cache_ttl": 120},
    "1d": {"days": 90, "limit": 90, "cache_ttl": 300},
    "1w": {"days": 365, "limit": 52, "cache_ttl": 600},
}

# Simple in-memory cache: {(symbol, timeframe): (timestamp, data)}
_candle_cache: dict[tuple[str, str], tuple[float, list[CandleResponse]]] = {}


@router.get("/market/{symbol}/candles", response_model=list[CandleResponse])
def get_candles(
    symbol: str,
    timeframe: str = Query(default="1h", pattern="^(1m|1h|1d|1w)$"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
):
    """Fetch candles from Binance with in-memory cache to avoid API spam."""
    cfg = _TF_CONFIG.get(timeframe, _TF_CONFIG["1h"])
    cache_key = (symbol, timeframe)
    now = time.time()

    # Return cached if fresh enough
    if cache_key in _candle_cache:
        cached_at, cached_data = _candle_cache[cache_key]
        if now - cached_at < cfg["cache_ttl"]:
            return cached_data

    fetch_limit = min(limit, cfg["limit"])

    try:
        df = exchange_service.fetch_ohlcv(
            symbol.replace("-", "/"),
            timeframe=timeframe,
            limit=fetch_limit,
        )
        result = [
            CandleResponse(
                timestamp=row["timestamp"].to_pydatetime(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for _, row in df.iterrows()
        ]
        _candle_cache[cache_key] = (now, result)
        return result
    except Exception:
        # Fallback to DB data
        snapshots = (
            db.query(MarketSnapshot)
            .order_by(MarketSnapshot.id.desc())
            .limit(limit)
            .all()
        )
        return [
            CandleResponse(
                timestamp=s.timestamp,
                open=s.open,
                high=s.high,
                low=s.low,
                close=s.close,
                volume=s.volume,
            )
            for s in reversed(snapshots)
        ]


@router.get("/agents/{agent_id}/snapshots", response_model=list[SnapshotResponse])
def get_snapshots(
    agent_id: int,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    snapshots = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.agent_id == agent_id)
        .order_by(PortfolioSnapshot.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(snapshots))
