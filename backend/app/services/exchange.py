import ccxt
import pandas as pd
import logging
import threading
import time as _time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Minimum seconds between any API call
_MIN_INTERVAL = 5
_CALLS_PER_MINUTE_LIMIT = 10


class RateLimiter:
    """Simple rate limiter: max N calls per minute, min interval between calls."""

    def __init__(self, max_per_minute: int = _CALLS_PER_MINUTE_LIMIT, min_interval: float = _MIN_INTERVAL):
        self._max_per_minute = max_per_minute
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._timestamps: list[float] = []
        self._last_call: float = 0

    def acquire(self):
        with self._lock:
            now = _time.monotonic()

            # Enforce minimum interval
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                logger.warning(f"Rate limiter: waiting {wait:.1f}s (min interval)")
                _time.sleep(wait)
                now = _time.monotonic()

            # Enforce per-minute cap
            cutoff = now - 60
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self._max_per_minute:
                wait = self._timestamps[0] - cutoff + 0.1
                logger.warning(f"Rate limiter: waiting {wait:.1f}s (per-minute cap hit: {len(self._timestamps)}/{self._max_per_minute})")
                _time.sleep(wait)
                now = _time.monotonic()
                self._timestamps = [t for t in self._timestamps if t > now - 60]

            self._timestamps.append(now)
            self._last_call = now


class ExchangeService:
    def __init__(self):
        self.exchange = ccxt.binance({"enableRateLimit": True})
        self._limiter = RateLimiter()

    def fetch_ohlcv(
        self, symbol: str = "BTC/USDT", timeframe: str = "1m", limit: int = 50
    ) -> pd.DataFrame:
        self._limiter.acquire()
        raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def fetch_ohlcv_history(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        days: int = 7,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data going back `days` days."""
        since = self.exchange.parse8601(
            (datetime.utcnow() - timedelta(days=days)).isoformat()
        )
        all_candles = []
        while True:
            self._limiter.acquire()
            batch = self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=1000
            )
            if not batch:
                break
            all_candles.extend(batch)
            since = batch[-1][0] + 1
            if len(batch) < 1000:
                break

        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
        logger.info(f"Fetched {len(df)} historical {timeframe} candles for {symbol} ({days}d)")
        return df

    def fetch_ticker(self, symbol: str = "BTC/USDT") -> dict:
        self._limiter.acquire()
        ticker = self.exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "last": ticker["last"],
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "timestamp": datetime.now().isoformat(),
        }


exchange_service = ExchangeService()
