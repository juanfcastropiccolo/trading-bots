"""Genera el reporte comparativo de las pruebas A-E a partir de los JSON de
resultados (`backend/data/*_results[_real].json`).

    python scripts/render_abcde_report.py --source real      # → ESTRATEGIAS_ABCDE_REAL.md
    python scripts/render_abcde_report.py --source synthetic # → ESTRATEGIAS_ABCDE_SINTETICO.md

Determinístico: mismos JSON → mismo reporte. Con `--source real` la única
"semilla" es la 42 (una sola historia), así que la sección de consistencia
entre semillas se omite y en su lugar se muestra la consistencia entre
folds (cuántos de los 6 folds tienen Sharpe > 0), que es la evidencia
comparable con PLAN_FUTUROS.md ("folds positivos ≥ 5/6").
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
COSTS = ("conservador_0.15%", "realista_0.05%")
COST_KEY_ML = {"conservador_0.15%": "metrics_conservador", "realista_0.05%": "metrics_realista"}


def _load(name: str, suffix: str) -> dict | None:
    path = os.path.join(DATA_DIR, f"{name}_results{suffix}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def _first_seed(d: dict, key: str) -> tuple[str, dict]:
    seeds = d[key]
    k = "42" if "42" in seeds else sorted(seeds)[0]
    return k, seeds[k]


def _pos_folds(fold_metrics: list[dict]) -> str:
    n = len(fold_metrics)
    return f"{sum(1 for m in fold_metrics if m.get('sharpe', 0) > 0)}/{n}"


def collect(suffix: str) -> tuple[list[dict], dict]:
    """Filas normalizadas: nombre, por costo → (agregado, folds), b&h, random."""
    rows, periods = [], {}
    d = _load("breakout", suffix)
    if d:
        seed, r = _first_seed(d, "by_seed")
        periods["A"] = r.get("period", "")
        rows.append({"id": "A", "name": "Breakout Donchian 20/55 + ATR",
                     "costs": {c: (r["costs"][c]["estrategia"]["agregado"], r["costs"][c]["estrategia"]["folds"]) for c in COSTS},
                     "bh": r["costs"][COSTS[1]]["buy_and_hold"]["agregado"],
                     "rnd": {c: r["costs"][c]["random_baseline"]["agregado"] for c in COSTS}})
    d = _load("pairs", suffix)
    if d:
        seed, r = _first_seed(d, "seeds")
        periods["B"] = r.get("period", "")
        rows.append({"id": "B", "name": "Pairs trading (screening walk-forward)",
                     "costs": {c: (r["screening"]["metrics"][c]["agg"], r["screening"]["metrics"][c]["per_fold"]) for c in COSTS},
                     "bh": r["buy_and_hold"], "rnd": {c: r["random_baseline"][c] for c in COSTS},
                     "extra": r["screening"].get("pairs_by_fold")})
        if r.get("oracle"):
            rows.append({"id": "B'", "name": "Pairs trading (oráculo: 3 pares cointegrados)",
                         "costs": {c: (r["oracle"]["metrics"][c]["agg"], r["oracle"]["metrics"][c]["per_fold"]) for c in COSTS},
                         "bh": r["buy_and_hold"], "rnd": {c: r["random_baseline"][c] for c in COSTS}})
    d = _load("carry", suffix)
    if d:
        seed, r = _first_seed(d, "seeds")
        periods["C"] = r.get("period", "")

        def carry_block(v):
            fm = v["fold_metrics"]
            folds = [m for k, m in fm.items() if k != "Agregado"]
            return fm["Agregado"], folds
        rows.append({"id": "C", "name": "Carry de funding, dollar-neutral",
                     "costs": {c: carry_block(r["dollar_neutral"][c]) for c in COSTS},
                     "bh": r["benchmarks"]["buy_and_hold"],
                     "rnd": {c: r["benchmarks"]["random_baseline_gross2.0"][c] for c in COSTS},
                     "decomp": {c: r["dollar_neutral"][c]["decomposicion_agregada"] for c in COSTS}})
        rows.append({"id": "C'", "name": "Carry de funding, sin neutralizar",
                     "costs": {c: carry_block(r["sin_neutralizar"][c]) for c in COSTS},
                     "bh": r["benchmarks"]["buy_and_hold"],
                     "rnd": {c: r["benchmarks"]["random_baseline_gross2.0"][c] for c in COSTS}})
    d = _load("tsmom_vt", suffix)
    if d:
        seed, r = _first_seed(d, "seeds")
        periods["D"] = r.get("period", "")
        for vname, label in (("l90", "TSMOM L=90 + vol targeting"), ("ensemble", "TSMOM ensemble {20,60,90,120} + vol targeting")):
            v = r[vname]
            rows.append({"id": "D" if vname == "ensemble" else "D0", "name": label,
                         "costs": {c: (v["costs"][c]["aggregate"], [m for _, m in v["costs"][c]["folds"]] if isinstance(v["costs"][c]["folds"][0], (list, tuple)) else v["costs"][c]["folds"]) for c in COSTS},
                         "bh": r["buy_and_hold"]["aggregate"],
                         "rnd": {c: v["random_baseline"][c]["aggregate"] for c in COSTS}})
    d = _load("ml_walkforward", suffix)
    if d:
        seed, r = _first_seed(d, "seeds")
        periods["E"] = r.get("period", "")
        agg = r["aggregate"]
        for m, label in (("logistic", "ML logística walk-forward"), ("gboost", "ML gradient boosting walk-forward")):
            rows.append({"id": "E" if m == "logistic" else "E'", "name": label,
                         "costs": {c: (agg[m][COST_KEY_ML[c]], [f[m][COST_KEY_ML[c]] for f in r["folds"]]) for c in COSTS},
                         "bh": agg["buy_and_hold"]["metrics"],
                         "rnd": {c: agg["random_full_gross"][COST_KEY_ML[c]] for c in COSTS},
                         "naive": {c: agg["naive_momentum1"][COST_KEY_ML[c]] for c in COSTS},
                         "acc": [(f["fold"], f["logistic"]["accuracy"], f["gboost"]["accuracy"]) for f in r["folds"]]})
    return rows, periods


def _m(m: dict) -> str:
    return f"{m['sharpe']:+.2f} · {m['cagr']:+.1%} · {m['max_dd']:.1%}"


def render(rows: list[dict], periods: dict, source: str) -> str:
    real = source == "real"
    title = "datos REALES (perps Binance)" if real else "mercado SINTÉTICO"
    L = [f"# Pruebas A-E sobre {title}", "",
         f"_Generado por `backend/scripts/render_abcde_report.py --source {source}` el {date.today()}._", ""]
    if real:
        L += ["Datos: klines diarios y funding de perpetuos USDT-M de Binance (bulk mensual de data.binance.vision, "
              "cache en `backend/data/cache/`), 10 majors, alineados desde que todos listan. Una sola historia: no hay "
              "semillas que comparar; la consistencia se mide entre folds contiguos. Costos por lado sobre turnover: "
              "0.15% conservador / 0.05% realista. Buy&hold es equiponderado rebalanceado a diario, sin costo.", ""]
        for k, p in periods.items():
            L.append(f"- Prueba {k}: {p}")
        L.append("")
    else:
        L += ["Mercado sintético (`synthetic_market.py`, semilla 42). Ver `ESTRATEGIAS_ABCDE.md` para el análisis.", ""]

    for c in COSTS:
        L += [f"## Costo {c.replace('_', ' ')}", "",
              "| # | Construcción | Sharpe | CAGR | Max DD | folds Sharpe>0 | b&h (Sharpe · CAGR · DD) | random (Sharpe · CAGR · DD) |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            agg, folds = r["costs"][c]
            L.append(f"| {r['id']} | {r['name']} | {agg['sharpe']:+.2f} | {agg['cagr']:+.1%} | {agg['max_dd']:.1%} | "
                     f"{_pos_folds(folds)} | {_m(r['bh'])} | {_m(r['rnd'][c])} |")
        L.append("")

    L += ["## Detalle por fold (costo realista 0.05%)", ""]
    for r in rows:
        agg, folds = r["costs"][COSTS[1]]
        L += [f"### {r['id']} — {r['name']}", "", "| Fold | Sharpe | CAGR | Max DD | win rate |", "|---|---|---|---|---|"]
        for i, m in enumerate(folds, 1):
            L.append(f"| {i} | {m['sharpe']:+.2f} | {m['cagr']:+.1%} | {m['max_dd']:.1%} | {m.get('win_rate', 0):.1%} |")
        L.append(f"| **agregado** | {agg['sharpe']:+.2f} | {agg['cagr']:+.1%} | {agg['max_dd']:.1%} | {agg.get('win_rate', 0):.1%} |")
        if "decomp" in r:
            dd = r["decomp"][COSTS[1]]
            L.append(f"\nDescomposición del PnL (suma de retornos diarios): precio {dd['precio_sum']:+.3f} · funding {dd['funding_sum']:+.3f} · total {dd['total_sum']:+.3f}")
        if "naive" in r:
            nv = r["naive"][COSTS[1]]
            L.append(f"\nBaseline «persiste el signo de ayer»: Sharpe {nv['sharpe']:+.2f}, CAGR {nv['cagr']:+.1%}, DD {nv['max_dd']:.1%}")
        if "acc" in r:
            L.append("\nAccuracy OOS por fold (logística / gboost): " + ", ".join(f"{k}: {a:.3f}/{b:.3f}" for k, a, b in r["acc"]))
        if r.get("extra"):
            L.append("\nPares elegidos por tramo: " + "; ".join(
                f"t{d['fold'] + 1}=[" + ", ".join(f"{p['a'].split('/')[0]}-{p['b'].split('/')[0]}" for p in d["pairs"]) + "]"
                for d in r["extra"]))
        L.append("")

    L += ["## Cómo leer esto", "",
          "- Un Sharpe agregado positivo con la mayoría de los folds positivos, en ambos costos, y por encima de buy&hold "
          "**y** del baseline aleatorio de igual exposición, es la vara mínima (la misma de `PLAN_FUTUROS.md`).",
          "- Una construcción que solo gana en el costo realista, o solo en 2-3 folds, es ruido hasta que se demuestre lo contrario.",
          "- Ninguna de estas configuraciones fue optimizada sobre estos datos; si se ajustan parámetros después de ver esto, "
          "hay que volver a validar en datos que no se hayan visto (el mes en curso y los siguientes)."]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("synthetic", "real"), default="real")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    suffix = "_real" if a.source == "real" else ""
    rows, periods = collect(suffix)
    if not rows:
        raise SystemExit(f"No hay JSON de resultados con sufijo '{suffix}' en {os.path.abspath(DATA_DIR)}")
    out = a.out or os.path.join(ROOT, "ESTRATEGIAS_ABCDE_REAL.md" if a.source == "real" else "ESTRATEGIAS_ABCDE_SINTETICO.md")
    with open(out, "w") as fh:
        fh.write(render(rows, periods, a.source))
    print(f"Reporte ({len(rows)} filas) → {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
