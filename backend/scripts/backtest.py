"""Backtester standalone para la estrategia trend_following del proyecto.

Replica la lógica de app/services/strategy_engine.py y execution_engine.py
sobre datos históricos reales (ccxt), con las mismas comisiones y slippage.

Uso:
    python scripts/backtest.py --symbol BTC/USDT --timeframe 15m --days 60
    python scripts/backtest.py --sweep   # corre la matriz símbolo x timeframe
"""
import argparse
import sys
from dataclasses import dataclass, field

import ccxt
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

SLIPPAGE_PCT = 0.0005  # igual que execution_engine
FEE_PCT = 0.001

TIMEFRAME_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def fetch_history(exchange_id: str, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    since = ex.milliseconds() - days * 86_400_000
    all_candles = []
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        all_candles.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = EMAIndicator(close=out["close"], window=9).ema_indicator()
    out["ema_slow"] = EMAIndicator(close=out["close"], window=21).ema_indicator()
    out["rsi"] = RSIIndicator(close=out["close"], window=14).rsi()
    out["atr"] = AverageTrueRange(
        high=out["high"], low=out["low"], close=out["close"], window=14
    ).average_true_range()
    return out


@dataclass
class Result:
    symbol: str
    timeframe: str
    days: int
    variant: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_pnl: float = 0.0
    fees_paid: float = 0.0
    final_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    buy_hold_return_pct: float = 0.0
    pnls: list = field(default_factory=list)

    @property
    def net_return_pct(self):
        return (self.final_equity - 100.0)

    @property
    def win_rate(self):
        closed = self.wins + self.losses
        return self.wins / closed * 100 if closed else 0.0


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    days: int,
    budget: float = 100.0,
    max_trade_usd: float = 10.0,
    rsi_buy_max: float = 70.0,
    rsi_sell_min: float = 30.0,
    atr_stop_mult: float | None = None,   # variante: stop-loss = entry - mult*ATR
    atr_take_mult: float | None = None,   # variante: take-profit = entry + mult*ATR
    variant: str = "baseline",
) -> Result:
    ind = compute_indicators(df).dropna().reset_index(drop=True)
    res = Result(symbol=symbol, timeframe=timeframe, days=days, variant=variant)

    cash = budget
    qty = 0.0
    entry = 0.0
    stop = None
    take = None
    peak = budget
    max_dd = 0.0

    for i in range(1, len(ind)):
        row, prev = ind.iloc[i], ind.iloc[i - 1]
        price = row["close"]

        # gestión de stops intra-vela (usa high/low de la vela)
        if qty > 0 and atr_stop_mult is not None and stop is not None and row["low"] <= stop:
            exec_price = stop * (1 - SLIPPAGE_PCT)
            gross = qty * exec_price
            fee = gross * FEE_PCT
            pnl = (exec_price - entry) * qty - fee
            cash += gross - fee
            res.fees_paid += fee
            res.pnls.append(pnl)
            res.trades += 1
            res.wins += pnl >= 0
            res.losses += pnl < 0
            qty, entry, stop, take = 0.0, 0.0, None, None
        elif qty > 0 and atr_take_mult is not None and take is not None and row["high"] >= take:
            exec_price = take * (1 - SLIPPAGE_PCT)
            gross = qty * exec_price
            fee = gross * FEE_PCT
            pnl = (exec_price - entry) * qty - fee
            cash += gross - fee
            res.fees_paid += fee
            res.pnls.append(pnl)
            res.trades += 1
            res.wins += pnl >= 0
            res.losses += pnl < 0
            qty, entry, stop, take = 0.0, 0.0, None, None

        bullish = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
        bearish = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]

        if bullish and row["rsi"] < rsi_buy_max and cash >= 1.0:
            trade_usd = min(max_trade_usd, cash * 0.95)
            exec_price = price * (1 + SLIPPAGE_PCT)
            fee = trade_usd * FEE_PCT
            bought = (trade_usd - fee) / exec_price
            if qty > 0:
                entry = (entry * qty + exec_price * bought) / (qty + bought)
            else:
                entry = exec_price
            qty += bought
            cash -= trade_usd
            res.fees_paid += fee
            if atr_stop_mult is not None:
                stop = entry - atr_stop_mult * row["atr"]
            if atr_take_mult is not None:
                take = entry + atr_take_mult * row["atr"]

        elif bearish and row["rsi"] > rsi_sell_min and qty > 0:
            exec_price = price * (1 - SLIPPAGE_PCT)
            gross = qty * exec_price
            fee = gross * FEE_PCT
            pnl = (exec_price - entry) * qty - fee
            cash += gross - fee
            res.fees_paid += fee
            res.pnls.append(pnl)
            res.trades += 1
            res.wins += pnl >= 0
            res.losses += pnl < 0
            qty, entry, stop, take = 0.0, 0.0, None, None

        equity = cash + qty * price
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    final_price = ind.iloc[-1]["close"]
    res.final_equity = round(cash + qty * final_price, 2)
    res.max_drawdown_pct = round(max_dd, 2)
    first_price = ind.iloc[0]["close"]
    res.buy_hold_return_pct = round((final_price - first_price) / first_price * 100, 2)
    res.gross_pnl = round(sum(res.pnls), 2)
    return res


def print_result(r: Result):
    print(
        f"{r.symbol:10s} {r.timeframe:4s} {r.days:>3}d {r.variant:22s} "
        f"equity=${r.final_equity:7.2f} ({r.net_return_pct:+6.2f}%) "
        f"trades={r.trades:3d} winrate={r.win_rate:5.1f}% "
        f"fees=${r.fees_paid:6.2f} maxDD={r.max_drawdown_pct:5.2f}% "
        f"buy&hold={r.buy_hold_return_pct:+6.2f}%"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--symbol", default="BTC/USDT")
    ap.add_argument("--timeframe", default="15m")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    if not args.sweep:
        df = fetch_history(args.exchange, args.symbol, args.timeframe, args.days)
        print(f"{len(df)} velas descargadas")
        r = run_backtest(df, args.symbol, args.timeframe, args.days)
        print_result(r)
        return

    header = f"{'símbolo':10s} {'tf':4s} {'días':>4} {'variante':22s} resultados"
    print(header)
    print("-" * 130)
    for symbol in ["BTC/USDT", "ETH/USDT"]:
        for timeframe, days in [("1m", 7), ("5m", 30), ("15m", 60), ("1h", 120)]:
            try:
                df = fetch_history(args.exchange, symbol, timeframe, days)
            except Exception as e:
                print(f"{symbol} {timeframe}: descarga falló: {e}", file=sys.stderr)
                continue
            print_result(run_backtest(df, symbol, timeframe, days, variant="baseline"))
            print_result(run_backtest(
                df, symbol, timeframe, days,
                atr_stop_mult=2.0, atr_take_mult=3.0, variant="atr_stop2_take3"))
            print_result(run_backtest(
                df, symbol, timeframe, days,
                max_trade_usd=50.0, atr_stop_mult=2.0, atr_take_mult=3.0,
                variant="size50_atr_stop"))


if __name__ == "__main__":
    main()
