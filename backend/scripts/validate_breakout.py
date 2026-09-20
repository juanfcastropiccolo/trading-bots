"""Prueba A: ruptura de canal (Donchian dual, estilo turtle) + sizing por ATR.

Construcción trend-following DISCRETA (entra/sale por umbral, no un score
continuo como momentum): para cada uno de los 10 activos, INDEPENDIENTEMENTE
(sin ranking cross-sectional ni rotación entre activos):

  - Canal de Donchian dual (estilo turtle system 1+2):
        upper_N = high.rolling(N).max().shift(1)
        lower_N = low.rolling(N).min().shift(1)
    con N_rapido=20 y N_lento=55. El `.shift(1)` es sobre el canal en sí (no
    sobre el precio): el canal "de hoy" resume [t-N, t-1], así que compararlo
    contra el close de HOY sigue siendo causal (toda la información usada
    -close de hoy y canal de ayer para atrás- está disponible al cierre de
    hoy; la posición decidida hoy se aplica al retorno de MAÑANA vía el
    shift(1) de pesos que hace `backtest_common.apply_costs`).

  - Entrada (estando flat): close de hoy rompe upper_fast o upper_slow ->
    largo; rompe lower_fast o lower_slow -> corto. Se guarda qué canal
    disparó la entrada (`entry_n` = 20 o 55) porque de eso depende cuál es
    la "banda opuesta" de salida.

  - Reversión: si ya hay posición y el precio rompe el canal CONTRARIO
    (p.ej. estando largo, close < lower_fast o close < lower_slow), se
    invierte directo (cierra la posición vieja y abre la nueva en la misma
    vela) en vez de esperar a que el trailing stop dispare por separado.
    Esto es una elección de diseño explícita del "sistema dual": tratamos
    las dos rupturas (20 y 55) como una sola señal direccional por activo,
    no dos sistemas que se puedan pisar entre sí.

  - Salida (sin reversión): trailing stop por ATR con k=3 desde el extremo
    (máximo/mínimo del CLOSE, no del high/low intradía —no hay granularidad
    intradía en el mercado sintético de velas diarias para saber si el stop
    se hubiese tocado antes de un nuevo extremo en la misma vela) alcanzado
    desde la entrada, O tocar la banda opuesta del MISMO canal que disparó
    la entrada (si entró por ruptura de 20, sale por el lower/upper de 20;
    si entró por ruptura de 55, sale por el de 55) — lo que ocurra primero.

  - ATR(14) en nivel de precio con true range clásico:
        TR_t = max(high_t - low_t, |high_t - close_{t-1}|, |low_t - close_{t-1}|)
        ATR_t = media móvil de 14 de TR_t
    (causal: TR_t usa el close de AYER para las dos últimas ramas, y el
    high/low de HOY, que ya están cerrados al momento de decidir con el
    close de hoy).

  - Sizing por riesgo: peso_i = riesgo_objetivo / (ATR_i(t)/close_i(t)),
    es decir arriesgar una fracción fija `riesgo_objetivo` de capital por
    cada unidad de ATR (a más volátil el activo, menor el peso). Se
    recalcula TODOS los días que la posición sigue abierta (no se fija en
    el momento de entrada) para reflejar el riesgo corriente; es una
    simplificación respecto del turtle original documentada acá. Cap por
    activo |w_i|<=0.5 y cap de exposición bruta total sum|w_i|<=3.0
    (si el bruto del día supera 3.0 se escala todo el vector de pesos del
    día hacia abajo proporcionalmente, no se recorta activo por activo).

  Elección de `riesgo_objetivo` (a priori, sin optimizar sobre el resultado
  final): con el ATR medio de este mercado sintético (~4%-7.5% del precio
  según el activo), riesgo_objetivo=0.01 da una exposición bruta media
  ~1.5x con el cap de 3.0 activo en <0.2% de los días (ver
  `_elegir_riesgo_objetivo` más abajo, corrida una sola vez sobre la
  semilla 42 como referencia). riesgo_objetivo=0.02 satura el cap de bruto
  ~43% de los días (deja de ser "sizing por riesgo" y pasa a ser "bruto
  fijo recortado"); riesgo_objetivo=0.005 es demasiado conservador (bruto
  medio 0.74x, casi nunca usa el cap). Nos quedamos con 0.01.

Toda la señal (canales, ATR, extremo del trailing) se calcula con
información disponible al cierre de t; el peso decidido en t se aplica al
retorno de t+1 (convención de `backtest_common.apply_costs`: el llamador
pasa pesos YA shifteados).

Uso:  python validate_breakout.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from backtest_common import (COST_CONSERVATIVE, COST_REALISTIC, PERIODS_PER_YEAR,
                              apply_costs, buy_and_hold, fold_slices, fold_table,
                              metrics, random_baseline)
from synthetic_market import SYMBOLS, generate_market

N_FAST = 20
N_SLOW = 55
ATR_N = 14
K_TRAIL = 3.0
RISK_TARGET = 0.01     # ver docstring del módulo: elegido a priori sobre semilla 42
CAP_ASSET = 0.5
CAP_GROSS = 3.0
N_FOLDS = 6
WARMUP = N_SLOW + 5     # margen sobre el canal más lento (55)
N_DAYS = 2190
SEEDS = (42, 7, 123)
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "breakout_results.json")


# ---------------------------------------------------------------- señales

def true_range(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """True range clásico, causal (usa el close de ayer, ya conocido)."""
    prev_close = close.shift(1)
    tr = np.maximum(np.maximum((high - low).to_numpy(),
                                (high - prev_close).abs().to_numpy()),
                     (low - prev_close).abs().to_numpy())
    return pd.DataFrame(tr, index=close.index, columns=close.columns)


def compute_channels_and_atr(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                              n_fast: int = N_FAST, n_slow: int = N_SLOW, atr_n: int = ATR_N):
    """Canales de Donchian (shifteados sobre sí mismos, ver docstring del
    módulo) y ATR en nivel de precio. Todo devuelto alineado al índice de
    `close`; las primeras filas son NaN hasta que el rolling tiene datos."""
    upper_fast = high.rolling(n_fast).max().shift(1)
    lower_fast = low.rolling(n_fast).min().shift(1)
    upper_slow = high.rolling(n_slow).max().shift(1)
    lower_slow = low.rolling(n_slow).min().shift(1)
    atr = true_range(close, high, low).rolling(atr_n).mean()
    return upper_fast, lower_fast, upper_slow, lower_slow, atr


def simulate_breakout_weights(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                               risk_target: float = RISK_TARGET, n_fast: int = N_FAST,
                               n_slow: int = N_SLOW, atr_n: int = ATR_N, k_trail: float = K_TRAIL,
                               cap_asset: float = CAP_ASSET, cap_gross: float = CAP_GROSS) -> pd.DataFrame:
    """Simula el sistema dual de ruptura + sizing por ATR, activo por activo
    (sin cruzar información entre columnas salvo el cap de bruto conjunto).

    Devuelve los pesos DECIDIDOS al cierre de cada día `t` (todavía SIN el
    shift de aplicación: quien llame a `apply_costs` debe hacer
    `.shift(1)` antes, como el resto de los scripts de esta sesión).
    """
    upper_fast, lower_fast, upper_slow, lower_slow, atr = compute_channels_and_atr(
        close, high, low, n_fast, n_slow, atr_n)

    n, k = close.shape
    C = close.to_numpy()
    UF, LF = upper_fast.to_numpy(), lower_fast.to_numpy()
    US, LS = upper_slow.to_numpy(), lower_slow.to_numpy()
    ATR = atr.to_numpy()

    position = np.zeros(k, dtype=np.int8)   # 0 flat, 1 largo, -1 corto
    entry_n = np.zeros(k, dtype=np.int8)    # 20 o 55: qué canal abrió la posición vigente
    extreme = np.zeros(k)                   # extremo (en close) alcanzado desde la entrada
    weight = np.zeros((n, k))

    warmup = n_slow + 1   # primera fila con upper_slow/lower_slow no-NaN
    for t in range(warmup, n):
        c, uf, lf, us, ls, atr_t = C[t], UF[t], LF[t], US[t], LS[t], ATR[t]
        valid = ~np.isnan(uf) & ~np.isnan(us) & ~np.isnan(atr_t) & (atr_t > 0)

        for j in range(k):
            if not valid[j]:
                continue
            pos = position[j]
            if pos == 1:
                if c[j] < lf[j] or c[j] < ls[j]:               # reversión a corto
                    position[j] = -1
                    entry_n[j] = 20 if c[j] < lf[j] else 55
                    extreme[j] = c[j]
                else:
                    extreme[j] = max(extreme[j], c[j])
                    trail = extreme[j] - k_trail * atr_t[j]
                    opp = lf[j] if entry_n[j] == 20 else ls[j]
                    if c[j] <= trail or c[j] <= opp:
                        position[j] = 0
            elif pos == -1:
                if c[j] > uf[j] or c[j] > us[j]:               # reversión a largo
                    position[j] = 1
                    entry_n[j] = 20 if c[j] > uf[j] else 55
                    extreme[j] = c[j]
                else:
                    extreme[j] = min(extreme[j], c[j])
                    trail = extreme[j] + k_trail * atr_t[j]
                    opp = uf[j] if entry_n[j] == 20 else us[j]
                    if c[j] >= trail or c[j] >= opp:
                        position[j] = 0
            else:                                              # flat: buscar entrada
                if c[j] > uf[j] or c[j] > us[j]:
                    position[j] = 1
                    entry_n[j] = 20 if c[j] > uf[j] else 55
                    extreme[j] = c[j]
                elif c[j] < lf[j] or c[j] < ls[j]:
                    position[j] = -1
                    entry_n[j] = 20 if c[j] < lf[j] else 55
                    extreme[j] = c[j]

            if position[j] != 0:
                size = min(risk_target / (atr_t[j] / c[j]), cap_asset)
                weight[t, j] = position[j] * size

        gross = np.abs(weight[t]).sum()
        if gross > cap_gross:
            weight[t] *= cap_gross / gross

    return pd.DataFrame(weight, index=close.index, columns=close.columns)


# ---------------------------------------------------------------- backtest por semilla

def run_seed(seed: int, risk_target: float = RISK_TARGET, n_days: int = N_DAYS) -> dict:
    """Corre la construcción completa (estrategia + benchmarks) para una
    semilla del mercado sintético y devuelve métricas por fold + agregadas,
    en ambos regímenes de costo, junto con buy&hold y el baseline aleatorio."""
    mk = generate_market(n_days=n_days, seed=seed)
    close = mk.close
    asset_returns = close.pct_change().fillna(0)

    signal = simulate_breakout_weights(close, mk.high, mk.low, risk_target=risk_target)
    weights = signal.shift(1).fillna(0.0)   # convención de apply_costs: ya en información de t

    avg_gross = float(weights.abs().sum(axis=1).mean())
    bh = buy_and_hold(close, rebalance=True)
    rb_weights = random_baseline(close.index, close.columns, avg_gross=avg_gross, seed=seed).shift(1).fillna(0.0)

    n = len(close)
    folds = fold_slices(n, N_FOLDS, warmup=WARMUP)

    out = {"seed": seed, "risk_target": risk_target, "avg_gross": round(avg_gross, 4),
           "n_days": n, "warmup": WARMUP, "folds": [], "costs": {}}

    for cost_label, cost in (("conservador_0.15%", COST_CONSERVATIVE), ("realista_0.05%", COST_REALISTIC)):
        strat_ret = apply_costs(weights, asset_returns, cost)
        bh_ret = bh          # buy&hold es el benchmark, sin costo (igual que backtest_common.buy_and_hold)
        rb_ret = apply_costs(rb_weights, asset_returns, cost)

        fold_rows_strat, fold_rows_bh, fold_rows_rb = [], [], []
        for i, (a, b) in enumerate(folds):
            fold_rows_strat.append((f"fold {i + 1} ({close.index[a].date()}→{close.index[b - 1].date()})",
                                     metrics(strat_ret.iloc[a:b])))
            fold_rows_bh.append((f"fold {i + 1}", metrics(bh_ret.iloc[a:b])))
            fold_rows_rb.append((f"fold {i + 1}", metrics(rb_ret.iloc[a:b])))

        agg_strat = metrics(strat_ret.iloc[WARMUP:])
        agg_bh = metrics(bh_ret.iloc[WARMUP:])
        agg_rb = metrics(rb_ret.iloc[WARMUP:])

        out["costs"][cost_label] = {
            "estrategia": {"folds": [m for _, m in fold_rows_strat], "agregado": agg_strat},
            "buy_and_hold": {"folds": [m for _, m in fold_rows_bh], "agregado": agg_bh},
            "random_baseline": {"folds": [m for _, m in fold_rows_rb], "agregado": agg_rb},
            "fold_table_estrategia": fold_table(fold_rows_strat + [("AGREGADO", agg_strat)]),
        }

    return out


def _elegir_riesgo_objetivo(seed: int = 42) -> None:
    """Utilidad de diagnóstico (no se llama en el flujo normal): corre un
    par de valores de `riesgo_objetivo` sobre la semilla de referencia y
    muestra la exposición bruta resultante, para documentar la elección a
    priori hecha en el docstring del módulo."""
    mk = generate_market(n_days=N_DAYS, seed=seed)
    for rt in (0.005, 0.01, 0.02):
        w = simulate_breakout_weights(mk.close, mk.high, mk.low, risk_target=rt)
        gross = w.abs().sum(axis=1)
        print(f"riesgo_objetivo={rt}: bruto medio={gross.mean():.2f} "
              f"p90={gross.quantile(.9):.2f} días en cap(3.0)={(gross >= 2.999).sum()}/{len(gross)}")


# ---------------------------------------------------------------- main

def main():
    results = {"params": {"n_fast": N_FAST, "n_slow": N_SLOW, "atr_n": ATR_N, "k_trail": K_TRAIL,
                           "risk_target": RISK_TARGET, "cap_asset": CAP_ASSET, "cap_gross": CAP_GROSS,
                           "n_folds": N_FOLDS, "warmup": WARMUP, "n_days": N_DAYS, "seeds": list(SEEDS)},
               "by_seed": {}}

    for seed in SEEDS:
        print(f"\n{'=' * 70}\nSEMILLA {seed}\n{'=' * 70}")
        res = run_seed(seed)
        results["by_seed"][str(seed)] = res
        print(f"exposición bruta media: {res['avg_gross']:.2f}x")
        for cost_label, block in res["costs"].items():
            print(f"\n--- costos {cost_label} ---")
            print(block["fold_table_estrategia"])
            print(f"  b&h agregado:      {block['buy_and_hold']['agregado']}")
            print(f"  random agregado:   {block['random_baseline']['agregado']}")

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResultados guardados en {RESULTS_PATH}")


if __name__ == "__main__":
    main()
