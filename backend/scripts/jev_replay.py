"""Corre el loop de market making sobre un feed grabado (jev_record.py) o
sobre el mercado sintético, con el juez elegido, e imprime PnL, costos y la
calibración por pregunta. Es el camino para validar Jev REAL en un venue:

  1. grabar libro + prints:      python scripts/jev_record.py --exchange hyperliquid --symbol BTC/USDC:USDC --seconds 3600
  2. reglas (sin API):           python scripts/jev_replay.py --feed backend/data/jev_feed.jsonl --judge rules
  3. Jev real (TYPESAFE_API_KEY): python scripts/jev_replay.py --feed backend/data/jev_feed.jsonl --judge jev

La corrida con `--judge jev` llama a la API una vez por bloque (≈ 240 tokens
→ ~$0.00001 por llamada) y guarda las triples en --triples para recalibrar
(Platt) y comparar contra las reglas sobre el mismo feed.

Uso:  python scripts/jev_replay.py --feed <jsonl> --judge rules|jev [--mode gated|argmax|always]
      python scripts/jev_replay.py --synthetic hostil --judge rules
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jev.battery import RulesJudge  # noqa: E402
from jev.calibration import platt_fit  # noqa: E402
from jev.feeds import MARKETS, SyntheticMarket, read_jsonl  # noqa: E402
from jev.loop import LoopConfig, run  # noqa: E402
from jev.policy import Thresholds  # noqa: E402
from jev.risk import Limits  # noqa: E402
from jev.venue import VenueCosts  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="jsonl grabado con jev_record.py")
    ap.add_argument("--synthetic", choices=list(MARKETS), help="mercado sintético en vez de feed")
    ap.add_argument("--blocks", type=int, default=24000)
    ap.add_argument("--judge", choices=["rules", "jev"], default="rules")
    ap.add_argument("--mode", choices=["gated", "argmax", "always"], default="gated")
    ap.add_argument("--keep-reducing", action="store_true", help="PULL mantiene el lado que reduce inventario")
    ap.add_argument("--tick", type=float, help="tamaño del tick (obligatorio con --feed)")
    ap.add_argument("--block-s", type=float, default=0.3, help="segundos por bloque/muestra del feed")
    ap.add_argument("--base-size", type=float, default=200.0)
    ap.add_argument("--budget", type=float, default=100.0)
    ap.add_argument("--maker-bps", type=float, default=0.0)
    ap.add_argument("--taker-bps", type=float, default=10.0)
    ap.add_argument("--gas", type=float, default=0.0, help="USD por transacción")
    ap.add_argument("--deadline-ms", type=float, default=250.0)
    ap.add_argument("--triples", help="jsonl de salida con las triples para calibrar")
    args = ap.parse_args()

    if args.synthetic:
        mk = SyntheticMarket(MARKETS[args.synthetic].params, args.blocks, seed=1)
        events, tick = mk.generate(), mk.tick
    elif args.feed:
        if not args.tick:
            raise SystemExit("--tick es obligatorio con --feed")
        events, tick = list(read_jsonl(args.feed)), args.tick
    else:
        raise SystemExit("indicar --feed o --synthetic")

    lim = Limits(max_position=2 * args.base_size, max_order=args.base_size, max_daily_loss=0.2 * args.budget, max_dd=0.15)
    if args.judge == "jev":
        from jev.battery import JevJudge
        judge = JevJudge(deadline_ms=args.deadline_ms)
    else:
        judge = RulesJudge(lim.max_position)
    cfg = LoopConfig(tick=tick, base_size=args.base_size, limits=lim, block_s=args.block_s,
                     costs=VenueCosts("cli", args.maker_bps, args.taker_bps, args.gas),
                     thresholds=Thresholds(pull_keep_reducing=args.keep_reducing), policy_mode=args.mode,
                     deadline_ms=args.deadline_ms, initial_equity_usd=args.budget,
                     state_engine_kwargs={} if args.block_s == 0.3 else {"w_flow": 100})
    r = run(events, judge, cfg, f"{args.judge}/{args.mode}")
    print(json.dumps(r.row(), indent=1))
    print("acciones:", r.actions)
    print("calibración:", json.dumps(r.calibration, indent=1))
    for q in ("toxic_flow", "liquidity_stressed"):
        ps = [t["answers"][q] for t in r.triples if q in t["outcome"]]
        ys = [t["outcome"][q] for t in r.triples if q in t["outcome"]]
        if ps:
            print(f"Platt {q}: a, b =", tuple(round(x, 3) for x in platt_fit(ps, ys)))
    if args.judge == "jev":
        print(f"Jev: {judge.calls} llamadas, {judge.errors} errores, {judge.late} tarde, ${judge.cost_usd:.4f}")
    if args.triples:
        with open(args.triples, "w") as fh:
            for t in r.triples:
                fh.write(json.dumps(t) + "\n")
        print("triples →", args.triples)


if __name__ == "__main__":
    main()
