"""Generador de mercado sintético multi-activo para investigar construcciones
de estrategia (prueba A-E de esta sesión).

Por qué sintético: este entorno de ejecución no tiene salida de red hacia
ningún exchange ni proveedor de datos (Binance, Kraken, KuCoin, MEXC, Gate,
Bybit, OKX, Hyperliquid y data.binance.vision devuelven 403 en el proxy de
salida al momento de escribir esto), así que no se puede descargar historia
real como hacen `research.py` / `futures_data.py`. Este módulo genera velas
diarias con las propiedades estilizadas de cripto —clusters de volatilidad,
colas gordas, régimen de tendencia común (factor "BTC"), reversión de corto
plazo, un puñado de pares con spread cointegrado, y funding correlacionado
con el trend reciente— para que las cinco construcciones de estrategia de
esta sesión se puedan comparar en igualdad de condiciones.

Es un banco de pruebas de ESTRUCTURA (¿la construcción encuentra lo que se
diseñó para encontrar? ¿sobrevive a costos y a walk-forward?), no una
estimación de retorno esperado en cripto real. Ningún número de acá debe
usarse para operar con plata; en cuanto el entorno tenga salida de red, el
mismo framework (`backtest_common.py`) corre igual sobre `research.fetch_history`
o `futures_data.build_matrices`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
           "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT"]

# beta al factor común ("BTC") y vol idiosincrática diaria: majors más bajos,
# alts más ruidosas y más beta, a grosso modo como en cripto real.
BETA = {"BTC/USDT": 1.00, "ETH/USDT": 1.15, "SOL/USDT": 1.45, "BNB/USDT": 0.80,
        "XRP/USDT": 0.90, "DOGE/USDT": 1.55, "ADA/USDT": 1.20, "LINK/USDT": 1.30,
        "AVAX/USDT": 1.40, "LTC/USDT": 0.85}
IDIO_VOL = {"BTC/USDT": 0.018, "ETH/USDT": 0.024, "SOL/USDT": 0.040, "BNB/USDT": 0.022,
            "XRP/USDT": 0.032, "DOGE/USDT": 0.048, "ADA/USDT": 0.034, "LINK/USDT": 0.036,
            "AVAX/USDT": 0.042, "LTC/USDT": 0.026}
PRICE0 = {"BTC/USDT": 42000.0, "ETH/USDT": 2400.0, "SOL/USDT": 95.0, "BNB/USDT": 310.0,
          "XRP/USDT": 0.55, "DOGE/USDT": 0.08, "ADA/USDT": 0.38, "LINK/USDT": 14.0,
          "AVAX/USDT": 28.0, "LTC/USDT": 70.0}

# pares con un spread adicional mean-reverting (Ornstein-Uhlenbeck) en precio
# de log: dan a la construcción de relative-value algo real que encontrar,
# sin que sea un espejo perfecto (cada pata igual tiene su propio ruido).
COINTEGRATED_PAIRS = [("ETH/USDT", "LINK/USDT"), ("SOL/USDT", "AVAX/USDT"), ("BNB/USDT", "LTC/USDT")]

REGIME_NAMES = ("bull", "bear", "crab")
START = "2018-06-01"


@dataclass
class Market:
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    funding: pd.DataFrame          # fracción diaria; positivo = long paga a short
    regime: pd.Series              # 0 bull / 1 bear / 2 crab del factor común (referencia, no usar como señal)

    @property
    def dates(self):
        return self.close.index


def _regime_path(n: int, rng: np.random.Generator) -> np.ndarray:
    """Cadena de Markov de 3 estados, duración media ~150-250 días (ciclos cripto)."""
    P = np.array([[1 - 1 / 220, 1 / 440, 1 / 440],
                  [1 / 300, 1 - 1 / 150, 1 / 300],
                  [1 / 260, 1 / 260, 1 - 1 / 130]])
    out = np.empty(n, dtype=int)
    state = 2
    for t in range(n):
        out[t] = state
        state = rng.choice(3, p=P[state])
    return out


def _common_factor(n: int, rng: np.random.Generator, regimes: np.ndarray) -> np.ndarray:
    mu = {0: 0.0022, 1: -0.0022, 2: 0.0000}
    sig = {0: 0.026, 1: 0.042, 2: 0.019}
    mu_t = np.array([mu[r] for r in regimes])
    sig_t = np.array([sig[r] for r in regimes])
    shock = rng.standard_t(df=4, size=n) / np.sqrt(4 / (4 - 2))
    f = mu_t + sig_t * shock
    jump = rng.random(n) < 0.0035
    sign = np.where(rng.random(n) < 0.65, -1.0, 1.0)
    f = f + jump * sign * rng.uniform(0.05, 0.16, n)
    return f


def _ou(n: int, rng: np.random.Generator, rho: float = 0.985, vol: float = 0.010) -> np.ndarray:
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = rho * x[t - 1] + rng.normal(0, vol)
    return x


def generate_market(n_days: int = 2190, seed: int = 0, symbols: list[str] | None = None) -> Market:
    symbols = symbols or SYMBOLS
    rng = np.random.default_rng(seed)
    dates = pd.date_range(START, periods=n_days, freq="D")
    regimes = _regime_path(n_days, rng)
    f = _common_factor(n_days, rng, regimes)

    logp = {}
    idio_ret = {}
    for sym in symbols:
        beta, vol = BETA[sym], IDIO_VOL[sym]
        drift = np.zeros(n_days)                       # tendencia idiosincrática lenta (AR1 muy persistente)
        for t in range(1, n_days):
            drift[t] = 0.985 * drift[t - 1] + rng.normal(0, vol * 0.05)
        eps = rng.standard_t(df=5, size=n_days) * vol / np.sqrt(5 / 3)
        r = beta * f + drift + eps
        r[1:] -= 0.12 * eps[:-1]                        # reversión de corto plazo: parte del shock de ayer se revierte
        idio_ret[sym] = r
        logp[sym] = np.cumsum(r)

    # pares cointegrados: `b` seguidor de `a` por corrección de error (ECM),
    # con el MISMO beta al factor común (así se cancela en el spread) y una
    # corrección kappa hacia un spread objetivo. Esto hace que
    # log(close_b) - log(close_a) sea AR(1) estacionario por construcción
    # (coeficiente 1-kappa < 1), con vida media controlada por kappa —
    # justo lo que una estrategia de relative-value tiene que descubrir y
    # verificar (no asumir) sobre datos reales.
    for (a, b), kappa, target in zip(COINTEGRATED_PAIRS, (0.05, 0.035, 0.02),
                                     (np.log(PRICE0[p[1]] / PRICE0[p[0]]) for p in COINTEGRATED_PAIRS)):
        beta_shared = BETA[a]                       # b hereda el beta de a: el factor común se cancela en el spread
        vol_b = IDIO_VOL[b]
        eps_b = rng.standard_t(df=5, size=n_days) * vol_b / np.sqrt(5 / 3)
        logp_b = np.zeros(n_days)
        logp_b[0] = logp[a][0] + target
        for t in range(1, n_days):
            spread_prev = logp_b[t - 1] - logp[a][t - 1]
            correction = kappa * (target - spread_prev)
            r_b = correction + beta_shared * f[t] + eps_b[t] - 0.12 * eps_b[t - 1]
            logp_b[t] = logp_b[t - 1] + r_b
        idio_ret[b] = np.diff(logp_b, prepend=logp_b[0])
        logp[b] = logp_b

    close = pd.DataFrame({s: PRICE0[s] * np.exp(logp[s] - logp[s][0]) for s in symbols}, index=dates)

    # rango intradiario a partir de la magnitud del shock del día (para
    # breakouts/ATR); no hay "open" separado, alcanza para señales de daily bar.
    high = close.copy()
    low = close.copy()
    for sym in symbols:
        rng_frac = 0.35 * np.abs(idio_ret[sym]) + rng.uniform(0.003, 0.015, n_days)
        high[sym] = close[sym] * (1 + rng_frac * rng.uniform(0.4, 1.0, n_days))
        low[sym] = close[sym] * (1 - rng_frac * rng.uniform(0.4, 1.0, n_days))
    low = np.minimum(low, close * 0.999)
    high = np.maximum(high, close * 1.001)

    # funding: correlacionado con el retorno reciente (el lado "obvio" paga),
    # con ruido propio y squeezes ocasionales que lo llevan en contra —
    # descripción de PLAN_FUTUROS.md sobre funding real.
    funding = {}
    for sym in symbols:
        r = pd.Series(idio_ret[sym] + BETA[sym] * f)
        trend = r.ewm(halflife=5, min_periods=1).mean().to_numpy()
        noise = _ou(n_days, rng, rho=0.9, vol=0.00025)
        squeeze = np.where(rng.random(n_days) < 0.01, rng.choice([-1.0, 1.0], n_days) * rng.uniform(3, 8, n_days), 1.0)
        fnd = (0.35 * trend + noise) * squeeze
        funding[sym] = np.clip(fnd, -0.006, 0.006)      # cap ~ funding extremo real (~600%/año en el pico)
    funding = pd.DataFrame(funding, index=dates)

    return Market(close=close, high=pd.DataFrame(high, index=dates, columns=symbols),
                  low=pd.DataFrame(low, index=dates, columns=symbols), funding=funding,
                  regime=pd.Series(regimes, index=dates))


if __name__ == "__main__":
    mk = generate_market(seed=1)
    ret = mk.close.pct_change().dropna()
    print("días:", len(mk.close), "activos:", mk.close.shape[1])
    print("vol anualizada (%):\n", (ret.std() * (365 ** 0.5) * 100).round(1))
    print("corr:\n", ret.corr().round(2))
    print("autocorr lag1 (reversión corta si < 0):\n", ret.apply(lambda s: s.autocorr(1)).round(3))
    for a, b in COINTEGRATED_PAIRS:
        spread = np.log(mk.close[a]) - np.log(mk.close[b])
        print(f"spread {a}-{b}: std={spread.std():.3f} autocorr1={spread.diff().autocorr(1):.2f} "
              f"half-life~{-np.log(2)/np.log(abs(spread.autocorr(1))+1e-9):.0f}d" if spread.autocorr(1) < 1 else "")
    print("funding anualizado medio (%):\n", (mk.funding.mean() * 365 * 100).round(1))
