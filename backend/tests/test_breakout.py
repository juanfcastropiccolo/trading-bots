"""Tests de la Prueba A (ruptura de canal Donchian dual + sizing por ATR),
`validate_breakout.py`. Corre con:

    cd backend && <venv>/bin/python -m pytest tests/test_breakout.py -q

Cubre: ausencia de lookahead (regla no negociable #1), causalidad del canal
y del ATR, respeto de los caps de riesgo, y que la lógica de entrada /
reversión / sizing haga exactamente lo que dice el docstring del script
(verificado contra los mismos canales/ATR recalculados con pandas, no
reimplementando el loop de estado).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from synthetic_market import generate_market  # noqa: E402
from validate_breakout import (ATR_N, CAP_ASSET, CAP_GROSS, K_TRAIL, N_FAST, N_SLOW,  # noqa: E402
                                RISK_TARGET, compute_channels_and_atr, run_seed,
                                simulate_breakout_weights, true_range)

SEED = 42
N_DAYS = 900   # suficiente para varios ciclos de entrada/salida, corre rápido


def _toy_market():
    mk = generate_market(n_days=N_DAYS, seed=SEED)
    return mk.close, mk.high, mk.low


# ---------------------------------------------------------------- lookahead

def test_sin_lookahead_perturbar_futuro_no_cambia_pasado():
    """Regla no negociable #1: cambiar los datos DESPUÉS de un corte no
    puede alterar los pesos decididos ANTES de ese corte."""
    close, high, low = _toy_market()
    cutoff = 400

    w_original = simulate_breakout_weights(close, high, low)

    close2, high2, low2 = close.copy(), high.copy(), low.copy()
    rng = np.random.default_rng(999)
    for df in (close2, high2, low2):
        shock = pd.DataFrame(rng.normal(1.0, 0.5, size=df.iloc[cutoff:].shape).clip(min=0.05),
                              index=df.index[cutoff:], columns=df.columns)
        df.iloc[cutoff:] = (df.iloc[cutoff:] * shock).abs() + 1e-6

    w_perturbado = simulate_breakout_weights(close2, high2, low2)

    pd.testing.assert_frame_equal(w_original.iloc[:cutoff], w_perturbado.iloc[:cutoff])


def test_canal_donchian_excluye_la_vela_de_hoy():
    """upper_N/lower_N en la fila t deben resumir SOLO [t-N, t-1]."""
    idx = pd.date_range("2020-01-01", periods=10)
    high = pd.DataFrame({"X": [10, 20, 15, 12, 30, 11, 11, 11, 11, 11]}, index=idx)
    low = high - 1
    close = high - 0.5

    upper_fast, lower_fast, _, _, _ = compute_channels_and_atr(close, high, low, n_fast=3, n_slow=5, atr_n=3)

    # fila 4 (high=30) NO debe verse reflejada en upper_fast hasta la fila 5
    assert upper_fast.iloc[4]["X"] == high.iloc[1:4]["X"].max()   # ventana [1,2,3], excluye la fila 4
    assert upper_fast.iloc[5]["X"] == 30.0                  # ahora sí incluye la fila 4 (ventana [2,3,4])
    assert np.isnan(upper_fast.iloc[2]["X"])                # todavía sin 3 velas previas completas


def test_true_range_formula_clasica():
    idx = pd.date_range("2020-01-01", periods=3)
    close = pd.DataFrame({"X": [100.0, 90.0, 108.0]}, index=idx)
    high = pd.DataFrame({"X": [101.0, 95.0, 110.0]}, index=idx)
    low = pd.DataFrame({"X": [99.0, 88.0, 104.0]}, index=idx)

    tr = true_range(close, high, low)
    # fila 1: max(95-88=7, |95-100|=5, |88-100|=12) = 12
    assert tr.iloc[1]["X"] == 12.0
    # fila 2: max(110-104=6, |110-90|=20, |104-90|=14) = 20
    assert tr.iloc[2]["X"] == 20.0


# ---------------------------------------------------------------- caps de riesgo

def test_cap_por_activo_nunca_se_viola():
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    assert (w.abs() <= CAP_ASSET + 1e-9).all().all()


def test_cap_de_bruto_nunca_se_viola():
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    assert (w.abs().sum(axis=1) <= CAP_GROSS + 1e-9).all()


def test_sin_posicion_durante_el_warmup():
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    assert (w.iloc[:N_SLOW + 1] == 0).all().all()


# ---------------------------------------------------------------- lógica de entrada/reversión/sizing

def test_toda_entrada_desde_flat_respeta_la_regla_de_ruptura():
    """Cada vez que una columna pasa de 0 a != 0 (sin venir de una
    reversión, o sea el día anterior también estaba en 0), la dirección
    tiene que coincidir con una ruptura de upper_N (largo) o lower_N
    (corto) documentada en el script."""
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    upper_fast, lower_fast, upper_slow, lower_slow, _ = compute_channels_and_atr(close, high, low)

    prev_flat = (w.shift(1).fillna(0) == 0)
    entra_largo = prev_flat & (w > 0)
    entra_corto = prev_flat & (w < 0)

    cond_largo = (close > upper_fast) | (close > upper_slow)
    cond_corto = (close < lower_fast) | (close < lower_slow)

    assert (~entra_largo | cond_largo.fillna(False)).all().all()
    assert (~entra_corto | cond_corto.fillna(False)).all().all()
    # al menos hubo alguna entrada de cada signo en 900 días / 10 activos (si no, el test no prueba nada)
    assert entra_largo.any().any() and entra_corto.any().any()


def test_toda_reversion_directa_respeta_la_ruptura_contraria():
    """Cuando el signo pasa de + a - (o viceversa) SIN pasar por 0, la
    ruptura del canal contrario tiene que estar activa ese día."""
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    upper_fast, lower_fast, upper_slow, lower_slow, _ = compute_channels_and_atr(close, high, low)

    prev_sign = np.sign(w.shift(1).fillna(0))
    cur_sign = np.sign(w)
    reversion_a_corto = (prev_sign > 0) & (cur_sign < 0)
    reversion_a_largo = (prev_sign < 0) & (cur_sign > 0)

    cond_corto = (close < lower_fast) | (close < lower_slow)
    cond_largo = (close > upper_fast) | (close > upper_slow)

    assert (~reversion_a_corto | cond_corto.fillna(False)).all().all()
    assert (~reversion_a_largo | cond_largo.fillna(False)).all().all()


def test_sizing_por_riesgo_fuera_de_los_dias_con_cap_de_bruto():
    """En los días donde el cap de bruto (3.0) NO está activo, el tamaño de
    cada posición abierta debe ser exactamente
    min(riesgo_objetivo / (ATR/precio), cap_por_activo)."""
    close, high, low = _toy_market()
    w = simulate_breakout_weights(close, high, low)
    _, _, _, _, atr = compute_channels_and_atr(close, high, low)

    gross = w.abs().sum(axis=1)
    dias_sin_cap = gross < (CAP_GROSS - 1e-6)
    activo = w != 0

    esperado = (RISK_TARGET / (atr / close)).clip(upper=CAP_ASSET)
    mask = dias_sin_cap.to_numpy()[:, None] & activo.to_numpy()
    diff = (w.abs() - esperado).where(pd.DataFrame(mask, index=w.index, columns=w.columns))
    assert diff.abs().max().max() < 1e-9
    assert mask.sum() > 0   # que el chequeo realmente haya corrido sobre algún día/activo


# ---------------------------------------------------------------- integración con backtest_common

def test_run_seed_produce_ambos_regimenes_de_costo_y_folds():
    res = run_seed(42, n_days=N_DAYS)
    assert set(res["costs"].keys()) == {"conservador_0.15%", "realista_0.05%"}
    for block in res["costs"].values():
        assert len(block["estrategia"]["folds"]) == 6
        assert "sharpe" in block["estrategia"]["agregado"]
        assert "sharpe" in block["buy_and_hold"]["agregado"]
        assert "sharpe" in block["random_baseline"]["agregado"]

    # el costo conservador (0.15%) nunca puede rendir MÁS que el realista
    # (0.05%) sobre la MISMA serie de pesos/turnover: a más costo, menos neto.
    cagr_cons = res["costs"]["conservador_0.15%"]["estrategia"]["agregado"]["cagr"]
    cagr_real = res["costs"]["realista_0.05%"]["estrategia"]["agregado"]["cagr"]
    assert cagr_real >= cagr_cons
