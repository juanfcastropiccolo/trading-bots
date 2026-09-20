"""Tests de la Prueba C: carry cross-sectional de funding, dollar-neutral
(`scripts/validate_carry.py`).

Cubren lo no negociable: cero lookahead en la señal, la convención de signo
del PnL de funding (rate positivo -> el largo paga), la neutralidad dólar de
la cartera principal, la cadencia de rebalanceo semanal, y que la
descomposición precio/funding sume el total.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from backtest_common import COST_CONSERVATIVE, COST_REALISTIC  # noqa: E402
from synthetic_market import generate_market  # noqa: E402
from validate_carry import (K, N_DAYS, OUT_PATH, REBAL_DAYS, WARMUP,  # noqa: E402
                            build_weights, funding_trend, portfolio_returns,
                            run_seed)


@pytest.fixture(scope="module")
def mk():
    return generate_market(n_days=400, seed=1)


# ------------------------------------------------------------------- señal

def test_funding_trend_es_causal_sin_lookahead():
    """La media móvil de 7 días en la fila i no puede depender de funding en
    i+1 en adelante: recortar la serie en i y volver a calcular debe dar el
    mismo valor en la fila i que calcularla sobre la serie completa."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=60)
    funding = pd.DataFrame(rng.normal(0, 0.001, (60, 3)), index=idx, columns=["A", "B", "C"])
    full = funding_trend(funding)
    for cut in (20, 35, 59):
        trunc = funding_trend(funding.iloc[:cut + 1])
        pd.testing.assert_series_equal(full.iloc[cut], trunc.iloc[cut], check_names=False)


def test_build_weights_no_usa_informacion_futura():
    """Cambiar el funding DESPUÉS del día i no debe alterar el peso crudo
    decidido en la fila i (ni ninguna fila anterior)."""
    rng = np.random.default_rng(1)
    idx = pd.date_range("2024-01-01", periods=80)
    cols = [f"S{k}" for k in range(6)]
    funding_a = pd.DataFrame(rng.normal(0, 0.001, (80, 6)), index=idx, columns=cols)
    funding_b = funding_a.copy()
    perturb_from = 50
    funding_b.iloc[perturb_from:] = funding_b.iloc[perturb_from:] + rng.normal(0, 0.01, funding_b.iloc[perturb_from:].shape)

    trend_a = funding_trend(funding_a, window=7)
    trend_b = funding_trend(funding_b, window=7)
    w_a = build_weights(trend_a, k=2, rebal_days=7, warmup=10)
    w_b = build_weights(trend_b, k=2, rebal_days=7, warmup=10)
    # antes de la perturbación (con margen para la ventana de 7 días) los
    # pesos crudos tienen que ser IDÉNTICOS entre ambas corridas
    cutoff = perturb_from - 7
    pd.testing.assert_frame_equal(w_a.iloc[:cutoff], w_b.iloc[:cutoff])


def test_posicion_se_aplica_recien_al_dia_siguiente():
    """`portfolio_returns` debe usar `weights_raw.shift(1)`: un peso crudo
    fijado en la fila t no puede afectar el PnL de la fila t (solo el de
    t+1 en adelante)."""
    idx = pd.date_range("2024-01-01", periods=5)
    cols = ["A", "B"]
    weights_raw = pd.DataFrame(0.0, index=idx, columns=cols)
    weights_raw.loc[idx[2], "A"] = 1.0     # decidido con info hasta el cierre de t=2
    price_ret = pd.DataFrame(0.0, index=idx, columns=cols)
    price_ret.loc[idx[2], "A"] = 0.05      # este retorno es "del día t=2": no debe contar
    price_ret.loc[idx[3], "A"] = 0.07      # este sí, porque es t+1
    funding = pd.DataFrame(0.0, index=idx, columns=cols)

    res = portfolio_returns(weights_raw, price_ret, funding, cost_per_side=0.0)
    assert res["price"].loc[idx[2]] == pytest.approx(0.0)    # sin lookahead
    assert res["price"].loc[idx[3]] == pytest.approx(0.07)   # se aplica un día después


# --------------------------------------------------------------- convención de signo

def test_convencion_signo_funding_long_paga_short_cobra():
    """Rate positivo: el largo (w>0) pierde con el funding, el corto (w<0)
    gana. Rate negativo: al revés."""
    idx = pd.date_range("2024-01-01", periods=3)
    cols = ["A"]
    weights_raw = pd.DataFrame([[1.0], [1.0], [-1.0]], index=idx, columns=cols)
    price_ret = pd.DataFrame(0.0, index=idx, columns=cols)
    funding = pd.DataFrame([[0.0], [0.001], [0.001]], index=idx, columns=cols)  # funding positivo

    res = portfolio_returns(weights_raw, price_ret, funding, cost_per_side=0.0)
    # fila 1: w_prev viene de la fila 0 (=1.0, largo) con funding de la fila 1 (positivo) -> pierde
    assert res["funding"].iloc[1] == pytest.approx(-1.0 * 0.001)
    # fila 2: w_prev viene de la fila 1 (=1.0, largo todavía) con funding positivo -> pierde
    assert res["funding"].iloc[2] == pytest.approx(-1.0 * 0.001)

    weights_raw2 = pd.DataFrame([[-1.0], [-1.0]], index=idx[:2], columns=cols)
    funding2 = pd.DataFrame([[0.0], [0.001]], index=idx[:2], columns=cols)
    res2 = portfolio_returns(weights_raw2, price_ret.iloc[:2], funding2, cost_per_side=0.0)
    assert res2["funding"].iloc[1] == pytest.approx(0.001)   # corto + funding positivo -> cobra


