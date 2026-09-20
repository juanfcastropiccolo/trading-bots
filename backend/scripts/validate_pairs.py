"""Validación de relative-value / pairs trading (Prueba B) sobre el mercado
sintético multi-activo de `synthetic_market.py`.

Mecánica (mean-reversion de un SPREAD, no direccional):
  1. Screening walk-forward, sin lookahead: para cada uno de los 6 tramos
     out-of-sample (definidos con `fold_slices`, ventana expandiente en el
     sentido de que cada tramo posterior tiene más historia disponible),
     se recalcula la selección de pares usando ÚNICAMENTE la ventana rolling
     de `CORR_WINDOW` días INMEDIATAMENTE ANTERIOR al inicio del tramo:
       a) correlación de retornos diarios sobre esos `CORR_WINDOW` días →
          top-`TOP_M` por correlación (preselección barata sobre los 45
          pares posibles).
       b) para cada preseleccionado: hedge ratio por OLS de log(close_A)
          contra log(close_B) en la misma ventana, spread = log(A) −
          hedge_ratio·log(B), coeficiente AR(1) del spread y half-life
          implícito. Se retienen los pares con half-life en `[HL_MIN,
          HL_MAX]` días — el criterio de "cointegración creíble".
     Nota sobre "ventana rolling de 250d" vs. "expandiente": el enunciado
     pide ambas cosas y no son lo mismo. Se resuelve así: la selección en
     sí SIEMPRE usa el tramo de 250 días más reciente (cointegración es
     inestable en el tiempo; una ventana de 6 años mezclaría regímenes de
     hedge ratio distintos), pero el conjunto de datos disponible para
     elegir ESA ventana crece (se "expande") tramo a tramo, y en ningún
     caso se toca el tramo evaluado ni el futuro. `screen_pairs()` nunca
     referencia `COINTEGRATED_PAIRS`: la selección es ciega a la respuesta.
  2. Trading, durante el tramo OOS, con los pares congelados hasta el
     próximo re-screening:
       - z-score del spread sobre rolling de `Z_WINDOW` días.
       - entra largo-de-spread (largo A, corto B) si z < -`Z_ENTRY`;
         corto-de-spread si z > `Z_ENTRY`; cierra si |z| < `Z_EXIT` o tras
         `MAX_HOLD` días en la posición.
       - pesos de las dos patas proporcionales al hedge ratio, normalizados
         para que la exposición bruta del PAR sea `1 / n_pares_del_tramo`
         cuando está activo (o sea, exposición bruta ≤ 1.0 si TODOS los
         pares del tramo estuvieran simultáneamente activos).
       - decisión con información hasta el cierre de t, aplicada al retorno
         de t+1 (igual convención que `backtest_common.apply_costs`: acá
         se arma la señal causal día a día y se hace UN solo `shift(1)`
         antes de pasarla a `apply_costs`, igual que en
         `validate_ls_momentum.py`).
  3. Versión "oráculo": mismos mecanismos de estimación y trading, pero SIN
     screening — siempre opera los 3 `COINTEGRATED_PAIRS` verdaderos, con
     hedge ratio re-estimado cada tramo (sigue habiendo riesgo de parámetro,
     cero riesgo de selección). Es la cota superior de referencia.

Uso:  python validate_pairs.py
"""
from __future__ import annotations

import itertools
import json
import os

import numpy as np
import pandas as pd

from synthetic_market import COINTEGRATED_PAIRS, SYMBOLS
from market_data import describe, load_market, parse_cli
from backtest_common import (COST_CONSERVATIVE, COST_REALISTIC, apply_costs,
                              buy_and_hold, fold_slices, fold_table, metrics,
                              random_baseline)

SEEDS = [42, 7, 123]
N_DAYS = 2190
N_FOLDS = 6
CORR_WINDOW = 250              # ventana de correlación / hedge ratio / AR1
WARMUP = CORR_WINDOW + 10      # margen para que el tramo 1 ya tenga ventana completa
TOP_M = 10                     # preselección por correlación antes del filtro de half-life
HL_MIN, HL_MAX = 5.0, 90.0     # banda de half-life "creíble" (documentada arriba)
Z_WINDOW = 60
Z_ENTRY = 2.0
Z_EXIT = 0.5
MAX_HOLD = 30
COSTS = {"conservador_0.15%": COST_CONSERVATIVE, "realista_0.05%": COST_REALISTIC}

TRUE_PAIRS = {frozenset(p) for p in COINTEGRATED_PAIRS}
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "pairs_results.json")

SOURCE = "synthetic"     # market_data: 'synthetic' | 'real' (se fija desde la CLI en main)
CACHE_DIR = None         # cache de futures_data para --source real


# ---------------------------------------------------------------- screening

