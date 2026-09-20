"""Evaluación de cuatro baselines (Tabla VI del paper) del loop de market
making con Jev como capa de juicio, sobre el mercado sintético.

Filas (por mercado × venue):
  always            piso mecánico: A-S cotiza ambos lados siempre, sin juicio
  rules             reglas determinísticas → compose() del paper
  llm-stale(a)      juicio de calidad `a` entregado 10 bloques (3 s) tarde, sin deadline
  jev-argmax(a)     juicio de calidad `a` usado por argmax (sin umbrales ni Kelly)
  jev-gated(a)      la política del paper: vetos, umbrales por acción, Kelly
  jev-gated+r(a)    ídem + al hacer PULL se mantiene el lado que reduce inventario

`a` es la informatividad del oráculo calibrado (battery.OracleJudge): a = 0 es
el prior, a = 4 acierta ~99%. Un Jev real se ubica en esta escala midiendo
su Brier/accuracy con jev_replay.py sobre datos grabados del venue.

Lo que ESTE script valida: la estructura de costos, el efecto de la política
y que la calibración se mide bien. Lo que NO valida: el PnL esperado en un
venue real (eso requiere datos grabados + la API real).

Uso:  python scripts/validate_jev_mm.py [--blocks 48000] [--seed 1] [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jev.battery import DelayedJudge, OracleJudge, RulesJudge  # noqa: E402
from jev.feeds import MARKETS, SyntheticMarket  # noqa: E402
from jev.loop import LoopConfig, run  # noqa: E402
from jev.policy import Thresholds  # noqa: E402
from jev.risk import Limits  # noqa: E402
from jev.venue import VenueCosts  # noqa: E402

BUDGET = 100.0
BASE_SIZE = 200.0          # 200 MON: mínimo de orden en Kuru MON-USDC (jev-trader)
LIMITS = Limits(max_position=2 * BASE_SIZE, max_order=BASE_SIZE, max_daily_loss=20.0, max_dd=0.15)
GAS_KURU = 0.0008          # USD por tx: 0.0357 MON × $0.0226 (evento del README de jev-trader)

# gas relativo al notional de la orden: kuru_x20 = misma cadena con órdenes 20× más grandes
VENUES = {
    "ideal": VenueCosts("ideal"),
    "kuru_demo": VenueCosts("kuru_demo", maker_fee_bps=0.0, taker_fee_bps=10.0, gas_usd_per_tx=GAS_KURU),
    "kuru_x20": VenueCosts("kuru_x20", maker_fee_bps=0.0, taker_fee_bps=10.0, gas_usd_per_tx=GAS_KURU / 20),
    "perp_cex": VenueCosts("perp_cex", maker_fee_bps=1.5, taker_fee_bps=4.5, gas_usd_per_tx=0.0),
}
A_VALUES = (1.0, 2.0, 4.0)
DELAY_BLOCKS = 10          # 3 s: el LLM "rápido" de la Tabla I

REPORT = os.path.join(os.path.dirname(__file__), "..", "..", "JEV_REPORT.md")
OUT_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "jev_validation.json")


def policies(priors: dict, seed: int):
    """(nombre, judge factory, policy_mode, thresholds, enforce_deadline)."""
    mp = LIMITS.max_position
    yield "always", lambda: RulesJudge(mp), "always", Thresholds(), True
    yield "rules", lambda: RulesJudge(mp), "gated", Thresholds(), True
    yield "llm-stale(a=2)", lambda: DelayedJudge(OracleJudge(2.0, mp, seed, priors), DELAY_BLOCKS), "gated", Thresholds(), False
    yield "jev-argmax(a=2)", lambda: OracleJudge(2.0, mp, seed, priors), "argmax", Thresholds(), True
    for a in A_VALUES:
        yield f"jev-gated(a={a:g})", (lambda a=a: OracleJudge(a, mp, seed, priors)), "gated", Thresholds(), True
    for a in A_VALUES:
        yield f"jev-gated+r(a={a:g})", (lambda a=a: OracleJudge(a, mp, seed, priors)), "gated", Thresholds(pull_keep_reducing=True), True


def run_grid(n_blocks: int, seed: int, quick: bool) -> list[dict]:
    rows = []
    for mname, preset in MARKETS.items():
        mk = SyntheticMarket(preset.params, n_blocks, seed)
        events = mk.generate()
        for vname, vc in VENUES.items():
            if quick and vname not in ("ideal", "kuru_demo"):
                continue
            costs = replace(vc, inside_queue_p=preset.inside_queue_p, inside_queue_mean=preset.inside_queue_mean)
            for pname, mk_judge, mode, th, deadline in policies(mk.priors, seed + 100):
                if quick and pname not in ("always", "rules", "jev-gated(a=2)", "jev-gated+r(a=2)"):
                    continue
                cfg = LoopConfig(tick=mk.tick, base_size=BASE_SIZE, limits=LIMITS, costs=costs, thresholds=th,
                                 policy_mode=mode, enforce_deadline=deadline, min_repost_ticks=2,
                                 initial_equity_usd=BUDGET)
                t0 = time.time()
                r = run(events, mk_judge(), cfg, pname)
                row = r.row()
                row.update({"market": mname, "venue": vname, "hours": round(r.hours, 2),
                            "pnl_per_hour": round(r.net_pnl / r.hours, 4), "calibration": r.calibration,
                            "actions": r.actions, "max_tokens": r.max_tokens, "secs": round(time.time() - t0, 1)})
                rows.append(row)
                print(f"{mname:8s} {vname:9s} {pname:18s} pnl {r.net_pnl:+8.3f}  spread {r.gross_spread:6.2f} "
                      f"markout {r.markout:+6.2f} gas {r.gas:5.2f} fees {r.fees:5.2f} fills {r.fills:5d} "
                      f"tx {r.txs:5d} quoted {row['quoted%']:5.1f}%  [{row['secs']}s]", flush=True)
    return rows


def seeds_variance(n_blocks: int, seeds: tuple) -> list[dict]:
    """Variabilidad entre semillas del piso mecánico y de la política del paper (venue ideal)."""
    out = []
    for mname, preset in MARKETS.items():
        for seed in seeds:
            mk = SyntheticMarket(preset.params, n_blocks, seed)
            events = mk.generate()
            costs = replace(VENUES["ideal"], inside_queue_p=preset.inside_queue_p, inside_queue_mean=preset.inside_queue_mean)
            for pname, mode, th, judge in (("always", "always", Thresholds(), RulesJudge(LIMITS.max_position)),
                                           ("jev-gated(a=2)", "gated", Thresholds(), OracleJudge(2.0, LIMITS.max_position, seed + 100, mk.priors)),
                                           ("jev-gated+r(a=2)", "gated", Thresholds(pull_keep_reducing=True), OracleJudge(2.0, LIMITS.max_position, seed + 100, mk.priors))):
                cfg = LoopConfig(tick=mk.tick, base_size=BASE_SIZE, limits=LIMITS, costs=costs, thresholds=th,
                                 policy_mode=mode, min_repost_ticks=2, initial_equity_usd=BUDGET)
                r = run(events, judge, cfg, pname)
                out.append({"market": mname, "seed": seed, "name": pname, "net_pnl": round(r.net_pnl, 3), "fills": r.fills})
    return out


def gas_table() -> list[dict]:
    """Gas por transacción en bps del notional de la orden vs captura de spread por fill."""
    spread_bps = 7.07                      # MON-USDC en el evento del README
    capture_bps = 0.75 * spread_bps / 2    # cotizando al 75% del half-spread
    rows = []
    for notional in (4.5, 45.0, 100.0, 1000.0):
        gas_bps = GAS_KURU / notional * 1e4
        rows.append({"notional_usd": notional, "gas_bps_per_tx": round(gas_bps, 2),
                     "capture_bps_per_fill": round(capture_bps, 2),
                     "fills_per_tx_needed": round(gas_bps / capture_bps, 2)})
    return rows


def render(rows: list[dict], var: list[dict], gas: list[dict], n_blocks: int, seed: int) -> str:
    hours = n_blocks * 0.3 / 3600
    L = ["# Jev market-making POC — validación de cuatro baselines", "",
         f"_Generado por `backend/scripts/validate_jev_mm.py` · {n_blocks} bloques de 300 ms ({hours:.1f} h) por corrida · "
         f"semilla {seed} · bankroll ${BUDGET:.0f} · orden {BASE_SIZE:.0f} unidades · inventario máx. {LIMITS.max_position:.0f}_", "",
         "**Mercado sintético, no datos reales.** Sirve para medir estructura de costos y el efecto de la política, "
         "no para estimar el PnL de un venue real. Ver `JEV_ANALISIS.md` para el contexto y las conclusiones.", "",
         "## 1. Gas vs spread en Kuru MON-USDC (aritmética, no simulación)", "",
         f"Gas por transacción ${GAS_KURU} (evento del README de jev-trader). Cada bloque en que se cancela/repostea paga gas, se llene o no.", "",
         "| Notional por orden | Gas por tx (bps) | Captura por fill (bps) | Fills por tx para empatar |",
         "|---|---|---|---|"]
    for g in gas:
        L.append(f"| ${g['notional_usd']:.1f} | {g['gas_bps_per_tx']} | {g['capture_bps_per_fill']} | {g['fills_per_tx_needed']} |")
    L += ["", "Con órdenes de $4.5 (el demo del tweet) hace falta más de un fill por transacción para pagar el gas; "
          "el loop del demo hace ~1 tx por bloque y se llena en una fracción de ellos. Es negativo por construcción, "
          "independientemente de la calidad del modelo.", ""]
    L += ["## 2. Grilla mercado × venue × política", "",
          "`spread` = spread capturado en fills maker (a mid del fill); `markout` = PnL de esos fills 20 bloques después "
          "(negativo = selección adversa); `pnl` = neto de gas, fees y flatten final; `quoted%` = bloques con al menos una orden en el libro.", ""]
    for mname in MARKETS:
        L += [f"### Mercado `{mname}` — {MARKETS[mname].note}", ""]
        for vname in VENUES:
            sub = [r for r in rows if r["market"] == mname and r["venue"] == vname]
            if not sub:
                continue
            L += [f"**Venue `{vname}`** (maker {VENUES[vname].maker_fee_bps} bps · taker {VENUES[vname].taker_fee_bps} bps · gas ${VENUES[vname].gas_usd_per_tx}/tx)", "",
                  "| Política | PnL neto | PnL/h | spread | markout | gas | fees | juicio $ | fills | txs | quoted% | pulls | maxDD% |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for r in sub:
                L.append(f"| {r['name']} | {r['net_pnl']:+.3f} | {r['pnl_per_hour']:+.3f} | {r['spread']:.2f} | {r['markout']:+.2f} | "
                         f"{r['gas']:.2f} | {r['fees']:.3f} | {r['judge']:.3f} | {r['fills']} | {r['txs']} | {r['quoted%']} | {r['pulls']} | {r['max_dd%']} |")
            L.append("")
    L += ["## 3. Variabilidad entre semillas (venue ideal)", "", "| Mercado | Política | " + " | ".join(f"seed {s}" for s in sorted({v['seed'] for v in var})) + " |",
          "|---|---|" + "---|" * len({v['seed'] for v in var})]
    for mname in MARKETS:
        for pname in ("always", "jev-gated(a=2)", "jev-gated+r(a=2)"):
            vals = [v for v in var if v["market"] == mname and v["name"] == pname]
            L.append(f"| {mname} | {pname} | " + " | ".join(f"{v['net_pnl']:+.3f}" for v in sorted(vals, key=lambda x: x['seed'])) + " |")
    L += ["", "## 4. Calibración medida sobre las triples (estado, decisión, resultado)", "",
          "Brier y ECE por pregunta, mercado `hostil`, venue ideal. El oráculo está calibrado por construcción: "
          "ECE ≈ 0 confirma que el log de triples y las definiciones de resultado funcionan; el juez de reglas muestra "
          "cómo se ve un juicio mal calibrado. Un Jev real se evalúa igual con `jev_replay.py`.", "",
          "| Política | Pregunta | n | Brier | ECE | accuracy | base rate |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["market"] == "hostil" and r["venue"] == "ideal" and r["name"] in ("rules", "jev-gated(a=1)", "jev-gated(a=2)", "jev-gated(a=4)"):
            for q, m in r["calibration"].items():
                L.append(f"| {r['name']} | {q} | {m['n']} | {m['brier']} | {m['ece']} | {m['accuracy']} | {m['base_rate']} |")
    L += ["", f"Snapshot máximo observado: {max(r['max_tokens'] for r in rows)} tokens aprox. (budget del paper: 400).", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=48000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="subconjunto de venues y políticas")
    args = ap.parse_args()
    t0 = time.time()
    rows = run_grid(args.blocks, args.seed, args.quick)
    var = seeds_variance(args.blocks if not args.quick else args.blocks // 2, (1, 2, 3))
    gas = gas_table()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump({"rows": rows, "variance": var, "gas": gas, "blocks": args.blocks, "seed": args.seed}, fh, indent=1)
    with open(REPORT, "w") as fh:
        fh.write(render(rows, var, gas, args.blocks, args.seed))
    print(f"\nReporte: {os.path.abspath(REPORT)}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