def test_pnl_total_es_precio_menos_funding_con_signo():
    idx = pd.date_range("2024-01-01", periods=4)
    cols = ["A", "B"]
    rng = np.random.default_rng(2)
    weights_raw = pd.DataFrame(rng.normal(0, 0.3, (4, 2)), index=idx, columns=cols)
    price_ret = pd.DataFrame(rng.normal(0, 0.02, (4, 2)), index=idx, columns=cols)
    funding = pd.DataFrame(rng.normal(0, 0.0005, (4, 2)), index=idx, columns=cols)

    res = portfolio_returns(weights_raw, price_ret, funding, cost_per_side=0.0)
    w_prev = weights_raw.shift(1).fillna(0)
    expected = (w_prev * price_ret).sum(axis=1) - (w_prev * funding).sum(axis=1)
    pd.testing.assert_series_equal(res["gross"], expected, check_names=False)
    # sin costos, el retorno neto (gross - 0) coincide con la suma precio+funding
    pd.testing.assert_series_equal(res["net"], expected, check_names=False)


# ----------------------------------------------------------- cartera dollar-neutral

def test_dollar_neutral_bruto_2_neto_0(mk):
    trend = funding_trend(mk.funding)
    w = build_weights(trend, k=K, rebal_days=REBAL_DAYS, warmup=WARMUP, neutral=True)
    post_warmup = w.iloc[WARMUP + 1:]
    gross = post_warmup.abs().sum(axis=1)
    net = post_warmup.sum(axis=1)
    assert gross.mean() == pytest.approx(2.0, abs=1e-9)
    assert (net.abs() < 1e-9).all()
    # cada pata tiene exactamente K posiciones de tamaño 1/K
    for _, row in post_warmup.iterrows():
        longs = row[row > 0]
        shorts = row[row < 0]
        assert len(longs) == K and len(shorts) == K
        assert np.allclose(longs.to_numpy(), 1.0 / K)
        assert np.allclose(shorts.to_numpy(), -1.0 / K)


def test_variante_sin_neutralizar_solo_tiene_pata_corta(mk):
    trend = funding_trend(mk.funding)
    w = build_weights(trend, k=K, rebal_days=REBAL_DAYS, warmup=WARMUP, neutral=False)
    post_warmup = w.iloc[WARMUP + 1:]
    assert (post_warmup.sum(axis=1) < 0).all()          # neto siempre negativo (solo shorts)
    assert post_warmup.abs().sum(axis=1).mean() == pytest.approx(1.0, abs=1e-9)


def test_rebalanceo_semanal_pesos_fijos_entre_rebalanceos(mk):
    trend = funding_trend(mk.funding)
    w = build_weights(trend, k=K, rebal_days=REBAL_DAYS, warmup=WARMUP, neutral=True)
    # entre dos días de rebalanceo consecutivos el peso crudo no cambia
    for i in range(WARMUP + 1, WARMUP + 3 * REBAL_DAYS):
        if (i - WARMUP) % REBAL_DAYS != 0:
            pd.testing.assert_series_equal(w.iloc[i], w.iloc[i - 1], check_names=False)


# ------------------------------------------------------------- descomposición

def test_descomposicion_precio_funding_suma_el_total(mk):
    price_ret = mk.close.pct_change().fillna(0.0)
    trend = funding_trend(mk.funding)
    w = build_weights(trend, k=K, rebal_days=REBAL_DAYS, warmup=WARMUP, neutral=True)
    res = portfolio_returns(w, price_ret, mk.funding, COST_REALISTIC)
    pd.testing.assert_series_equal(res["gross"], res["price"] + res["funding"], check_names=False)
    # con costos, el neto es <= el bruto en cada día (el costo solo resta)
    assert (res["net"] <= res["gross"] + 1e-12).all()


# ------------------------------------------------------------------------ main

def test_run_seed_estructura_y_reproducibilidad():
    r1 = run_seed(42)
    r2 = run_seed(42)
    assert r1["dollar_neutral"]["realista_0.05%"]["fold_metrics"] == \
        r2["dollar_neutral"]["realista_0.05%"]["fold_metrics"]
    for cost_label in (f"{'conservador_0.15%'}", "realista_0.05%"):
        assert cost_label in r1["dollar_neutral"]
        assert cost_label in r1["sin_neutralizar"]
    assert "buy_and_hold" in r1["benchmarks"]
    assert "random_baseline_gross2.0" in r1["benchmarks"]
    assert set(r1["correlacion_con_buy_and_hold"]) == {"dollar_neutral", "sin_neutralizar"}


def test_carry_results_json_se_genera(tmp_path, monkeypatch):
    import validate_carry as vc
    target = tmp_path / "carry_results.json"
    monkeypatch.setattr(vc, "OUT_PATH", str(target))
    vc.main()
    assert target.exists()
    data = json.loads(target.read_text())
    assert set(data["seeds"]) == {"42", "7", "123"}
    for seed in data["seeds"].values():
        assert "dollar_neutral" in seed and "sin_neutralizar" in seed