def _ols_hedge_ratio(y: np.ndarray, x: np.ndarray) -> float:
    """Pendiente de y = a + b*x por mínimos cuadrados (b = hedge ratio)."""
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(coef[1])


def _ar1_half_life(spread: np.ndarray) -> tuple[float, float]:
    """AR(1) de `spread` (regresión spread_t = a + b*spread_{t-1}) y su
    half-life implícito (inf si no hay reversión, 0<b<1)."""
    s_lag, s_now = spread[:-1], spread[1:]
    X = np.column_stack([np.ones_like(s_lag), s_lag])
    coef, *_ = np.linalg.lstsq(X, s_now, rcond=None)
    ar1 = float(coef[1])
    half_life = float(np.log(2) / -np.log(ar1)) if 0 < ar1 < 1 else float("inf")
    return ar1, half_life


def screen_pairs(log_close: pd.DataFrame, ret: pd.DataFrame, as_of: int, *,
                  corr_window: int = CORR_WINDOW, top_m: int = TOP_M,
                  hl_min: float = HL_MIN, hl_max: float = HL_MAX) -> list[dict]:
    """Selecciona pares usando SOLO `ret`/`log_close` en `[as_of-corr_window,
    as_of)`: información estrictamente anterior al tramo que arranca en
    `as_of`. Nunca mira `as_of` en adelante. Ciega a `COINTEGRATED_PAIRS`."""
    start = as_of - corr_window
    if start < 0:
        raise ValueError("warmup insuficiente para la ventana de correlación")
    corr = ret.iloc[start:as_of].corr()
    symbols = list(log_close.columns)

    scored = [(a, b, float(corr.loc[a, b])) for a, b in itertools.combinations(symbols, 2)]
    scored.sort(key=lambda t: -t[2])  # top por correlación (no por |corr|): buscamos co-movimiento positivo
    preselected = scored[:top_m]

    chosen = []
    for a, b, c in preselected:
        y = log_close[a].iloc[start:as_of].values
        x = log_close[b].iloc[start:as_of].values
        hedge_ratio = _ols_hedge_ratio(y, x)
        spread = y - hedge_ratio * x
        ar1, half_life = _ar1_half_life(spread)
        if hl_min <= half_life <= hl_max:
            chosen.append({"a": a, "b": b, "corr": c, "hedge_ratio": hedge_ratio,
                            "ar1": ar1, "half_life": half_life})
    return chosen


# ---------------------------------------------------------------- trading

def _pair_positions(spread: np.ndarray, *, entry: float = Z_ENTRY, exit_z: float = Z_EXIT,
                     max_hold: int = MAX_HOLD, z_window: int = Z_WINDOW) -> np.ndarray:
    """Estado {-1,0,+1} día a día a partir del z-score rolling del spread.
    +1 = largo-de-spread (largo A, corto B); -1 = corto-de-spread."""
    s = pd.Series(spread)
    roll_mean = s.rolling(z_window, min_periods=z_window).mean()
    roll_std = s.rolling(z_window, min_periods=z_window).std(ddof=0).replace(0, np.nan)
    z = ((s - roll_mean) / roll_std).to_numpy()

    pos = np.zeros(len(z), dtype=int)
    cur, held = 0, 0
    for t in range(len(z)):
        zt = z[t]
        if np.isnan(zt):
            pos[t] = cur
            continue
        if cur == 0:
            if zt < -entry:
                cur, held = 1, 1
            elif zt > entry:
                cur, held = -1, 1
        else:
            held += 1
            if abs(zt) < exit_z or held >= max_hold:
                cur, held = 0, 0
        pos[t] = cur
    return pos


def build_tramp_weights(log_close: pd.DataFrame, pairs: list[dict], start: int, end: int,
                         z_window: int = Z_WINDOW) -> np.ndarray:
    """Pesos (end-start x n_símbolos) para un tramo OOS. El estado de cada
    par arranca en `flat` exactamente en `start` (se incluye un buffer de
    `z_window` días PREVIOS a `start` solo para calentar la ventana rolling
    del z-score con datos ya conocidos; la máquina de estados no toma
    decisiones ahí porque el z-score es NaN hasta completar la ventana)."""
    symbols = list(log_close.columns)
    idx = {s: i for i, s in enumerate(symbols)}
    w = np.zeros((end - start, len(symbols)))
    n_pairs = len(pairs)
    if n_pairs == 0:
        return w
    ctx_start = start - z_window
    if ctx_start < 0:
        raise ValueError("warmup insuficiente para el buffer del z-score")

    for p in pairs:
        a, b, h = p["a"], p["b"], p["hedge_ratio"]
        logA = log_close[a].iloc[ctx_start:end].to_numpy()
        logB = log_close[b].iloc[ctx_start:end].to_numpy()
        spread = logA - h * logB
        pos_full = _pair_positions(spread, z_window=z_window)
        pos = pos_full[z_window:]  # recorta el buffer: pos[0] == día `start`
        leg_a = 1.0 / (1.0 + abs(h)) / n_pairs
        leg_b = -h / (1.0 + abs(h)) / n_pairs
        w[:, idx[a]] += pos * leg_a
        w[:, idx[b]] += pos * leg_b
    return w


