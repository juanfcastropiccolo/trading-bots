"""Prueba E — clasificador ML con walk-forward honesto sobre el mercado
sintético (backend/scripts/synthetic_market.py).

Contexto (PLAN_FUTUROS.md): la decisión de NO usar ML para dirección se basa
en "el único backtest de XGBoost con costos de perps y walk-forward honesto
empata con buy&hold" (arXiv 2606.00060). Este script es la prueba directa de
esa hipótesis en este mercado sintético: ¿un clasificador con walk-forward
EXPANDIENTE genuinamente honesto (el modelo nunca ve una fila del fold que
va a predecir, ni siquiera para el fit del scaler) le gana a baselines
triviales una vez puestos los costos?

Diseño (panel pooled, no un modelo por activo):
  - Apilamos las filas de los 10 activos en un solo panel (activo, fecha) y
    entrenamos UN modelo único sobre todos. Con ~2000 días × 10 activos y un
    edge (si existe) que se espera común entre criptos correlacionadas, un
    panel pooled da mucha más señal de entrenamiento que 10 modelos con
    ~2000 filas cada uno; es una elección de diseño explícita, no un default.
  - Features CAUSALES calculadas con información hasta el cierre de t
    (nunca t+1): RSI(14), retorno acumulado a {5,10,20,60}d, volatilidad
    realizada a {10,30}d, distancia % a SMA(50)/SMA(200), rank cross-
    sectional del retorno de 20d entre los 10 activos ese día (0-1), y el
    funding del propio activo en t (ya es información de t).
  - Label: signo(retorno de close de t a t+1) por activo (1 sube, 0 baja o
    queda igual).
  - Walk-forward EXPANDIENTE de 6 folds (fold_slices de backtest_common):
    para cada fold de test, el modelo se reentrena con TODA la historia
    ESTRICTAMENTE anterior al inicio de ese fold (nunca con datos del fold
    actual ni de folds futuros). El StandardScaler de la logística también
    se ajusta solo con ese train — nunca ve el fold de test.
  - Señal de trading: peso_i,t = (K/N) * clip(2*p_i,t - 1, -1, 1), con
    K=1.0 (exposición bruta tope, comparable a estar 100% invertido) y N=10
    activos, así el gross máximo posible es K=1.0 (cuando los 10 activos
    están en el extremo de confianza el mismo día). El peso decidido con el
    cierre de t se aplica al retorno realizado de t a t+1 (columna `fwd_ret`
    del panel, ya construida así) — sin shift extra, tal como pide la
    convención de backtest_common.

Baselines de comparación (misma ventana de test, mismos costos):
  (a) buy_and_hold(close, rebalance=True) — equiponderada, sin costos (b&h
      no es una estrategia operable gratis, es la vara).
  (b) random_baseline con exposición bruta comparable a la del modelo.
  (c) "persiste el signo de ayer" (naive momentum-1 día): peso_i,t =
      (K/N)*signo(retorno realizado en t), el punto de comparación más
      importante: si el ML no le gana a esto, no hay edge.

Uso:
    python scripts/validate_ml_walkforward.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
from synthetic_market import SYMBOLS  # noqa: E402
from market_data import describe, load_market, parse_cli  # noqa: E402
from backtest_common import (  # noqa: E402
    COST_CONSERVATIVE, COST_REALISTIC,
    apply_costs, buy_and_hold, fold_slices, metrics, random_baseline,
)

N_DAYS = 2190           # ~6 años, igual que synthetic_market.generate_market default
N_FOLDS = 6
SEEDS = [42, 7, 123]

RET_WINDOWS = (5, 10, 20, 60)
VOL_WINDOWS = (10, 30)
SMA_WINDOWS = (50, 200)
RSI_WINDOW = 14
FEATURE_WARMUP = max(SMA_WINDOWS)   # SMA(200) es la ventana causal más larga
# Warmup pasado a fold_slices: además de los 200 días que tardan en quedar
# válidas las features, dejamos ~200 días más de historia utilizable ANTES
# del primer fold de test para que el primer reentrenamiento no tenga que
# aprender de un puñado de filas.
WARMUP = FEATURE_WARMUP + 200

SIGNAL_K = 1.0          # exposición bruta tope de la señal ML/naive (gross máx = K)
N_ASSETS = len(SYMBOLS)

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ml_walkforward_results.json")

SOURCE = "synthetic"     # market_data: 'synthetic' | 'real' (se fija desde la CLI en main)
CACHE_DIR = None         # cache de futures_data para --source real

warnings.filterwarnings("ignore", category=ConvergenceWarning)


# ---------------------------------------------------------------- features

def _rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_feature_frames(close: pd.DataFrame, funding: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Todas las features usan solo información hasta el cierre de la fila
    (día t): ninguna mira hacia adelante. Devuelve un dict nombre->DataFrame
    (fecha x activo), todas con la MISMA forma que `close`."""
    daily_ret = close.pct_change()
    feats: dict[str, pd.DataFrame] = {}
    feats["rsi14"] = close.apply(_rsi) / 100.0
    for k in RET_WINDOWS:
        feats[f"ret_{k}d"] = close.pct_change(k)
    for w in VOL_WINDOWS:
        feats[f"vol_{w}d"] = daily_ret.rolling(w).std()
    for w in SMA_WINDOWS:
        feats[f"dist_sma{w}"] = close / close.rolling(w).mean() - 1.0
    # rank cross-sectional del retorno de 20d entre los N activos, ese mismo
    # día (0 a 1): sigue siendo información de t, no de otra fecha.
    feats["xs_rank_ret20"] = feats["ret_20d"].rank(axis=1, pct=True)
    feats["funding"] = funding.reindex(columns=close.columns)
    return feats


