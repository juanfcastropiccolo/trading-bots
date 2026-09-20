"""Tests de la Prueba E (backend/scripts/validate_ml_walkforward.py):
clasificador ML con walk-forward honesto sobre el mercado sintético.

El foco es verificar que NO hay lookahead en ningún paso del pipeline
(features, label, split train/test por fold) y que la mecánica de señal ->
pesos respeta el cap de exposición bruta documentado.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from synthetic_market import SYMBOLS, generate_market  # noqa: E402
from backtest_common import fold_slices  # noqa: E402
import validate_ml_walkforward as V  # noqa: E402


@pytest.fixture(scope="module")
def small_market():
    return generate_market(n_days=420, seed=42)


@pytest.fixture(scope="module")
def small_panel(small_market):
    panel, dates = V.build_panel(small_market.close, small_market.funding)
    return panel, dates


# ---------------------------------------------------------------- sin lookahead

def test_train_set_no_contiene_fechas_del_fold_de_test(small_panel):
    """Rule 8: el train de un fold no puede tener NINGUNA fecha >= al
    inicio del fold de test."""
    panel, dates = small_panel
    boundaries = fold_slices(len(dates), 3, warmup=250)

    for start, end in boundaries:
        test_start_date = dates[start]
        train = panel[panel["day_pos"] < start]
        test = panel[(panel["day_pos"] >= start) & (panel["day_pos"] < end)]

        assert len(train) > 0 and len(test) > 0
        # explícito sobre FECHAS reales, no solo sobre el índice entero day_pos
        assert (train["date"] < test_start_date).all(), (
            f"lookahead: el train del fold [{start},{end}) tiene fechas >= "
            f"{test_start_date} (inicio del fold de test)")
        assert (test["date"] >= test_start_date).all()
        assert train["date"].max() < test["date"].min()


def test_fit_predict_fold_respeta_el_corte_temporal(small_panel):
    panel, dates = small_panel
    boundaries = fold_slices(len(dates), 3, warmup=250)
    start, end = boundaries[1]

    for model_name in ("logistic", "gboost"):
        test_df, proba, acc, auc, model, extra = V.fit_predict_fold(panel, model_name, start, end, seed=42)
        assert (test_df["day_pos"] >= start).all() and (test_df["day_pos"] < end).all()
        assert len(proba) == len(test_df)
        assert ((proba >= 0) & (proba <= 1)).all()
        assert 0.0 <= acc <= 1.0


def test_folds_son_contiguos_y_expandientes(small_panel):
    """Los 6(N) folds de fold_slices cubren [warmup, n) sin huecos ni
    superposición, y cada fold siguiente tiene más historia de train
    disponible que el anterior (walk-forward expandiente, no rolling)."""
    _, dates = small_panel
    n = len(dates)
    boundaries = fold_slices(n, 4, warmup=250)

    assert boundaries[0][0] == 250
    assert boundaries[-1][1] == n
    for (s1, e1), (s2, e2) in zip(boundaries, boundaries[1:]):
        assert e1 == s2, "los folds deben ser contiguos (sin huecos ni overlap)"
        assert s2 > s1, "cada fold expandiente arranca más tarde que el anterior"


# ---------------------------------------------------------------- features causales

def test_features_en_t_no_ven_precios_de_t_mas_uno():
    """Cambiar el precio de una fecha futura no debe alterar ninguna
    feature calculada en una fecha anterior."""
    dates = pd.date_range("2020-01-01", periods=300, freq="D")
    rng = np.random.default_rng(0)
    base = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (300, 3)), axis=0)),
                        index=dates, columns=["A", "B", "C"])
    funding = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C"])

    perturbed = base.copy()
    perturbed.iloc[250:] *= 1.5   # solo se modifica el futuro respecto del día 200

    feats_base = V.build_feature_frames(base, funding)
    feats_pert = V.build_feature_frames(perturbed, funding)

    cutoff = 200
    for name in V.FEATURE_NAMES:
        if name == "funding":
            continue
        a = feats_base[name].iloc[:cutoff]
        b = feats_pert[name].iloc[:cutoff]
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-12,
                                      obj=f"feature '{name}' cambió al modificar solo el futuro")


def test_label_es_el_signo_del_retorno_de_t_a_t_mas_uno(small_market):
    close = small_market.close
    panel, dates = V.build_panel(close, small_market.funding)

    sample = panel.sample(200, random_state=0)
    for _, row in sample.iterrows():
        t = row["day_pos"]
        sym = row["symbol"]
        actual_fwd_ret = close[sym].iloc[t + 1] / close[sym].iloc[t] - 1
        assert row["fwd_ret"] == pytest.approx(actual_fwd_ret, rel=1e-9, abs=1e-12)
        assert row["label"] == float(actual_fwd_ret > 0)


def test_panel_descarta_warmup_y_ultimo_dia(small_panel):
    panel, dates = small_panel
    # ningún row con day_pos == n-1 (no hay t+1 para el último día)
    assert panel["day_pos"].max() < len(dates) - 1
    # ninguna fila antes de que SMA(200) tenga historia suficiente
    assert panel["day_pos"].min() >= max(V.SMA_WINDOWS) - 1


# ---------------------------------------------------------------- señal -> pesos

def test_signal_to_weights_respeta_el_cap_de_gross():
    dates = pd.date_range("2020-01-01", periods=50, freq="D")
    rng = np.random.default_rng(1)
    proba = pd.DataFrame(rng.uniform(0, 1, (50, len(SYMBOLS))), index=dates, columns=SYMBOLS)

    weights = V.signal_to_weights(proba, is_probability=True)
    gross = weights.abs().sum(axis=1)
    assert (gross <= V.SIGNAL_K + 1e-9).all()

    extreme = pd.DataFrame(1.0, index=dates, columns=SYMBOLS)  # p=1 en todos: máximo gross posible
    w_extreme = V.signal_to_weights(extreme, is_probability=True)
    assert w_extreme.abs().sum(axis=1).iloc[0] == pytest.approx(V.SIGNAL_K)


def test_naive_signal_es_signo_del_retorno_de_ayer():
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    close = pd.DataFrame({"A": [100, 110, 90, 90, 130]}, index=dates)
    sign = np.sign(close.pct_change())
    weights = V.signal_to_weights(sign, is_probability=False)
    # día 1: sube -> signo +1 -> peso positivo; día 2: baja -> signo -1 -> peso negativo
    assert weights["A"].iloc[1] > 0
    assert weights["A"].iloc[2] < 0
    assert weights["A"].iloc[3] == 0  # retorno nulo -> signo 0


# ---------------------------------------------------------------- corrida chica end-to-end

def test_run_walkforward_smoke():
    """Corrida chica (pocos días/folds) para validar que el pipeline
    completo -incluido el guardado de diagnósticos del último fold- corre
    sin lookahead y produce métricas bien formadas."""
    res = V.run_walkforward(seed=42, n_days=420, n_folds=3, warmup=250)

    assert len(res["folds"]) == 3
    for fold in res["folds"]:
        for model_name in ("logistic", "gboost"):
            m = fold[model_name]
            assert 0.0 <= m["accuracy"] <= 1.0
            assert m["auc"] is None or 0.0 <= m["auc"] <= 1.0
            for cost_key in ("metrics_conservador", "metrics_realista"):
                assert m[cost_key]["n"] > 0
        assert "naive_momentum1" in fold and "random_full_gross" in fold and "buy_and_hold" in fold

    diag = res["last_fold_diagnostics"]
    assert set(diag["logistic_coefficients"]) == set(V.FEATURE_NAMES)
    assert set(diag["gboost_feature_importances"]) == set(V.FEATURE_NAMES)
    assert all(v >= 0 for v in diag["gboost_feature_importances"].values())


# ---------------------------------------------------------------- entregable guardado

def test_resultados_guardados_en_json():
    assert os.path.exists(V.RESULTS_PATH), (
        "falta backend/data/ml_walkforward_results.json: correr "
        "python scripts/validate_ml_walkforward.py antes de este test")
    import json
    with open(V.RESULTS_PATH) as fh:
        data = json.load(fh)
    assert set(data["seeds"]) == {"42", "7", "123"}
    for seed_key, seed_res in data["seeds"].items():
        assert len(seed_res["folds"]) == V.N_FOLDS
        assert "logistic" in seed_res["aggregate"] and "gboost" in seed_res["aggregate"]