# ---------------------------------------------------------------- orquestación

def run_variant(log_close: pd.DataFrame, ret: pd.DataFrame, folds: list[tuple[int, int]],
                 *, use_screening: bool) -> tuple[pd.DataFrame, list[dict]]:
    symbols = list(log_close.columns)
    n = len(log_close)
    weights = np.zeros((n, len(symbols)))
    diag = []

    for k, (start, end) in enumerate(folds):
        if use_screening:
            pairs = screen_pairs(log_close, ret, start)
        else:
            pairs = []
            for a, b in COINTEGRATED_PAIRS:
                y = log_close[a].iloc[start - CORR_WINDOW:start].to_numpy()
                x = log_close[b].iloc[start - CORR_WINDOW:start].to_numpy()
                pairs.append({"a": a, "b": b, "hedge_ratio": _ols_hedge_ratio(y, x)})

        diag.append({
            "fold": k, "start": start, "end": end,
            "pairs": [{"a": p["a"], "b": p["b"], "hedge_ratio": round(p["hedge_ratio"], 4),
                       **({"corr": round(p["corr"], 4), "half_life": round(p["half_life"], 1)}
                          if "corr" in p else {})}
                      for p in pairs],
        })
        weights[start:end, :] += build_tramp_weights(log_close, pairs, start, end)

    return pd.DataFrame(weights, index=log_close.index, columns=symbols), diag


def match_stats(diag: list[dict]) -> list[dict]:
    out = []
    for d in diag:
        chosen = {frozenset((p["a"], p["b"])) for p in d["pairs"]}
        tp, fn, fp = chosen & TRUE_PAIRS, TRUE_PAIRS - chosen, chosen - TRUE_PAIRS
        out.append({"fold": d["fold"],
                     "n_chosen": len(chosen),
                     "true_positives": sorted(tuple(sorted(s)) for s in tp),
                     "false_negatives": sorted(tuple(sorted(s)) for s in fn),
                     "false_positives": sorted(tuple(sorted(s)) for s in fp)})
    return out


def evaluate(weights_df: pd.DataFrame, ret: pd.DataFrame, folds: list[tuple[int, int]]) -> dict:
    shifted = weights_df.shift(1).fillna(0)  # única aplicación del shift: señal de t -> retorno de t+1
    combined_start, combined_end = folds[0][0], folds[-1][1]
    out = {}
    for cost_name, cost in COSTS.items():
        net = apply_costs(shifted, ret, cost)
        out[cost_name] = {
            "per_fold": [metrics(net.iloc[s:e]) for s, e in folds],
            "agg": metrics(net.iloc[combined_start:combined_end]),
        }
    return out


def _tuple_lists(d):
    """Convierte tuplas anidadas a listas para que json.dump no falle."""
    if isinstance(d, tuple):
        return list(d)
    if isinstance(d, list):
        return [_tuple_lists(x) for x in d]
    if isinstance(d, dict):
        return {k: _tuple_lists(v) for k, v in d.items()}
    return d


def run_seed(seed: int) -> dict:
    mk = load_market(SOURCE, seed=seed, n_days=N_DAYS, cache_dir=CACHE_DIR)
    close = mk.close
    log_close = np.log(close)
    ret = close.pct_change()
    folds = fold_slices(len(close), N_FOLDS, warmup=WARMUP)
    combined_start, combined_end = folds[0][0], folds[-1][1]

    w_screen, diag_screen = run_variant(log_close, ret, folds, use_screening=True)
    ev_screen = evaluate(w_screen, ret, folds)
    # el oráculo (operar los 3 pares cointegrados por construcción) solo existe
    # en el mercado sintético: con datos reales nadie sabe cuáles son los pares
    oracle = None
    if SOURCE == "synthetic":
        w_oracle, diag_oracle = run_variant(log_close, ret, folds, use_screening=False)
        ev_oracle = evaluate(w_oracle, ret, folds)
        oracle = {"pairs_by_fold": diag_oracle, "metrics": ev_oracle,
                  "avg_gross": float(w_oracle.iloc[combined_start:combined_end].abs().sum(axis=1).mean())}

    bh_metrics = metrics(buy_and_hold(close, rebalance=True).iloc[combined_start:combined_end])

    avg_gross_screen = float(w_screen.iloc[combined_start:combined_end].abs().sum(axis=1).mean())
    ret_span = ret.iloc[combined_start:combined_end]
    rb_weights = random_baseline(close.index[combined_start:combined_end], close.columns,
                                  avg_gross_screen, seed)
    rb_shifted = rb_weights.shift(1).fillna(0)
    rb_metrics = {cost_name: metrics(apply_costs(rb_shifted, ret_span, cost))
                  for cost_name, cost in COSTS.items()}

    return {
        "seed": seed,
        "source": SOURCE,
        "period": describe(mk),
        "n_days": len(close),
        "folds": [{"start": s, "end": e} for s, e in folds],
        "screening": {"pairs_by_fold": diag_screen,
                      "match_stats": match_stats(diag_screen) if SOURCE == "synthetic" else None,
                      "metrics": ev_screen, "avg_gross": avg_gross_screen},
        "oracle": oracle,
        "buy_and_hold": bh_metrics,
        "random_baseline": rb_metrics,
    }


