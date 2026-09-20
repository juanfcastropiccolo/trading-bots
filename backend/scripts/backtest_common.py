"""Utilidades compartidas por las 5 construcciones de estrategia de esta
sesión (A-E), para que las métricas y los costos se calculen exactamente
igual en todas y los resultados sean comparables.

Convenciones (consistentes con research.py / validate_ls_momentum.py /
PLAN_FUTUROS.md):
  - Costos por lado: 0.15% conservador, 0.05% realista. Se cobran sobre el
    turnover (cambio de peso), no por operación, para que aplique igual a
    estrategias de rebalanceo diario y a las que casi no rotan.
  - 365 períodos por año (cripto opera todos los días).
  - Toda señal se calcula con información hasta el cierre de t y se aplica
    al retorno de t+1 (`shift(1)`): quien no lo haga en su script está
    metiendo lookahead y el backtest no vale.
  - Folds contiguos (no aleatorios) para que cada uno sea un período de
    mercado real y no una mezcla de régimen bull con bear.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COST_CONSERVATIVE = 0.0015
COST_REALISTIC = 0.0005
PERIODS_PER_YEAR = 365


def max_drawdown(equity: pd.Series) -> float:
    """Fracción, positiva (0.25 = -25%)."""
    peak = equity.cummax()
    dd = (peak - equity) / peak.replace(0, np.nan)
    return float(dd.max()) if len(dd) else 0.0


def metrics(returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR) -> dict:
    """Métricas estándar sobre una serie de retornos NETOS (ya con costos).
    `returns` debe estar alineada con el día en que el PnL se realiza."""
    returns = returns.dropna()
    if len(returns) == 0:
        return {"n": 0, "cagr": 0.0, "vol_ann": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "max_dd": 0.0, "calmar": 0.0, "win_rate": 0.0, "best": 0.0, "worst": 0.0,
                "total_return": 0.0}
    equity = (1 + returns).cumprod()
    n = len(returns)
    total_return = float(equity.iloc[-1] - 1)
    years = n / periods_per_year
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else -1.0
    vol_ann = float(returns.std(ddof=0) * np.sqrt(periods_per_year))
    sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year)) if returns.std(ddof=0) > 0 else 0.0
    downside = returns[returns < 0]
    sortino = float(returns.mean() / downside.std(ddof=0) * np.sqrt(periods_per_year)) if len(downside) > 1 and downside.std(ddof=0) > 0 else 0.0
    mdd = max_drawdown(equity)
    calmar = float(cagr / mdd) if mdd > 1e-9 else 0.0
    return {"n": n, "cagr": round(cagr, 4), "vol_ann": round(vol_ann, 4), "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3), "max_dd": round(mdd, 4), "calmar": round(calmar, 3),
            "win_rate": round(float((returns > 0).mean()), 4), "best": round(float(returns.max()), 4),
            "worst": round(float(returns.min()), 4), "total_return": round(total_return, 4)}


def apply_costs(weights: pd.DataFrame, asset_returns: pd.DataFrame, cost_per_side: float) -> pd.Series:
    """PnL neto de una cartera de pesos `weights` (ya en información de t,
    o sea, se van a aplicar al retorno de t -> el llamador ya hizo el
    shift(1) antes de pasar `weights`). Turnover = suma de |Δpeso| por día."""
    gross = (weights * asset_returns).sum(axis=1)
    turnover = weights.fillna(0).diff().abs().sum(axis=1)
    turnover.iloc[0] = weights.iloc[0].abs().sum()
    costs = turnover * cost_per_side
    return gross - costs


def fold_slices(n: int, n_folds: int, warmup: int = 0) -> list[tuple[int, int]]:
    """Índices [start, end) de `n_folds` folds contiguos sobre las filas
    utilizables (después de `warmup`). Igual criterio que validate_ls_momentum."""
    usable = n - warmup
    size = usable // n_folds
    return [(warmup + i * size, warmup + (i + 1) * size if i < n_folds - 1 else n) for i in range(n_folds)]


def buy_and_hold(close: pd.DataFrame, rebalance: bool = True) -> pd.Series:
    """Cartera equiponderada de todos los activos: rebalanceada a diario
    (`rebalance=True`, sin costos — es el benchmark, no una estrategia
    operable gratis) o comprada una vez y sostenida (pesos a la deriva)."""
    rets = close.pct_change().fillna(0)
    if rebalance:
        return rets.mean(axis=1)
    w = pd.DataFrame(1.0 / close.shape[1], index=close.index, columns=close.columns)
    for t in range(1, len(close)):
        prev = w.iloc[t - 1] * (1 + rets.iloc[t])
        w.iloc[t] = prev / prev.sum()
    return (w.shift(1).fillna(1.0 / close.shape[1]) * rets).sum(axis=1)


def random_baseline(index: pd.Index, columns, avg_gross: float, seed: int, autocorr: float = 0.9) -> pd.DataFrame:
    """Pesos aleatorios con la MISMA exposición bruta media que la
    estrategia a comparar (`avg_gross` = exposición bruta promedio, p.ej.
    1.0 = 100% invertido), con algo de persistencia día a día (`autocorr`)
    para que el turnover también sea comparable. Sin costo de por sí: se
    le aplican los mismos costos que a la estrategia con `apply_costs`."""
    rng = np.random.default_rng(seed)
    n, k = len(index), len(columns)
    w = np.zeros((n, k))
    cur = rng.normal(0, 1, k)
    for t in range(n):
        cur = autocorr * cur + (1 - autocorr) * rng.normal(0, 1, k)
        raw = cur / (np.abs(cur).sum() + 1e-12) * avg_gross * k / max(1, k)
        w[t] = raw
    return pd.DataFrame(w, index=index, columns=columns)


def fold_table(name_metric_pairs: list[tuple[str, dict]]) -> str:
    """Tabla markdown de métricas por fold + agregado, para pegar directo
    en un reporte."""
    if not name_metric_pairs:
        return ""
    cols = ["n", "cagr", "vol_ann", "sharpe", "max_dd", "calmar", "win_rate"]
    lines = ["| Fold | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for name, m in name_metric_pairs:
        lines.append(f"| {name} | " + " | ".join(str(m.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)
