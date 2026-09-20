"""Tests de validate_pairs.py (Prueba B: relative value / pairs trading).

Cubren: recuperación de hedge ratio y half-life sobre procesos sintéticos
con parámetros conocidos, la máquina de estados de entrada/salida del
z-score, normalización de exposición bruta, ausencia de lookahead en el
screening (dato central de esta prueba: nada del tramo evaluado ni del
futuro puede cambiar la selección de pares) y una corrida de integración
liviana de `run_seed`.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from synthetic_market import COINTEGRATED_PAIRS, SYMBOLS  # noqa: E402
from validate_pairs import (CORR_WINDOW, N_FOLDS, WARMUP, Z_WINDOW,  # noqa: E402
                            _ar1_half_life, _ols_hedge_ratio, _pair_positions,
                            build_tramp_weights, run_seed, screen_pairs)


def test_hedge_ratio_recupera_pendiente_conocida():
    rng = np.random.default_rng(0)
    x = np.cumsum(rng.normal(0, 1, 500))
    y = 2.5 * x + rng.normal(0, 0.01, 500)  # ruido chico: la pendiente debe recuperarse casi exacta
    h = _ols_hedge_ratio(y, x)
    assert abs(h - 2.5) < 0.02


def test_ar1_half_life_de_un_proceso_ou_conocido():
    rng = np.random.default_rng(1)
    n = 3000
    ar1_true = 0.95
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = ar1_true * x[t - 1] + rng.normal(0, 0.1)
    ar1_est, hl_est = _ar1_half_life(x)
    hl_true = np.log(2) / -np.log(ar1_true)
    assert abs(ar1_est - ar1_true) < 0.02
    assert abs(hl_est - hl_true) < 3.0


def test_ar1_half_life_serie_no_reversiva_da_infinito():
    # random walk puro (ar1 ~ 1): no hay half-life finito
    rng = np.random.default_rng(2)
    x = np.cumsum(rng.normal(0, 1, 500))
    ar1_est, hl_est = _ar1_half_life(x)
    # el estimador OLS de un random walk está sesgado a la baja (sesgo de
    # Dickey-Fuller) pero sigue muy cerca de 1: half-life implícito enorme,
    # muy por fuera de cualquier banda razonable de "cointegración creíble".
    assert ar1_est > 0.9
    assert hl_est > 50.0


def test_pair_positions_entra_y_sale_por_zscore():
    # 60 días de calentamiento con ruido chico (std>0, z ~0), un salto grande
    # que dispara entrada corto-de-spread (z>2), vuelta a la media que cierra.
    rng = np.random.default_rng(3)
    warmup = 0.001 * rng.standard_normal(60)
    jump = np.full(10, 5.0)          # spread muy por encima de su media reciente
    revert = np.zeros(40)            # vuelve a ~0: |z| < 0.5 debería cerrar
    spread = np.concatenate([warmup, jump, revert])
    pos = _pair_positions(spread, entry=2.0, exit_z=0.5, max_hold=30, z_window=60)

    assert (pos[:60] == 0).all()          # sin señal durante el calentamiento
    assert pos[60] == -1                  # z>entry -> corto-de-spread
    # en algún punto de `revert` se cierra la posición (|z|<0.5)
    assert 0 in pos[70:]


def test_pair_positions_max_hold_fuerza_cierre():
    rng = np.random.default_rng(4)
    warmup = 0.001 * rng.standard_normal(60)
    # spread quieto en un nivel elevado y ESTABLE tras el salto: el ruido es
    # tan chico que el z jamás vuelve a |z|<exit_z por sí solo dentro de
    # max_hold, así que la única salida posible es el límite de tenencia.
    plateau = 5.0 + 0.001 * rng.standard_normal(80)
    spread = np.concatenate([warmup, plateau])
    pos = _pair_positions(spread, entry=2.0, exit_z=0.5, max_hold=15, z_window=60)
    entry_idx = np.argmax(pos != 0)
    assert pos[entry_idx] == -1
    # `held` cuenta el día de entrada como 1: con max_hold=15 el cierre por
    # tenencia ocurre 14 días después de la entrada (15 días en posición).
    assert pos[entry_idx + 13] != 0        # sigue adentro justo antes del límite
    assert pos[entry_idx + 14] == 0        # se cerró exactamente al llegar a max_hold


def test_build_tramp_weights_expone_gross_manejable():
    idx = pd.date_range("2020-01-01", periods=200, freq="D")
    log_close = pd.DataFrame({s: np.log(100 + np.cumsum(np.random.default_rng(5).normal(0, 0.5, 200)))
                              for s in SYMBOLS[:3]}, index=idx)
    pairs = [{"a": SYMBOLS[0], "b": SYMBOLS[1], "hedge_ratio": 1.3},
              {"a": SYMBOLS[0], "b": SYMBOLS[2], "hedge_ratio": 0.7}]
    w = build_tramp_weights(log_close, pairs, start=100, end=140)
    gross = np.abs(w).sum(axis=1)
    # con 2 pares y exposición bruta 1/n_pares por pata activa, el máximo
    # posible (los 2 pares activos a la vez) es 1.0
    assert gross.max() <= 1.0 + 1e-9


def test_build_tramp_weights_sin_pares_da_cero():
    idx = pd.date_range("2020-01-01", periods=100, freq="D")
    log_close = pd.DataFrame({s: np.zeros(100) for s in SYMBOLS[:2]}, index=idx)
    w = build_tramp_weights(log_close, [], start=70, end=90)
    assert (w == 0).all()


def test_screen_pairs_no_usa_datos_del_futuro():
    """El punto central de la prueba: cambiar drásticamente los datos DESPUÉS
    de `as_of` no puede alterar la selección de pares en `as_of`."""
    rng = np.random.default_rng(6)
    n = 800
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    symbols = SYMBOLS[:5]
    log_close = pd.DataFrame({s: np.cumsum(rng.normal(0, 0.02, n)) + 4.0 for s in symbols}, index=idx)
    ret = np.exp(log_close.diff()) - 1
    ret.iloc[0] = 0.0

    as_of = 500
    chosen_before = screen_pairs(log_close, ret, as_of)

    # perturbación fuerte de TODO lo posterior a `as_of` (incluida la última
    # fila usable en la ventana, para descartar off-by-one)
    log_close_mutated = log_close.copy()
    ret_mutated = ret.copy()
    log_close_mutated.iloc[as_of:] += 50.0
    ret_mutated.iloc[as_of:] = 5.0
    chosen_after = screen_pairs(log_close_mutated, ret_mutated, as_of)

    def key(chosen):
        return sorted((c["a"], c["b"], round(c["hedge_ratio"], 6), round(c["half_life"], 3))
                      for c in chosen)

    assert key(chosen_before) == key(chosen_after)


def test_screen_pairs_nunca_referencia_los_pares_verdaderos():
    # co_names captura los nombres globales que el bytecode realmente usa
    # (a diferencia de buscar en el texto fuente, no lo engañan docstrings
    # ni comentarios): confirma que la función es ciega a la respuesta.
    names = screen_pairs.__code__.co_names
    assert "COINTEGRATED_PAIRS" not in names and "TRUE_PAIRS" not in names


def test_run_seed_integracion_liviana():
    res = run_seed(42)
    assert len(res["folds"]) == N_FOLDS
    # sin operaciones antes del warmup/primer tramo (nada de lookahead hacia atrás)
    assert res["folds"][0]["start"] >= WARMUP
    for cost_name in ("conservador_0.15%", "realista_0.05%"):
        assert len(res["screening"]["metrics"][cost_name]["per_fold"]) == N_FOLDS
        assert len(res["oracle"]["metrics"][cost_name]["per_fold"]) == N_FOLDS
        assert res["screening"]["metrics"][cost_name]["agg"]["n"] == res["oracle"]["metrics"][cost_name]["agg"]["n"]
    assert len(res["screening"]["match_stats"]) == N_FOLDS
    # la unión de verdaderos+faltantes en cada tramo siempre reconstruye los 3 pares reales
    true_set = {frozenset(p) for p in COINTEGRATED_PAIRS}
    for ms in res["screening"]["match_stats"]:
        found = {frozenset(p) for p in ms["true_positives"]}
        missing = {frozenset(p) for p in ms["false_negatives"]}
        assert found | missing == true_set
        assert found & missing == set()
