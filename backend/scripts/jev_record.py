"""Graba libro L2 + trades de un par vía ccxt para replay con jev_replay.py.

Un CEX no tiene bloques: cada muestra (`--interval` segundos) hace de bloque.
Los trades se deduplican por id. Salida: jsonl con {block, ts, bids, asks, prints}.

Uso:  python scripts/jev_record.py --exchange hyperliquid --symbol BTC/USDC:USDC --seconds 3600 --interval 1
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jev.feeds import record  # noqa: E402

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "jev_feed.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="hyperliquid")
    ap.add_argument("--symbol", default="BTC/USDC:USDC")
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--levels", type=int, default=5)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n = record(args.exchange, args.symbol, args.seconds, args.out, args.interval, args.levels)
    print(f"{n} bloques → {args.out}")


if __name__ == "__main__":
    main()