def main():
    global SOURCE, CACHE_DIR, SEEDS
    cfg = parse_cli("Prueba B: relative value / pairs trading")
    SOURCE, CACHE_DIR, SEEDS = cfg.source, cfg.cache_dir, list(cfg.seeds)
    data_path = cfg.results_path(DATA_PATH)
    print("=== Prueba B: relative value / pairs trading (spread mean-reversion) ===")
    print(f"Fuente: {cfg.label}; {len(SYMBOLS)} activos, semillas {SEEDS}")
    print(f"Screening: ventana corr/hedge/AR1={CORR_WINDOW}d, top-{TOP_M} por correlación, "
          f"banda half-life=[{HL_MIN:.0f},{HL_MAX:.0f}]d")
    print(f"Trading: z-window={Z_WINDOW}d, entrada |z|>{Z_ENTRY}, salida |z|<{Z_EXIT} o {MAX_HOLD}d en posición")
    print(f"Pares verdaderos (NO usados por el screening, solo para reportar al final): {COINTEGRATED_PAIRS}\n")

    all_results = {}
    for seed in SEEDS:
        res = run_seed(seed)
        all_results[str(seed)] = res

        print(f"--- semilla {seed} --- datos: {res['period']}")
        ms_list = res["screening"]["match_stats"] or [None] * len(res["screening"]["pairs_by_fold"])
        for d, ms in zip(res["screening"]["pairs_by_fold"], ms_list):
            elegidos = [(p["a"], p["b"], p.get("half_life")) for p in d["pairs"]]
            print(f"  tramo {d['fold'] + 1} [{d['start']}:{d['end']}] elegidos={elegidos}")
            if ms is not None:
                print(f"    verdaderos encontrados: {ms['true_positives']} | no encontrados: {ms['false_negatives']} | "
                      f"otros elegidos (no verdaderos): {ms['false_positives']}")

        if seed == SEEDS[0]:
            for cost_name in COSTS:
                rows = [(f"tramo{k + 1}", res["screening"]["metrics"][cost_name]["per_fold"][k])
                        for k in range(N_FOLDS)] + [("AGREGADO", res["screening"]["metrics"][cost_name]["agg"])]
                print(f"\n  [SCREENING] costo {cost_name}\n" + fold_table(rows))
                if res["oracle"] is not None:
                    rows_o = [(f"tramo{k + 1}", res["oracle"]["metrics"][cost_name]["per_fold"][k])
                              for k in range(N_FOLDS)] + [("AGREGADO", res["oracle"]["metrics"][cost_name]["agg"])]
                    print(f"\n  [ORÁCULO] costo {cost_name}\n" + fold_table(rows_o))
            print(f"\n  buy&hold equiponderado (mismo span OOS): {res['buy_and_hold']}")
            print(f"  random baseline (avg_gross={res['screening']['avg_gross']:.3f}): {res['random_baseline']}\n")
        else:
            print(f"  [screening agregado realista] {res['screening']['metrics']['realista_0.05%']['agg']}")
            if res["oracle"] is not None:
                print(f"  [oráculo agregado realista]   {res['oracle']['metrics']['realista_0.05%']['agg']}\n")

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    payload = {
        "config": {"source": SOURCE, "n_days": N_DAYS, "n_folds": N_FOLDS, "warmup": WARMUP, "corr_window": CORR_WINDOW,
                   "top_m": TOP_M, "hl_min": HL_MIN, "hl_max": HL_MAX, "z_window": Z_WINDOW,
                   "z_entry": Z_ENTRY, "z_exit": Z_EXIT, "max_hold": MAX_HOLD, "seeds": SEEDS,
                   "costs": COSTS},
        "true_pairs": [list(p) for p in COINTEGRATED_PAIRS],
        "seeds": all_results,
    }
    with open(data_path, "w") as f:
        json.dump(_tuple_lists(payload), f, indent=2, default=float)
    print(f"Resultados guardados en {data_path}")


if __name__ == "__main__":
    main()
