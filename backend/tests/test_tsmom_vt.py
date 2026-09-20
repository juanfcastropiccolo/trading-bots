"""Tests de la Prueba D: TSMOM absoluto diversificado + vol targeting de dos
capas (backend/scripts/validate_tsmom_vt.py).

Cubren lo que el proyecto exige verificar en código: cero lookahead
(recalcular sobre un prefijo de los datos no cambia los pesos pasados),
caps de apalancamiento respetados en las dos capas, dirección de la señal
correcta sobre una tendencia sintética simple, folds walk-forward bien
formados, y que el pipeline completo (una semilla, ambas variantes) corre
sin errores y produce un payload JSON-serializable con la estructura
esperada.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from backtest_common import fold_slices, metrics  # noqa: E402
from synthetic_market import generate_market  # noqa: E402
import validate_tsmom_vt as tv  # noqa: E402


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def market():
    return generate_market(n_days=500, seed=42)


@pytest.fixture(scope="module")
def close(market):
    return market.close


@pytest.fixture(scope="module")
def daily_ret(close):
    return close.pct_change()


# ---------------------------------------------------------------- cero lookahead

def test_no_lookahead_prefijo_l90(close, daily_ret):
    """Recalcular la señal/pesos sobre un prefijo de los datos debe dar
    exactamente los mismos valores para esas fechas que calcularlos sobre
    la serie completa: si algo mirara al futuro, truncar cambiaría el
    pasado."""
    cut = 350
    full = tv.build_weights(close, daily_ret, [tv.L_BASE])["weights"]
    prefix = tv.build_weights(close.iloc[:cut], daily_ret.iloc[:cut], [tv.L_BASE])["weights"]
    pd.testing.assert_frame_equal(full.iloc[:cut], prefix, check_exact=False, atol=1e-10)


def test_no_lookahead_prefijo_ensemble(close, daily_ret):
    cut = 350
    full = tv.build_weights(close, daily_ret, tv.ENSEMBLE_LBS)["weights"]
    prefix = tv.build_weights(close.iloc[:cut], daily_ret.iloc[:cut], tv.ENSEMBLE_LBS)["weights"]
    pd.testing.assert_frame_equal(full.iloc[:cut], prefix, check_exact=False, atol=1e-10)


def test_shift_reduce_lookahead_advantage(close, daily_ret):
    """La versión con shift(1) (correcta) no debe rendir mejor, en Sharpe,
    que la versión con lookahead deliberado (aplicar el peso al retorno del
    mismo día): si el shift no restara ninguna ventaja informativa, algo
    estaría mal en la alineación temporal."""
    from backtest_common import apply_costs

    w = tv.build_weights(close, daily_ret, [tv.L_BASE])["weights"]
    ret_ok = tv.strategy_returns(w, daily_ret, tv.COST_REALISTIC)
    ret_lookahead = apply_costs(w.fillna(0.0), daily_ret.fillna(0.0), tv.COST_REALISTIC)

    m_ok = metrics(ret_ok.iloc[tv.WARMUP:])
    m_la = metrics(ret_lookahead.iloc[tv.WARMUP:])
    assert m_ok["sharpe"] < m_la["sharpe"]


# ---------------------------------------------------------------- caps de apalancamiento

def test_cap_por_activo_capa1(close, daily_ret):
    built = tv.build_weights(close, daily_ret, [tv.L_BASE])
    raw = built["raw_weights"]
    assert raw.abs().max().max() <= tv.ASSET_LEVERAGE_CAP + 1e-9


def test_cap_bruto_portafolio_capa2(close, daily_ret):
    for lbs in ([tv.L_BASE], tv.ENSEMBLE_LBS):
        w = tv.build_weights(close, daily_ret, lbs)["weights"]
        gross = w.abs().sum(axis=1)
        assert gross.max() <= tv.GROSS_CAP + 1e-9


def test_pesos_nulos_en_warmup(close, daily_ret):
    """Antes del warmup (falta historia para el lookback más largo o para
    la ventana de vol) no debe haber posición: cero lookahead implícito."""
    warmup = max(max(tv.ENSEMBLE_LBS), tv.VOL_LOOKBACK)
    w = tv.build_weights(close, daily_ret, tv.ENSEMBLE_LBS)["weights"]
    assert (w.iloc[:warmup].abs().to_numpy() == 0).all()


# ---------------------------------------------------------------- dirección de la señal

def test_signo_de_la_senal_sigue_tendencia():
    """Con una tendencia sintética simple y clara (un activo sube, el otro
    baja, ambos con algo de ruido chico) la posición final debe terminar
    larga en el que sube y corta en el que baja, no al revés."""
    n = 400
    rng = np.random.default_rng(0)
    up = 0.01 + rng.normal(0, 0.002, n)
    down = -0.01 + rng.normal(0, 0.002, n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    close = pd.DataFrame({
        "UP": 100 * np.exp(np.cumsum(up)),
        "DOWN": 100 * np.exp(np.cumsum(down)),
    }, index=idx)
    daily_ret = close.pct_change()
    w = tv.build_weights(close, daily_ret, [tv.L_BASE])["weights"]
    tail = w.iloc[-30:]
    assert (tail["UP"] > 0).all()
    assert (tail["DOWN"] < 0).all()


# ---------------------------------------------------------------- folds walk-forward

def test_fold_slices_cobertura_completa():
    n = 2190
    slices = fold_slices(n, tv.N_FOLDS, warmup=tv.WARMUP)
    assert len(slices) == tv.N_FOLDS
    assert slices[0][0] == tv.WARMUP
    assert slices[-1][1] == n
    # contiguos, sin huecos ni superposición
    for (a1, b1), (a2, b2) in zip(slices, slices[1:]):
        assert b1 == a2


def test_costo_mayor_no_rinde_mejor(close, daily_ret):
    """Con el mismo vector de pesos y turnover > 0, el régimen de costo
    conservador (0.15%) no puede rendir mejor que el realista (0.05%)."""
    w = tv.build_weights(close, daily_ret, [tv.L_BASE])["weights"]
    ret_cons = tv.strategy_returns(w, daily_ret, tv.COST_CONSERVATIVE)
    ret_real = tv.strategy_returns(w, daily_ret, tv.COST_REALISTIC)
    assert ret_cons.iloc[tv.WARMUP:].sum() <= ret_real.iloc[tv.WARMUP:].sum()


# ---------------------------------------------------------------- pipeline completo

def test_run_seed_end_to_end(monkeypatch):
    """Corrida completa (mercado + 2 variantes + 2 regímenes de costo +
    baseline aleatorio + b&h) sobre una serie corta, y el payload JSON debe
    poder armarse y serializarse."""
    monkeypatch.setattr(tv, "N_DAYS", 400)
    result = tv.run_seed(42)

    assert result["n_days"] == 400
    for vname in ("l90", "ensemble"):
        assert vname in result
        v = result[vname]
        for cost_name in tv.COSTS:
            assert cost_name in v["costs"]
            agg = v["costs"][cost_name]["aggregate"]
            assert agg["n"] > 0
            assert len(v["costs"][cost_name]["folds"]) == tv.N_FOLDS
            assert cost_name in v["random_baseline"]
        assert len(v["exposure_by_fold"]) == tv.N_FOLDS

    payload = tv.build_payload({42: result})
    # slim con full=True para la única semilla presente (42 == PRIMARY_SEED)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["seeds"]["42"]["l90"]["costs"][tv.COST_REALISTIC and "realista_0.05%"]["aggregate"]["n"] > 0


def test_metrics_estructura(close, daily_ret):
    w = tv.build_weights(close, daily_ret, [tv.L_BASE])["weights"]
    ret = tv.strategy_returns(w, daily_ret, tv.COST_REALISTIC)
    m = metrics(ret.iloc[tv.WARMUP:])
    for key in ("cagr", "vol_ann", "sharpe", "max_dd", "calmar", "win_rate"):
        assert key in m
