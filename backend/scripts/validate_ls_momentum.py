"""Validación de variantes momentum long/short sobre perpetuos USDT-M.

Lista CERRADA de variantes y criterios de aceptación definidos ex-ante en
PLAN_FUTUROS.md (commit dc0ca74). No agregar variantes después de ver
resultados: cada trial extra infla el mejor Sharpe esperado por azar.

Mecánica común:
  - Datos: perps 1d + funding diario desde sep-2020 (futures_data.py).
  - Señales causales sobre la historia completa (mom, SMA); pesos decididos
    al cierre y aplicados al día siguiente (shift 1). Los folds se evalúan
    partiendo la serie diaria de retornos resultante (a diferencia de
    validate_momentum.py no se re-calientan indicadores por fold: el régimen
    SMA-200 dejaría solo ~60 días operables en folds de ~9 meses).
  - PnL diario = L·[(w_prev·ret) − (w_prev·funding)] − L·turnover·costo
    (funding positivo → el long paga; el short cobra).
  - Liquidación simulada: con palanca L, un movimiento intradía adverso
    ≥ 0.9/L sobre el cierre previo cuenta como evento de liquidación.

Uso:  python scripts/validate_ls_momentum.py
"""
import numpy as np
import pandas as pd

from futures_data import SYMBOLS, build_matrices

COSTS = {"conservador_0.15%": 0.0015, "realista_0.05%": 0.0005}
LEVERAGES = [1.0, 2.0]
N_FOLDS = 8
REBAL_DAYS = 7
LOOKBACK = 30
TREND_W = 100
REGIME_W = 200          # SMA de BTC que habilita shorts (V4)
ENSEMBLE_LBS = [15, 30, 60, 90]
VOL_TARGET_ANN = 0.50   # vol targeting: objetivo 50% anualizado, cap 1 (sin apalancar)
SHORTABLE = ["BTC/USDT", "ETH/USDT"]  # shorts solo majors líquidos
BTC = "BTC/USDT"


# ---------------------------------------------------------------- señales

def causal_signals(px: pd.DataFrame):
    mom = px.pct_change(LOOKBACK)
    mom_ens = sum(px.pct_change(lb) for lb in ENSEMBLE_LBS) / len(ENSEMBLE_LBS)
    above_trend = px > px.rolling(TREND_W).mean()
    bull = px[BTC] > px[BTC].rolling(REGIME_W).mean()
    vol_ann = px.pct_change().rolling(30).std() * np.sqrt(365)
    return mom, mom_ens, above_trend, bull, vol_ann


def _rebalance_grid(index) -> list[bool]:
    warmup = max(REGIME_W, max(ENSEMBLE_LBS), TREND_W)
    return [(i % REBAL_DAYS == 0 and i >= warmup) for i in range(len(index))]


def make_weights(px, variant: str, mom, mom_ens, above_trend, bull, vol_ann,
                 use_ensemble=False, use_voltarget=False) -> pd.DataFrame:
    score = mom_ens if use_ensemble else mom
    weights = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    current = pd.Series(0.0, index=px.columns)
    rebal = _rebalance_grid(px.index)

    for i in range(len(px.index)):
        if rebal[i]:
            sc = score.iloc[i].dropna()
            ranked = sc.sort_values(ascending=False)
            ok = above_trend.iloc[i]
            below = ~ok
            current = pd.Series(0.0, index=px.columns)

            if variant == "long_only":  # baseline validado, sobre perps
                for s in [s for s in ranked.index[:2] if ok[s]]:
                    current[s] = 0.5

            elif variant == "v4_regime_gate":
                if bull.iloc[i]:
                    for s in [s for s in ranked.index[:2] if ok[s]]:
                        current[s] = 0.5
                else:
                    for s in SHORTABLE:
                        if below[s] and sc.get(s, 0) < 0:
                            current[s] = -0.25

            elif variant == "v5_gate_cash":  # ablación de V4: bear → cash (sin shorts)
                if bull.iloc[i]:
                    for s in [s for s in ranked.index[:2] if ok[s]]:
                        current[s] = 0.5

            elif variant == "v2_tsmom":
                for s in px.columns:
                    if sc.get(s, 0) > 0 and ok[s]:
                        current[s] = 0.10
                    elif s in SHORTABLE and sc.get(s, 0) < 0 and below[s]:
                        current[s] = -0.10

            elif variant == "v1_espejo":  # control: shorts en cualquier símbolo
                for s in [s for s in ranked.index[:2] if ok[s]]:
                    current[s] = 0.5
                for s in [s for s in ranked.index[-2:] if below[s] and sc.get(s, 0) < 0]:
                    current[s] = -0.25

            elif variant == "v3_market_neutral":  # control: sin filtros
                for s in ranked.index[:2]:
                    current[s] = 0.25
                for s in ranked.index[-2:]:
                    current[s] = -0.25

            if use_voltarget:
                scale = (VOL_TARGET_ANN / vol_ann.iloc[i]).clip(upper=1.0).fillna(0)
                current = current * scale

        weights.iloc[i] = current
    return weights


# ---------------------------------------------------------------- pnl y métricas

def portfolio_returns(weights, ret, fund, cost, leverage):
    w_prev = weights.shift(1).fillna(0)
    turnover = (weights - w_prev).abs().sum(axis=1)
    price_pnl = (w_prev * ret).sum(axis=1)
    funding_pnl = -(w_prev * fund).sum(axis=1)
    port = leverage * (price_pnl + funding_pnl) - leverage * turnover * cost
    return port, leverage * price_pnl, leverage * funding_pnl


