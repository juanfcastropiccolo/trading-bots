"""Validación de carry cross-sectional de funding, dollar-neutral (Prueba C).

Eje distinto de momentum/reversión de precio: acá la apuesta es al PREMIO POR
MANTENER RIESGO (funding), no a la dirección del precio. Mercado sintético
(`synthetic_market.py`, ver ese archivo para por qué es sintético y qué
propiedades tiene el funding simulado) porque este entorno no tiene salida de
red hacia ningún exchange.

Mecánica:
  - Señal: media móvil de 7 días del funding diario de cada activo
    (`funding_trend`), calculada con información hasta el cierre de t.
  - Cartera dollar-neutral: cada `REBAL_DAYS` días se recalcula el ranking
    cross-sectional de `funding_trend` y se arma la cartera; entre
    rebalanceos el peso se mantiene fijo (no se re-arma a diario: la señal
    se mueve lento -ewm halflife=5 sobre el retorno más ruido AR(1) rho=0.9-
    y rebalancear a diario solo pagaría turnover sin cambiar de opinión).
    Short en los K activos con funding_trend más alto (funding positivo alto
    -> los longs pagan mucho -> conviene ser el short que cobra), long en
    los K con funding_trend más bajo/más negativo (los shorts pagan ->
    conviene ser el long que cobra). Equiponderado dentro de cada pata,
    bruto ~2.0 (1.0 largo + 1.0 corto), neto ~0.
  - Sin lookahead: la señal usa funding hasta el cierre de t; la posición
    resultante (peso "crudo", decidido en la fila t) se aplica recién al
    PnL de t+1 vía `weights.shift(1)`, exactamente como en
    `validate_ls_momentum.py` (w_prev = weights.shift(1)).
  - PnL con signo (misma convención que futures_data.py / validate_ls_momentum.py,
    funding positivo = los longs pagan a los shorts):
        pnl_i,t+1 = w_i,t * retorno_precio_i,t+1  -  w_i,t * funding_i,t+1
    Con w>0 (largo) y funding>0 el segundo término resta (el largo paga).
    Con w<0 (corto) y funding>0 el segundo término suma (el corto cobra).
  - Descomposición del PnL total en componente de PRECIO (sum w*retorno) y
    componente de FUNDING (sum -w*funding) -- el corazón de esta prueba:
    ¿el resultado es carry real (componente de funding positivo y
    consistente) o una apuesta direccional disfrazada (depende del
    componente de precio)?
  - Control: misma señal pero SIN la pata larga compensadora (solo corto en
    high-funding), para cuantificar cuánto beta direccional agrega no ser
    dollar-neutral.

Uso:  python scripts/validate_carry.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from backtest_common import (COST_CONSERVATIVE, COST_REALISTIC, apply_costs,
                             buy_and_hold, fold_slices, fold_table, metrics,
                             random_baseline)
from synthetic_market import generate_market

N_DAYS = 2190          # ~6 años
N_FOLDS = 6
WARMUP = 30            # > ventana de la señal (7d); deja además algunos
                       # rebalanceos "asentados" antes de que arranque el fold 1
FUNDING_WINDOW = 7     # días de la media móvil de funding (la señal)
REBAL_DAYS = 7         # cadencia de rebalanceo (semanal)
K = 3                  # activos por pata
SEEDS = [42, 7, 123]
COSTS = {"conservador_0.15%": COST_CONSERVATIVE, "realista_0.05%": COST_REALISTIC}
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "carry_results.json")


# --------------------------------------------------------------- señal / pesos

def funding_trend(funding: pd.DataFrame, window: int = FUNDING_WINDOW) -> pd.DataFrame:
    """Media móvil causal de `window` días del funding diario: la fila t usa
    solo funding hasta el cierre de t (rolling, sin shift adicional acá --
    el shift se aplica después, sobre los PESOS, en `build_weights`)."""
    return funding.rolling(window, min_periods=window).mean()


def _rebalance_grid(n: int, rebal_days: int, warmup: int) -> list[bool]:
    return [i >= warmup and (i - warmup) % rebal_days == 0 for i in range(n)]


def build_weights(trend: pd.DataFrame, k: int = K, rebal_days: int = REBAL_DAYS,
                  warmup: int = WARMUP, neutral: bool = True) -> pd.DataFrame:
    """Pesos CRUDOS (decididos con información hasta el cierre de la fila i;
    el llamador debe hacer `.shift(1)` antes de aplicarlos a retornos, igual
    que `validate_ls_momentum.py`). Se recalcula el ranking solo en los días
    de rebalanceo; el resto de los días el peso queda fijo (`current`)."""
    cols = trend.columns
    weights = pd.DataFrame(0.0, index=trend.index, columns=cols)
    current = pd.Series(0.0, index=cols)
    grid = _rebalance_grid(len(trend), rebal_days, warmup)
    for i in range(len(trend)):
        if grid[i]:
            row = trend.iloc[i].dropna()
            if len(row) >= 2 * k:
                ranked = row.sort_values(ascending=False)   # funding más alto primero
                shorts = ranked.index[:k]                    # funding alto -> corto (cobra)
                longs = ranked.index[-k:]                    # funding bajo/negativo -> largo (cobra)
                current = pd.Series(0.0, index=cols)
                for s in shorts:
                    current[s] -= 1.0 / k
                if neutral:
                    for s in longs:
                        current[s] += 1.0 / k
        weights.iloc[i] = current
    return weights


# --------------------------------------------------------------- pnl

def portfolio_returns(weights_raw: pd.DataFrame, price_ret: pd.DataFrame,
                      funding: pd.DataFrame, cost_per_side: float) -> dict:
    """Aplica el shift causal (peso decidido en t -> PnL de t+1) y devuelve
    la descomposición precio/funding + el retorno neto de costos.

    pnl_i,t+1 = w_i,t*retorno_i,t+1 - w_i,t*funding_i,t+1 (funding positivo
    = el largo paga), con w_prev = weights_raw.shift(1) representando esa
    posición decidida en t y recién efectiva en t+1.
    """
    w_prev = weights_raw.shift(1).fillna(0)
    price_component = (w_prev * price_ret).sum(axis=1)
    funding_component = (-w_prev * funding).sum(axis=1)
    combined = price_ret - funding
    net = apply_costs(w_prev, combined, cost_per_side)
    gross = price_component + funding_component
    turnover = w_prev.fillna(0).diff().abs().sum(axis=1)
    turnover.iloc[0] = w_prev.iloc[0].abs().sum()
    return {"w_prev": w_prev, "price": price_component, "funding": funding_component,
            "gross": gross, "net": net, "turnover": turnover}


# --------------------------------------------------------------- reporte

def _decomp_row(price: pd.Series, funding: pd.Series) -> dict:
    p, f = float(price.sum()), float(funding.sum())
    total = p + f
    share = f / total if abs(total) > 1e-12 else float("nan")
    return {"precio_sum": round(p, 4), "funding_sum": round(f, 4),
            "total_sum": round(total, 4), "funding_share": round(share, 4) if share == share else None}


def run_seed(seed: int) -> dict:
    mk = generate_market(n_days=N_DAYS, seed=seed)
    price_ret = mk.close.pct_change().fillna(0.0)
    trend = funding_trend(mk.funding)
    idx = mk.close.index
    folds = fold_slices(len(idx), N_FOLDS, warmup=WARMUP)

    w_neutral = build_weights(trend, neutral=True)
    w_directional = build_weights(trend, neutral=False)

    out = {"seed": seed, "warmup": WARMUP, "folds": [(int(a), int(b)) for a, b in folds],
          "dollar_neutral": {}, "sin_neutralizar": {}, "benchmarks": {}}

    for cost_label, cost in COSTS.items():
        res_n = portfolio_returns(w_neutral, price_ret, mk.funding, cost)
        res_d = portfolio_returns(w_directional, price_ret, mk.funding, cost)

        fold_m_n, decomp_n = [], []
        for i, (a, b) in enumerate(folds):
            seg = res_n["net"].iloc[a:b]
            fold_m_n.append((f"Fold {i + 1}", metrics(seg)))
            decomp_n.append({"fold": i + 1, **_decomp_row(res_n["price"].iloc[a:b], res_n["funding"].iloc[a:b])})
        agg_n = metrics(res_n["net"].iloc[WARMUP:])
        fold_m_n.append(("Agregado", agg_n))
        decomp_agg_n = _decomp_row(res_n["price"].iloc[WARMUP:], res_n["funding"].iloc[WARMUP:])

        fold_m_d, decomp_d = [], []
        for i, (a, b) in enumerate(folds):
            seg = res_d["net"].iloc[a:b]
            fold_m_d.append((f"Fold {i + 1}", metrics(seg)))
        agg_d = metrics(res_d["net"].iloc[WARMUP:])
        fold_m_d.append(("Agregado", agg_d))
        decomp_agg_d = _decomp_row(res_d["price"].iloc[WARMUP:], res_d["funding"].iloc[WARMUP:])

        out["dollar_neutral"][cost_label] = {
            "fold_metrics": {name: m for name, m in fold_m_n},
            "fold_table": fold_table(fold_m_n),
            "decomposicion_por_fold": decomp_n,
            "decomposicion_agregada": decomp_agg_n,
            "avg_gross": round(float(res_n["w_prev"].abs().sum(axis=1).iloc[WARMUP:].mean()), 4),
            "avg_net": round(float(res_n["w_prev"].sum(axis=1).iloc[WARMUP:].mean()), 4),
        }
        out["sin_neutralizar"][cost_label] = {
            "fold_metrics": {name: m for name, m in fold_m_d},
            "fold_table": fold_table(fold_m_d),
            "decomposicion_agregada": decomp_agg_d,
            "avg_gross": round(float(res_d["w_prev"].abs().sum(axis=1).iloc[WARMUP:].mean()), 4),
            "avg_net": round(float(res_d["w_prev"].sum(axis=1).iloc[WARMUP:].mean()), 4),
        }

    # benchmarks: buy&hold (sin costo, es la referencia) y baseline aleatorio
    # con exposición bruta comparable (2.0, igual que la pata dollar-neutral)
    bh = buy_and_hold(mk.close, rebalance=True)
    rb_weights = random_baseline(idx, mk.close.columns, avg_gross=2.0, seed=seed)
    rb_combined = price_ret - mk.funding
    out["benchmarks"]["buy_and_hold"] = metrics(bh.iloc[WARMUP:])
    for cost_label, cost in COSTS.items():
        rb_net = apply_costs(rb_weights, rb_combined, cost)
        out["benchmarks"].setdefault("random_baseline_gross2.0", {})[cost_label] = metrics(rb_net.iloc[WARMUP:])

    # correlación de los retornos netos (realista) con buy&hold: mide cuánto
    # beta direccional queda en cada variante
    net_n_realistic = portfolio_returns(w_neutral, price_ret, mk.funding, COST_REALISTIC)["net"]
    net_d_realistic = portfolio_returns(w_directional, price_ret, mk.funding, COST_REALISTIC)["net"]
    out["correlacion_con_buy_and_hold"] = {
        "dollar_neutral": round(float(net_n_realistic.iloc[WARMUP:].corr(bh.iloc[WARMUP:])), 4),
        "sin_neutralizar": round(float(net_d_realistic.iloc[WARMUP:].corr(bh.iloc[WARMUP:])), 4),
    }
    return out


def main():
    results = {"params": {"n_days": N_DAYS, "n_folds": N_FOLDS, "warmup": WARMUP,
                          "funding_window": FUNDING_WINDOW, "rebal_days": REBAL_DAYS,
                          "k": K, "seeds": SEEDS, "costs": COSTS},
              "seeds": {}}
    for seed in SEEDS:
        print(f"\n{'=' * 70}\nSEED {seed}\n{'=' * 70}")
        r = run_seed(seed)
        results["seeds"][str(seed)] = r

        for cost_label in COSTS:
            dn = r["dollar_neutral"][cost_label]
            print(f"\n-- dollar-neutral [{cost_label}] gross={dn['avg_gross']} net={dn['avg_net']} --")
            print(dn["fold_table"])
            d = dn["decomposicion_agregada"]
            print(f"  descomposición agregada: precio={d['precio_sum']:+.4f}  "
                  f"funding={d['funding_sum']:+.4f}  total={d['total_sum']:+.4f}  "
                  f"funding_share={d['funding_share']}")

        print(f"\n-- buy&hold -- {r['benchmarks']['buy_and_hold']}")
        print(f"-- corr con buy&hold: neutral={r['correlacion_con_buy_and_hold']['dollar_neutral']} "
              f"sin_neutralizar={r['correlacion_con_buy_and_hold']['sin_neutralizar']} --")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResultados guardados en {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    main()