FEATURE_NAMES = ["rsi14", "ret_5d", "ret_10d", "ret_20d", "ret_60d", "vol_10d", "vol_30d",
                  "dist_sma50", "dist_sma200", "xs_rank_ret20", "funding"]


def build_panel(close: pd.DataFrame, funding: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Panel pooled (una fila por (fecha, activo)) con las features, el
    label (signo del retorno t->t+1) y las columnas auxiliares para
    reconstruir después una matriz de pesos ancha (fwd_ret, naive_sign,
    day_pos). Filas sin todas las features válidas o sin label se
    descartan (warmup de las rolling windows al principio, último día sin
    t+1 al final)."""
    dates = close.index
    feats = build_feature_frames(close, funding)

    cols = []
    for name in FEATURE_NAMES:
        s = feats[name].stack()
        s.name = name
        cols.append(s)
    panel = pd.concat(cols, axis=1)
    panel.index.names = ["date", "symbol"]

    fwd_ret = close.pct_change().shift(-1)              # retorno REALIZADO de t a t+1, en la fila t
    label = (fwd_ret > 0).astype(float)
    label = label.where(fwd_ret.notna())                 # NaN en el último día (no hay t+1)
    naive_sign = np.sign(close.pct_change())             # signo del retorno de ayer a hoy (info de t)

    idx_names = ["date", "symbol"]
    panel = panel.join(fwd_ret.stack().rename("fwd_ret").rename_axis(idx_names), how="left")
    panel = panel.join(label.stack().rename("label").rename_axis(idx_names), how="left")
    panel = panel.join(naive_sign.stack().rename("naive_sign").rename_axis(idx_names), how="left")

    panel = panel.reset_index()
    pos_of_date = pd.Series(np.arange(len(dates)), index=dates)
    panel["day_pos"] = panel["date"].map(pos_of_date).astype(int)

    before = len(panel)
    panel = panel.dropna(subset=FEATURE_NAMES + ["label", "fwd_ret"]).reset_index(drop=True)
    assert before - len(panel) > 0, "se esperaban filas descartadas por warmup / último día sin t+1"
    return panel, dates


# ---------------------------------------------------------------- fit / predict por fold

def fit_predict_fold(panel: pd.DataFrame, model_name: str, start: int, end: int, seed: int):
    """Entrena SOLO con filas de `panel` con day_pos < start (historia
    estrictamente anterior al fold) y predice sobre day_pos en [start, end).
    Para 'logistic', el StandardScaler se ajusta también solo con ese
    train. Devuelve (test_df, proba, accuracy, auc, model[, scaler])."""
    train = panel[panel["day_pos"] < start]
    test = panel[(panel["day_pos"] >= start) & (panel["day_pos"] < end)]
    assert train["day_pos"].max() < start, "lookahead: el train tocó una fecha del fold de test"

    X_train, y_train = train[FEATURE_NAMES].to_numpy(), train["label"].to_numpy()
    X_test, y_test = test[FEATURE_NAMES].to_numpy(), test["label"].to_numpy()

    if model_name == "logistic":
        scaler = StandardScaler().fit(X_train)          # fit SOLO con train del fold
        model = LogisticRegression(max_iter=2000, random_state=seed)
        model.fit(scaler.transform(X_train), y_train)
        proba = model.predict_proba(scaler.transform(X_test))[:, 1]
        extra = scaler
    else:
        model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                           subsample=0.8, random_state=seed)
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        extra = None

    preds = (proba >= 0.5).astype(int)
    acc = float(accuracy_score(y_test, preds))
    auc = float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else float("nan")
    return test, proba, acc, auc, model, extra


# ---------------------------------------------------------------- pesos -> backtest

def signal_to_weights(prob_or_sign_wide: pd.DataFrame, is_probability: bool) -> pd.DataFrame:
    """peso_i,t = (K/N) * clip(2p-1, -1, 1) si es probabilidad, o
    (K/N) * signo si ya es +-1/0/NaN (baseline naive). Gross máximo = K."""
    if is_probability:
        raw = (2 * prob_or_sign_wide - 1).clip(-1, 1)
    else:
        raw = prob_or_sign_wide.clip(-1, 1)
    return (SIGNAL_K / N_ASSETS) * raw.fillna(0.0)


def backtest_weights(weights: pd.DataFrame, fwd_ret: pd.DataFrame) -> dict[str, pd.Series]:
    """PnL neto por régimen de costo. `weights` y `fwd_ret` alineados fila a
    fila: el peso decidido con el cierre de t se aplica al retorno de t a
    t+1 que ya vive en la fila t de `fwd_ret` (sin shift extra)."""
    out = {}
    for label, cost in (("conservador", COST_CONSERVATIVE), ("realista", COST_REALISTIC)):
        out[label] = apply_costs(weights, fwd_ret, cost)
    return out


# ---------------------------------------------------------------- walk-forward completo

def run_walkforward(seed: int, n_days: int = N_DAYS, n_folds: int = N_FOLDS,
                    warmup: int = WARMUP) -> dict:
    mk = load_market(SOURCE, seed=seed, n_days=n_days, cache_dir=CACHE_DIR)
    close, funding = mk.close, mk.funding
    panel, dates = build_panel(close, funding)
    n = len(dates)
    boundaries = fold_slices(n, n_folds, warmup=warmup)

    fwd_ret_wide = close.pct_change().shift(-1).fillna(0.0)
    naive_weights = signal_to_weights(np.sign(close.pct_change()), is_probability=False)
    naive_weights.iloc[:warmup] = 0.0

    bh = buy_and_hold(close, rebalance=True)

    result: dict = {"seed": seed, "source": SOURCE, "period": describe(mk), "folds": [],
                    "last_fold_diagnostics": {}}
    model_pnl = {"logistic": {"conservador": pd.Series(0.0, index=dates), "realista": pd.Series(0.0, index=dates)},
                "gboost": {"conservador": pd.Series(0.0, index=dates), "realista": pd.Series(0.0, index=dates)}}
    model_rnd_pnl = {"logistic": {"conservador": pd.Series(0.0, index=dates), "realista": pd.Series(0.0, index=dates)},
                     "gboost": {"conservador": pd.Series(0.0, index=dates), "realista": pd.Series(0.0, index=dates)}}
    model_gross = {"logistic": [], "gboost": []}
    fold_records = []

    for k, (start, end) in enumerate(boundaries):
        fold_entry = {"fold": k + 1, "test_start": str(dates[start].date()),
                     "test_end": str(dates[end - 1].date()), "n_test_days": end - start}
        for model_name in ("logistic", "gboost"):
            test_df, proba, acc, auc, model, extra = fit_predict_fold(panel, model_name, start, end, seed)

            proba_series = pd.Series(proba, index=pd.MultiIndex.from_arrays(
                [test_df["date"].to_numpy(), test_df["symbol"].to_numpy()], names=["date", "symbol"]))
            prob_wide = proba_series.unstack("symbol").reindex(index=dates[start:end], columns=SYMBOLS)
            w_fold = signal_to_weights(prob_wide, is_probability=True)
            model_gross[model_name].append(float(w_fold.abs().sum(axis=1).mean()))

            pnl_fold = backtest_weights(w_fold, fwd_ret_wide.loc[dates[start:end]])
            for cost_label, series in pnl_fold.items():
                model_pnl[model_name][cost_label].loc[dates[start:end]] = series

            # random calibrado a la MISMA exposición bruta que el modelo ese
            # fold (más estricto que compararlo contra un random a gross ~1:
            # aísla si el edge viene de la predicción o de simplemente estar
            # invertido con ese nivel de riesgo).
            gross_model_fold = float(w_fold.abs().sum(axis=1).mean())
            rnd_w_model = random_baseline(dates[start:end], SYMBOLS, gross_model_fold,
                                          seed=seed + k + (0 if model_name == "logistic" else 1000))
            rnd_model_fold = backtest_weights(rnd_w_model, fwd_ret_wide.loc[dates[start:end]])
            for cost_label, series in rnd_model_fold.items():
                model_rnd_pnl[model_name][cost_label].loc[dates[start:end]] = series

            fold_entry[model_name] = {
                "accuracy": round(acc, 4), "auc": round(auc, 4) if auc == auc else None,
                "avg_gross": round(gross_model_fold, 4),
                "metrics_conservador": metrics(pnl_fold["conservador"]),
                "metrics_realista": metrics(pnl_fold["realista"]),
                "random_same_gross_conservador": metrics(rnd_model_fold["conservador"]),
                "random_same_gross_realista": metrics(rnd_model_fold["realista"]),
            }

            if k == len(boundaries) - 1:
                if model_name == "logistic":
                    result["last_fold_diagnostics"]["logistic_coefficients"] = {
                        f: round(c, 4) for f, c in zip(FEATURE_NAMES, model.coef_[0].tolist())}
                    result["last_fold_diagnostics"]["logistic_intercept"] = round(float(model.intercept_[0]), 4)
                else:
                    result["last_fold_diagnostics"]["gboost_feature_importances"] = {
                        f: round(v, 4) for f, v in zip(FEATURE_NAMES, model.feature_importances_.tolist())}

        # baselines del mismo tramo (misma ventana de test): naive y b&h a
        # exposición "plena" (gross~1, igual convención K/N que la señal
        # ML), y un random a ESE mismo gross~1 (comparable a naive/b&h, no
        # al gross —mucho más bajo— de los modelos, que ya tienen su propio
        # random calibrado arriba).
        naive_fold = backtest_weights(naive_weights.loc[dates[start:end]], fwd_ret_wide.loc[dates[start:end]])
        avg_gross_naive = float(naive_weights.loc[dates[start:end]].abs().sum(axis=1).mean())
        rnd_weights = random_baseline(dates[start:end], SYMBOLS, avg_gross_naive, seed=seed + k)
        rnd_fold = backtest_weights(rnd_weights, fwd_ret_wide.loc[dates[start:end]])
        bh_seg = bh.loc[dates[start:end]]

        fold_entry["naive_momentum1"] = {
            "metrics_conservador": metrics(naive_fold["conservador"]),
            "metrics_realista": metrics(naive_fold["realista"]),
        }
        fold_entry["random_full_gross"] = {
            "metrics_conservador": metrics(rnd_fold["conservador"]),
            "metrics_realista": metrics(rnd_fold["realista"]),
        }
        fold_entry["buy_and_hold"] = {"metrics": metrics(bh_seg)}
        fold_records.append(fold_entry)

    result["folds"] = fold_records

    aggregate = {}
    for model_name in ("logistic", "gboost"):
        aggregate[model_name] = {
            "avg_gross": round(float(np.mean(model_gross[model_name])), 4),
            "metrics_conservador": metrics(model_pnl[model_name]["conservador"].iloc[warmup:]),
            "metrics_realista": metrics(model_pnl[model_name]["realista"].iloc[warmup:]),
            "random_same_gross_conservador": metrics(model_rnd_pnl[model_name]["conservador"].iloc[warmup:]),
            "random_same_gross_realista": metrics(model_rnd_pnl[model_name]["realista"].iloc[warmup:]),
        }
    naive_full = backtest_weights(naive_weights, fwd_ret_wide)
    aggregate["naive_momentum1"] = {
        "metrics_conservador": metrics(naive_full["conservador"].iloc[warmup:]),
        "metrics_realista": metrics(naive_full["realista"].iloc[warmup:]),
    }
    rnd_full_weights = random_baseline(dates, SYMBOLS,
                                       float(naive_weights.iloc[warmup:].abs().sum(axis=1).mean()), seed=seed)
    rnd_full = backtest_weights(rnd_full_weights, fwd_ret_wide)
    aggregate["random_full_gross"] = {
        "metrics_conservador": metrics(rnd_full["conservador"].iloc[warmup:]),
        "metrics_realista": metrics(rnd_full["realista"].iloc[warmup:]),
    }
    aggregate["buy_and_hold"] = {"metrics": metrics(bh.iloc[warmup:])}
    result["aggregate"] = aggregate
    return result


# ---------------------------------------------------------------- reporte en consola

def _fmt_m(m: dict) -> str:
    return f"cagr={m['cagr']:+.3f} sharpe={m['sharpe']:+.2f} max_dd={m['max_dd']:.3f}"


def print_report(res: dict) -> None:
    seed = res["seed"]
    print(f"\n{'=' * 70}\nSEMILLA {seed} — datos: {res['period']}\n{'=' * 70}")
    print(f"{'fold':>4} | {'log_acc':>7} {'log_auc':>7} | {'gb_acc':>7} {'gb_auc':>7} | rango de test")
    for f in res["folds"]:
        print(f"{f['fold']:>4} | {f['logistic']['accuracy']:>7.4f} {f['logistic']['auc']:>7.4f} | "
              f"{f['gboost']['accuracy']:>7.4f} {f['gboost']['auc']:>7.4f} | {f['test_start']}..{f['test_end']}")

    for cost_key, cost_label in (("metrics_conservador", "conservador 0.15%"), ("metrics_realista", "realista 0.05%")):
        print(f"\n-- costos {cost_label} --")
        for f in res["folds"]:
            rnd_log_key = cost_key.replace("metrics_", "random_same_gross_")
            print(f"  fold {f['fold']}: log[{_fmt_m(f['logistic'][cost_key])}] "
                  f"(rnd@gross[{_fmt_m(f['logistic'][rnd_log_key])}])  "
                  f"gb[{_fmt_m(f['gboost'][cost_key])}] (rnd@gross[{_fmt_m(f['gboost'][rnd_log_key])}])  "
                  f"naive[{_fmt_m(f['naive_momentum1'][cost_key])}]  "
                  f"random_full[{_fmt_m(f['random_full_gross'][cost_key])}]  "
                  f"b&h[{_fmt_m(f['buy_and_hold']['metrics'])}]")
        agg = res["aggregate"]
        print(f"  AGREGADO: log[{_fmt_m(agg['logistic'][cost_key])}] gb[{_fmt_m(agg['gboost'][cost_key])}]  "
              f"naive[{_fmt_m(agg['naive_momentum1'][cost_key])}]  "
              f"random_full[{_fmt_m(agg['random_full_gross'][cost_key])}]")
    print(f"  b&h agregado: {_fmt_m(res['aggregate']['buy_and_hold']['metrics'])}")

    print("\n-- diagnóstico último fold --")
    print("  coeficientes logística:", res["last_fold_diagnostics"]["logistic_coefficients"])
    print("  importancias gboost:", res["last_fold_diagnostics"]["gboost_feature_importances"])


def main() -> None:
    global SOURCE, CACHE_DIR, SEEDS
    cfg = parse_cli("Prueba E: clasificador ML con walk-forward expandiente")
    SOURCE, CACHE_DIR, SEEDS = cfg.source, cfg.cache_dir, list(cfg.seeds)
    results_path = cfg.results_path(RESULTS_PATH)
    print(f"Fuente de datos: {cfg.label}")
    all_results = {}
    for seed in SEEDS:
        res = run_walkforward(seed)
        all_results[str(seed)] = res
        print_report(res)

    meta = {
        "source": SOURCE, "n_days": N_DAYS, "n_folds": N_FOLDS, "warmup": WARMUP, "seeds": SEEDS,
        "feature_names": FEATURE_NAMES, "signal_k": SIGNAL_K, "n_assets": N_ASSETS,
        "cost_conservative": COST_CONSERVATIVE, "cost_realistic": COST_REALISTIC,
    }
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as fh:
        json.dump({"meta": meta, "seeds": all_results}, fh, indent=2, default=str)
    print(f"\nResultados guardados en {results_path}")


if __name__ == "__main__":
    main()