def liquidation_events(weights, px, hi, lo, leverage) -> int:
    if leverage <= 1:
        threshold = 0.9  # un −90% intradía: imposible en majors
    else:
        threshold = 0.9 / leverage
    w_prev = weights.shift(1).fillna(0)
    prev_close = px.shift(1)
    adverse_long = (1 - lo / prev_close).where(w_prev > 0, 0)
    adverse_short = (hi / prev_close - 1).where(w_prev < 0, 0)
    return int(((adverse_long >= threshold) | (adverse_short >= threshold)).any(axis=1).sum())


def metrics(port: pd.Series) -> dict:
    eq = (1 + port).cumprod()
    peak = eq.cummax()
    dd = ((peak - eq) / peak).max() * 100
    std = port.std()
    return {
        "ret": (eq.iloc[-1] - 1) * 100,
        "maxdd": dd,
        "sharpe": port.mean() / std * np.sqrt(365) if std > 0 else 0.0,
        "worst_day": port.min() * 100,
    }


def fmt(m: dict) -> str:
    return (f"ret={m['ret']:+8.2f}%  maxDD={m['maxdd']:5.1f}%  "
            f"sharpe={m['sharpe']:+5.2f}  peor día={m['worst_day']:+6.2f}%")


# ---------------------------------------------------------------- main

def main():
    px, hi, lo, ret, fund = build_matrices()
    mom, mom_ens, above_trend, bull, vol_ann = causal_signals(px)
    print(f"Perps: {px.shape[0]} días × {px.shape[1]} símbolos "
          f"({px.index[0].date()} → {px.index[-1].date()}) | "
          f"días bear (BTC<SMA200): {(~bull).sum()} de {len(bull)}")

    bh = ret.mean(axis=1)
    bear_mask = ~bull.reindex(px.index).fillna(False)
    edges = [int(len(px) * i / N_FOLDS) for i in range(N_FOLDS + 1)]

    # Lista cerrada (PLAN_FUTUROS.md): variantes × overlays declarados
    runs = [
        ("long_only (baseline perps)", "long_only", False, False),
        ("V4 espejo gateado", "v4_regime_gate", False, False),
        ("V2 tsmom", "v2_tsmom", False, False),
        ("V1 espejo (control)", "v1_espejo", False, False),
        ("V3 mkt-neutral (control)", "v3_market_neutral", False, False),
        ("long_only + ensemble", "long_only", True, False),
        ("long_only + voltarget", "long_only", False, True),
        ("V4 + ensemble", "v4_regime_gate", True, False),
        ("V4 + voltarget", "v4_regime_gate", False, True),
        # Ablaciones post-hoc declaradas (descomponen V4: ¿aportan los shorts
        # algo sobre "gate a cash"? son los trials 10-12 del experimento):
        ("ABLACIÓN gate→cash", "v5_gate_cash", False, False),
        ("ABLACIÓN gate→cash + ensemble", "v5_gate_cash", True, False),
        ("ABLACIÓN gate→cash + voltarget", "v5_gate_cash", False, True),
    ]

    for label, variant, ens, vt in runs:
        weights = make_weights(px, variant, mom, mom_ens, above_trend, bull, vol_ann,
                               use_ensemble=ens, use_voltarget=vt)
        print(f"\n=== {label} ===")
        gross = weights.abs().sum(axis=1)
        net = weights.sum(axis=1)
        print(f"  exposición media: gross={gross.mean():.2f}  net={net.mean():+.2f}")

        for cost_label, cost in COSTS.items():
            port, price_pnl, funding_pnl = portfolio_returns(weights, ret, fund, cost, 1.0)
            m = metrics(port)
            f_total = ((1 + port).cumprod().iloc[-1] /
                       (1 + port - funding_pnl).cumprod().iloc[-1] - 1) * 100
            print(f"  [{cost_label}] L=1  {fmt(m)}")
            print(f"      aporte funding al total: {f_total:+.2f} p.p. | "
                  f"bear-only: ret={((1+port[bear_mask]).cumprod().iloc[-1]-1)*100:+7.2f}%  "
                  f"bull-only: ret={((1+port[~bear_mask]).cumprod().iloc[-1]-1)*100:+7.2f}%")

            if cost_label.startswith("realista"):
                pos = 0
                for k in range(N_FOLDS):
                    a, b = edges[k], edges[k + 1]
                    seg, bh_seg = port.iloc[a:b], bh.iloc[a:b]
                    r = ((1 + seg).cumprod().iloc[-1] - 1) * 100
                    rb = ((1 + bh_seg).cumprod().iloc[-1] - 1) * 100
                    pos += r > 0
                    print(f"      fold {k+1}: {r:+7.2f}%  (b&h {rb:+7.2f}%)")
                print(f"      → folds positivos: {pos}/{N_FOLDS}")

        for lev in LEVERAGES:
            if lev > 1:
                port, _, _ = portfolio_returns(weights, ret, fund, COSTS["realista_0.05%"], lev)
                n_liq = liquidation_events(weights, px, hi, lo, lev)
                print(f"  [sensibilidad] L={lev:.0f}  {fmt(metrics(port))}  "
                      f"liquidaciones simuladas={n_liq}")
        n_liq1 = liquidation_events(weights, px, hi, lo, 1.0)
        if n_liq1:
            print(f"  ⚠️ liquidaciones a L=1: {n_liq1} (criterio (e) violado)")

    print(f"\n[b&h equiponderado 10 majors] {fmt(metrics(bh))}")


if __name__ == "__main__":
    main()
