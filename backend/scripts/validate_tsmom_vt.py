"""Prueba D — TSMOM absoluto diversificado con vol targeting en dos capas.

Deliberadamente DISTINTA de la rotación cross-sectional ya validada
(`validate_momentum.py`, top-2 por momentum de 30d sobre SMA-100): acá no
hay ranking ni "elegir ganadores" entre activos. Es time-series momentum
absoluto al estilo Moskowitz-Ooi-Pedersen (2012): CADA uno de los 10 activos
recibe una posición simultánea, larga o corta, según el signo de SU PROPIA
tendencia — no importa cómo le va a los demás. El tamaño de cada posición
se normaliza por volatilidad en dos capas independientes:

  Capa 1 (por activo): escala el peso bruto de cada activo para que su
  contribución de riesgo apunte a `VOL_TARGET_ASSET` anualizado, con un
  cap de apalancamiento por activo (`ASSET_LEVERAGE_CAP`). Esto evita que
  un activo ruidoso (SOL/DOGE) domine el libro solo por tener más volatilidad
  idiosincrática que un major (BTC).

  Capa 2 (portafolio): en cripto los 10 activos comparten un factor común
  fuerte (ver `synthetic_market.py`, `BETA`), así que en un régimen de
  tendencia generalizada (bull o bear) las señales de capa 1 tienden a
  alinearse en el mismo signo y el portafolio queda con MÁS riesgo
  correlacionado del que targetea la capa 1 activo por activo. La capa 2
  vuelve a escalar el VECTOR COMPLETO de pesos para que la vol realizada
  DEL PORTAFOLIO (no la suma ingenua de vols individuales) apunte a
  `VOL_TARGET_PORTFOLIO`, con un cap de exposición bruta total (`GROSS_CAP`).

  Método elegido para estimar la vol de portafolio con info hasta el cierre
  de t (sin lookahead): se toman los pesos brutos YA CONOCIDOS al cierre de
  t (capa 1) y se los aplica a los retornos diarios REALIZADOS de los
  últimos `VOL_LOOKBACK` días (incluido t) para armar una serie "pseudo-
  portafolio" retroactiva; su desvío estándar anualizado es la vol de
  portafolio estimada. Esto es algebraicamente equivalente a
  sqrt(w' Σ_rolling w) con Σ_rolling la covarianza muestral de esa misma
  ventana, pero se calcula sin construir la matriz de covarianza explícita.

Regla de no-lookahead del proyecto: toda señal/peso indexado en `t` usa
información hasta el cierre de `t`; se aplica al retorno de `t+1` vía
`.shift(1)` antes de pasar por `apply_costs` (igual convención que
`buy_and_hold` en `backtest_common.py`).

Variantes reportadas (ambas con vol targeting de dos capas):
  - L=90 solo: señal = signo(retorno acumulado de 90 días).
  - Ensemble de lookbacks {20, 60, 90, 120}: se promedia el SIGNO (no el
    resultado del backtest) de cada lookback antes de aplicar el vol
    targeting, tal como lo sugiere PLAN_FUTUROS.md citando Barroso-Santa
    Clara y Moreira-Muir (vol targeting) — acá además se prueba si el
    ensemble de lookbacks mejora Sharpe/estabilidad, como predice esa
    literatura para el overlay de vol targeting.

Walk-forward: 6 folds contiguos (`fold_slices`) sobre ~6 años de datos
sintéticos diarios, con warmup de 150 días (= max lookback del ensemble +
ventana de vol), igual para ambas variantes para que los folds sean
comparables. 3 semillas (42 primaria con detalle por fold, 7 y 123 solo
agregado). Costos: conservador (0.15%) y realista (0.05%) por lado, sobre
turnover. Comparación contra buy&hold equiponderado y contra un baseline de
pesos aleatorios con exposición bruta comparable.

Uso:  python scripts/validate_tsmom_vt.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from backtest_common import (
    COST_CONSERVATIVE,
    COST_REALISTIC,
    PERIODS_PER_YEAR,
    apply_costs,
    buy_and_hold,
    fold_slices,
    fold_table,
    metrics,
    random_baseline,
)
from market_data import describe, load_market, parse_cli

N_DAYS = 2190          # ~6 años
N_FOLDS = 6
SEEDS = [42, 7, 123]
PRIMARY_SEED = 42

SOURCE = "synthetic"     # market_data: 'synthetic' | 'real' (se fija desde la CLI en main)
CACHE_DIR = None         # cache de futures_data para --source real

L_BASE = 90
ENSEMBLE_LBS = [20, 60, 90, 120]
VOL_LOOKBACK = 30            # ventana rolling para vol realizada (activo y portafolio)
VOL_TARGET_ASSET = 0.40      # capa 1: vol objetivo por activo, anualizada (40%)
ASSET_LEVERAGE_CAP = 2.0     # cap |peso| por activo tras capa 1
VOL_TARGET_PORTFOLIO = 0.35  # capa 2: vol objetivo del portafolio, anualizada (35%)
GROSS_CAP = 3.0              # cap de exposición bruta total (sum|peso|) tras capa 2
WARMUP = max(ENSEMBLE_LBS) + VOL_LOOKBACK   # 150 días, común a L=90 y ensemble

COSTS = {"conservador_0.15%": COST_CONSERVATIVE, "realista_0.05%": COST_REALISTIC}


# ---------------------------------------------------------------- señal y pesos

def _signal(close: pd.DataFrame, lookbacks: list[int]) -> pd.DataFrame:
    """Momentum absoluto por activo (sin ranking cross-sectional): signo del
    retorno acumulado de los últimos L días, calculado hasta el cierre de t.
    Con varios L se promedia el SIGNO antes del vol targeting (ensemble)."""
    sigs = [np.sign(close.pct_change(L)) for L in lookbacks]
    return sum(sigs) / len(sigs)


def build_weights(close: pd.DataFrame, daily_ret: pd.DataFrame, lookbacks: list[int]) -> dict:
    """Pesos de la variante TSMOM + vol targeting de dos capas.

    Devuelve el vector de pesos indexado en t (información hasta el cierre
    de t; el llamador debe `.shift(1)` antes de aplicarlo a retornos), más
    series de diagnóstico (vol de portafolio estimada, exposición bruta).
    """
    signal = _signal(close, lookbacks)

    # --- capa 1: vol targeting por activo ---
    vol_asset = daily_ret.rolling(VOL_LOOKBACK).std() * np.sqrt(PERIODS_PER_YEAR)
    raw = (signal * (VOL_TARGET_ASSET / vol_asset)).clip(-ASSET_LEVERAGE_CAP, ASSET_LEVERAGE_CAP)
    raw = raw.where(vol_asset > 1e-9, 0.0).fillna(0.0)

    # --- capa 2: vol targeting de portafolio ---
    n, k = close.shape
    ret_vals = daily_ret.to_numpy()
    raw_vals = raw.to_numpy()
    final_vals = np.zeros((n, k))
    port_vol = np.full(n, np.nan)

    warmup = max(max(lookbacks), VOL_LOOKBACK)
    for t in range(warmup, n):
        w = raw_vals[t]
        window = ret_vals[t - VOL_LOOKBACK + 1: t + 1]
        if np.isnan(window).any() or np.isnan(w).any():
            continue
        pseudo = window @ w   # retorno diario "si hubiera sostenido w" en los últimos VOL_LOOKBACK días
        pv = float(pseudo.std(ddof=0) * np.sqrt(PERIODS_PER_YEAR))
        port_vol[t] = pv
        if pv <= 1e-9:
            continue
        w2 = w * (VOL_TARGET_PORTFOLIO / pv)
        gross = float(np.abs(w2).sum())
        if gross > GROSS_CAP:
            w2 = w2 * (GROSS_CAP / gross)
        final_vals[t] = w2

    final = pd.DataFrame(final_vals, index=close.index, columns=close.columns)
    return {"weights": final, "raw_weights": raw, "port_vol": pd.Series(port_vol, index=close.index)}


def strategy_returns(weights: pd.DataFrame, daily_ret: pd.DataFrame, cost: float) -> pd.Series:
    """PnL neto: la decisión tomada con info hasta el cierre de t (`weights`)
    se aplica al retorno de t+1 (`shift(1)`), con costos sobre turnover."""
    w_applied = weights.shift(1).fillna(0.0)
    return apply_costs(w_applied, daily_ret.fillna(0.0), cost)


# ---------------------------------------------------------------- diagnóstico

def exposure_diag(weights: pd.DataFrame, slices: list[tuple[int, int]]) -> list[dict]:
    """Exposición neta/bruta por fold: cuántos activos netos largos vs
    cortos en promedio, y el apalancamiento bruto máximo efectivamente
    usado (antes de aplicar shift, o sea el día en que se decide la
    posición)."""
    gross = weights.abs().sum(axis=1)
    n_long = (weights > 1e-9).sum(axis=1)
    n_short = (weights < -1e-9).sum(axis=1)
    rows = []
    for a, b in slices:
        rows.append({
            "n_long_avg": round(float(n_long.iloc[a:b].mean()), 2),
            "n_short_avg": round(float(n_short.iloc[a:b].mean()), 2),
            "gross_avg": round(float(gross.iloc[a:b].mean()), 2),
            "gross_max": round(float(gross.iloc[a:b].max()), 2),
        })
    return rows


def fold_metrics_rows(returns: pd.Series, slices: list[tuple[int, int]]) -> list[tuple[str, dict]]:
    return [(f"fold {i+1}", metrics(returns.iloc[a:b])) for i, (a, b) in enumerate(slices)]


# ---------------------------------------------------------------- una corrida completa (una semilla)

def run_seed(seed: int) -> dict:
    mk = load_market(SOURCE, seed=seed, n_days=N_DAYS, cache_dir=CACHE_DIR)
    close = mk.close
    daily_ret = close.pct_change()
    slices = fold_slices(len(close), N_FOLDS, warmup=WARMUP)

    out = {"n_days": len(close), "source": SOURCE, "period": describe(mk), "fold_slices": slices}

    variants = {"l90": [L_BASE], "ensemble": ENSEMBLE_LBS}
    bh = buy_and_hold(close, rebalance=True)
    out["buy_and_hold"] = {
        "folds": fold_metrics_rows(bh, slices),
        "aggregate": metrics(bh.iloc[WARMUP:]),
    }

    for vname, lbs in variants.items():
        built = build_weights(close, daily_ret, lbs)
        weights = built["weights"]
        gross_full = weights.abs().sum(axis=1).iloc[WARMUP:]
        avg_gross = float(gross_full.mean())

        vres = {
            "lookbacks": lbs,
            "avg_gross": round(avg_gross, 3),
            "max_gross": round(float(gross_full.max()), 3),
            "exposure_by_fold": exposure_diag(weights, slices),
            "costs": {},
        }
        for cost_name, cost in COSTS.items():
            ret = strategy_returns(weights, daily_ret, cost)
            vres["costs"][cost_name] = {
                "folds": fold_metrics_rows(ret, slices),
                "aggregate": metrics(ret.iloc[WARMUP:]),
            }

        # baseline aleatorio con exposición bruta comparable
        rb = random_baseline(close.index, close.columns, avg_gross=avg_gross, seed=seed)
        rb_applied = rb.shift(1).fillna(0.0)
        rb_costs = {}
        for cost_name, cost in COSTS.items():
            rret = apply_costs(rb_applied, daily_ret.fillna(0.0), cost)
            rb_costs[cost_name] = {
                "folds": fold_metrics_rows(rret, slices),
                "aggregate": metrics(rret.iloc[WARMUP:]),
            }
        vres["random_baseline"] = rb_costs

        out[vname] = vres

    return out


# ---------------------------------------------------------------- reporte

def print_report(results: dict) -> None:
    primary = results[PRIMARY_SEED]
    print(f"=== TSMOM absoluto diversificado + vol targeting (2 capas) ===")
    print(f"vol_objetivo_activo={VOL_TARGET_ASSET:.0%}  cap_activo={ASSET_LEVERAGE_CAP}  "
          f"vol_objetivo_portafolio={VOL_TARGET_PORTFOLIO:.0%}  cap_bruto={GROSS_CAP}")
    print(f"datos: {primary['period']}  folds={N_FOLDS}  warmup={WARMUP}  semillas={SEEDS}\n")

    print(f"--- buy&hold equiponderado (semilla {PRIMARY_SEED}) ---")
    print(fold_table(primary["buy_and_hold"]["folds"]))
    print("agregado:", primary["buy_and_hold"]["aggregate"], "\n")

    for vname, label in [("l90", "L=90 solo"), ("ensemble", f"ensemble {ENSEMBLE_LBS}")]:
        v = primary[vname]
        print(f"--- {label} (semilla {PRIMARY_SEED}) --- gross_prom={v['avg_gross']} gross_max={v['max_gross']}")
        for cost_name in COSTS:
            print(f"  [{cost_name}]")
            print(fold_table(v["costs"][cost_name]["folds"]))
            print("  agregado:", v["costs"][cost_name]["aggregate"])
            print("  [baseline aleatorio]", v["random_baseline"][cost_name]["aggregate"])
        print("  exposición por fold (n_long/n_short/gross_avg/gross_max):")
        for i, e in enumerate(v["exposure_by_fold"], 1):
            print(f"    fold {i}: {e}")
        print()

    for seed in SEEDS[1:]:
        r = results[seed]
        print(f"--- agregados semilla {seed} ---")
        for vname, label in [("l90", "L=90 solo"), ("ensemble", "ensemble")]:
            v = r[vname]
            for cost_name in COSTS:
                print(f"  {label} [{cost_name}]: {v['costs'][cost_name]['aggregate']}")
        print()


def slim_seed_result(seed_result: dict, full: bool) -> dict:
    """Recorta el resultado de una semilla para el JSON: detalle completo por
    fold solo cuando `full` (semilla primaria); si no, solo agregados."""
    out = {"n_days": seed_result["n_days"], "period": seed_result["period"], "source": seed_result["source"]}
    out["buy_and_hold"] = seed_result["buy_and_hold"] if full else {"aggregate": seed_result["buy_and_hold"]["aggregate"]}
    for vname in ("l90", "ensemble"):
        v = seed_result[vname]
        if full:
            out[vname] = v
        else:
            out[vname] = {
                "lookbacks": v["lookbacks"],
                "avg_gross": v["avg_gross"],
                "max_gross": v["max_gross"],
                "costs": {c: {"aggregate": v["costs"][c]["aggregate"]} for c in COSTS},
                "random_baseline": {c: {"aggregate": v["random_baseline"][c]["aggregate"]} for c in COSTS},
            }
    return out


def build_payload(results: dict) -> dict:
    return {
        "config": {
            "source": SOURCE, "n_days": N_DAYS, "n_folds": N_FOLDS, "warmup": WARMUP, "seeds": SEEDS,
            "L_base": L_BASE, "ensemble_lookbacks": ENSEMBLE_LBS,
            "vol_lookback": VOL_LOOKBACK, "vol_target_asset": VOL_TARGET_ASSET,
            "asset_leverage_cap": ASSET_LEVERAGE_CAP, "vol_target_portfolio": VOL_TARGET_PORTFOLIO,
            "gross_cap": GROSS_CAP, "cost_conservative": COST_CONSERVATIVE, "cost_realistic": COST_REALISTIC,
        },
        "seeds": {
            str(seed): slim_seed_result(res, full=(seed == PRIMARY_SEED)) for seed, res in results.items()
        },
    }


def main() -> None:
    global SOURCE, CACHE_DIR, SEEDS, PRIMARY_SEED
    cfg = parse_cli("Prueba D: TSMOM absoluto diversificado + vol targeting")
    SOURCE, CACHE_DIR, SEEDS = cfg.source, cfg.cache_dir, list(cfg.seeds)
    PRIMARY_SEED = SEEDS[0]
    print(f"Fuente de datos: {cfg.label}")
    results = {seed: run_seed(seed) for seed in SEEDS}
    print_report(results)

    payload = build_payload(results)

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "tsmom_vt_results.json")
    out_path = os.path.normpath(cfg.results_path(out_path))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nResultados guardados en {out_path}")


if __name__ == "__main__":
    main()
