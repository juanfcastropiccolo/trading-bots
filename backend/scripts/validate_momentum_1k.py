"""Validación de variantes long-only para la cuenta paper de $1000.

Contexto: la long-only en producción (momentum_paper.py, $100) usa top-2 por
momentum 30d con filtro SMA-100 y opera solo cuando cambia el target. Con
$1000 por slot se habilitan configuraciones irrealizables con $100 (top-3) y
vale la pena atacar el churn observado en vivo (oct-2026: alternancia diaria
ADA↔LTC con momentums empatados, pagando costos en cada vuelta).

Lista CERRADA de trials, declarada ex-ante (Bailey-López de Prado: nada de
iterar hasta que dé lindo):

  1. base_top2          control = regla de producción tal cual
  2. top3               top-3 equiponderado (diversificación)
  3. top2_hyst4         histéresis: una posición conserva su slot mientras
                        siga en el top-4 y sobre su SMA-100
  4. top3_hyst5         ídem con top-3 / banda top-5
  5. top2_vt50          vol targeting 50% anualizado por posición (overlay
                        validado en la investigación L/S)
  6. top2_ens           momentum promedio 15/30/60/90d (ensemble)
  7. top3_hyst5_vt50    combinación de 2+4+5

Criterios de aceptación (fijados antes de correr; costos 0.15% por lado):
  (a) folds positivos >= 4/6,
  (b) Sharpe full-period >= baseline + 0.05,
  (c) maxDD <= baseline,
  (d) turnover anual <= 2x baseline.
Si ninguna variante pasa los cuatro, la cuenta de $1000 corre el baseline
tal cual — "no hay mejora" es un resultado válido.

Datos: velas 1d spot de un solo exchange para los 10 majors (se intenta
EXCHANGE_ID en orden hasta que uno tenga historia suficiente para todos).
Escribe VALIDACION_1K.md en la raíz del repo.

Uso:  EXCHANGE_ID="kucoin,gate,mexc" python scripts/validate_momentum_1k.py
"""
import os
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
]
COST = 0.0015          # 0.15% por lado, conservador (igual que producción)
BUDGET = 1000.0
TREND_W = 100
N_FOLDS = 6
WARMUP = 105           # > SMA-100 y > lookback máximo (90)
TARGET_DAYS = 2100     # ~5.7 años si el exchange los tiene
MIN_DAYS = 1100        # mínimo aceptable de historia común

EXCHANGE_IDS = os.environ.get("EXCHANGE_ID", "kucoin,gate,mexc").split(",")

TRIALS = {
    "base_top2":      dict(top_k=2, lookbacks=[30], hyst=None, voltarget=None),
    "top3":           dict(top_k=3, lookbacks=[30], hyst=None, voltarget=None),
    "top2_hyst4":     dict(top_k=2, lookbacks=[30], hyst=4,    voltarget=None),
    "top3_hyst5":     dict(top_k=3, lookbacks=[30], hyst=5,    voltarget=None),
    "top2_vt50":      dict(top_k=2, lookbacks=[30], hyst=None, voltarget=0.50),
    "top2_ens":       dict(top_k=2, lookbacks=[15, 30, 60, 90], hyst=None, voltarget=None),
    "top3_hyst5_vt50": dict(top_k=3, lookbacks=[30], hyst=5,   voltarget=0.50),
}


def fetch_all() -> tuple[pd.DataFrame, str]:
    """Devuelve matriz de cierres diarios y el exchange usado."""
    last_err = None
    best: tuple[int, pd.DataFrame, str] | None = None
    for exid in [e.strip() for e in EXCHANGE_IDS if e.strip()]:
        try:
            ex = getattr(ccxt, exid)({"enableRateLimit": True})
            series = {}
            for s in SYMBOLS:
                since = ex.milliseconds() - TARGET_DAYS * 86_400_000
                candles = []
                while True:
                    batch = ex.fetch_ohlcv(s, timeframe="1d", since=since, limit=1000)
                    if not batch:
                        break
                    candles.extend(batch)
                    since = batch[-1][0] + 1
                    if len(batch) < 2:
                        break
                ser = pd.Series(
                    {pd.Timestamp(c[0], unit="ms").normalize(): c[4] for c in candles}
                ).sort_index()
                series[s] = ser[~ser.index.duplicated(keep="last")]
            px = pd.DataFrame(series).dropna()
            print(f"{exid}: {len(px)} días comunes ({px.index[0].date()} → {px.index[-1].date()})")
            if len(px) >= MIN_DAYS:
                return px, exid
            if best is None or len(px) > best[0]:
                best = (len(px), px, exid)
        except Exception as e:
            last_err = e
            print(f"⚠️  {exid} falló ({type(e).__name__}: {str(e)[:120]}); pruebo el siguiente…")
    if best is not None:
        print(f"⚠️  Ningún exchange llegó a {MIN_DAYS} días; uso el mejor disponible.")
        return best[1], best[2]
    raise SystemExit(f"Sin datos de ningún exchange de {EXCHANGE_IDS}: {last_err}")


def run_variant(px: pd.DataFrame, top_k: int, lookbacks: list[int],
                hyst: int | None, voltarget: float | None) -> tuple[pd.Series, pd.Series]:
    """Simula la variante día a día. Devuelve (retornos diarios netos, |Δw| diario).

    Réplica de la mecánica de producción: la decisión es diaria, pero solo se
    opera cuando cambia el conjunto de posiciones; con voltarget, la escala se
    refresca además los lunes (como el paper trader L/S). Pesos constantes
    entre operaciones (misma aproximación que validate_momentum.py).
    """
    score = sum(px.pct_change(lb) for lb in lookbacks) / len(lookbacks)
    sma = px.rolling(TREND_W).mean()
    ret = px.pct_change().fillna(0.0)
    vol30 = ret.rolling(30).std() * np.sqrt(365)

    weights = pd.DataFrame(0.0, index=px.index, columns=px.columns)
    current: dict[str, float] = {}          # símbolo -> peso

    for i in range(WARMUP, len(px)):
        ranked = score.iloc[i].dropna().sort_values(ascending=False)
        above = px.iloc[i] > sma.iloc[i]
        band = list(ranked.index[:hyst]) if hyst else []

        if hyst:
            kept = [s for s in current if s in band and above[s]]
        else:
            kept = [s for s in current
                    if s in ranked.index[:top_k] and above[s]]
        picks = list(kept)
        for s in ranked.index[:top_k]:
            if len(picks) >= top_k:
                break
            if s not in picks and above[s]:
                picks.append(s)

        is_monday = px.index[i].weekday() == 0
        if set(picks) != set(current) or (voltarget and is_monday):
            new = {}
            for s in picks:
                w = 1.0 / top_k
                if voltarget:
                    v = vol30.iloc[i][s]
                    if np.isfinite(v) and v > 0:
                        w *= min(1.0, voltarget / v)
                new[s] = w
            current = new

        for s, w in current.items():
            weights.iloc[i, weights.columns.get_loc(s)] = w

    w_prev = weights.shift(1).fillna(0.0)
    turnover = (weights - w_prev).abs().sum(axis=1)
    port_ret = (w_prev * ret).sum(axis=1) - turnover * COST
    return port_ret, turnover


def metrics(port_ret: pd.Series, turnover: pd.Series) -> dict:
    eq = (1 + port_ret).cumprod()
    peak = eq.cummax()
    dd = ((peak - eq) / peak).max() * 100
    std = port_ret.std()
    sharpe = port_ret.mean() / std * np.sqrt(365) if std > 0 else 0.0
    years = len(port_ret) / 365
    body = port_ret.iloc[WARMUP:]
    edges = [WARMUP + int((len(port_ret) - WARMUP) * j / N_FOLDS) for j in range(N_FOLDS + 1)]
    folds = [(1 + port_ret.iloc[edges[j]:edges[j + 1]]).prod() - 1 for j in range(N_FOLDS)]
    change_days = turnover[turnover > 1e-9]
    return {
        "ret": (eq.iloc[-1] - 1) * 100,
        "maxdd": dd,
        "sharpe": sharpe,
        "folds": folds,
        "folds_pos": sum(1 for f in folds if f > 0),
        "turnover_anual": turnover.sum() / years,
        "trades_anual": len(change_days) / years,
        "orden_media_usd": change_days.mean() * BUDGET / 2 if len(change_days) else 0.0,
        "equity_final": BUDGET * eq.iloc[-1],
        "_body_sharpe": body.mean() / body.std() * np.sqrt(365) if body.std() > 0 else 0.0,
    }


def main():
    px, exid = fetch_all()
    results = {name: metrics(*run_variant(px, **params)) for name, params in TRIALS.items()}

    bh_ret = px.pct_change().fillna(0.0).mean(axis=1)
    bh_eq = (1 + bh_ret).cumprod()
    bh_peak = bh_eq.cummax()

    base = results["base_top2"]
    verdicts = {}
    for name, m in results.items():
        if name == "base_top2":
            continue
        checks = {
            "a_folds": m["folds_pos"] >= 4,
            "b_sharpe": m["sharpe"] >= base["sharpe"] + 0.05,
            "c_maxdd": m["maxdd"] <= base["maxdd"],
            "d_turnover": m["turnover_anual"] <= 2 * base["turnover_anual"],
        }
        verdicts[name] = checks

    passing = [n for n, c in verdicts.items() if all(c.values())]
    # desempate declarado: mayor Sharpe entre las que pasan
    winner = max(passing, key=lambda n: results[n]["sharpe"]) if passing else "base_top2"

    hoy = datetime.now(timezone.utc).date().isoformat()
    lines = [
        "# Validación long-only $1000 — Resultados",
        "",
        f"_Lista cerrada de 7 trials (ver `backend/scripts/validate_momentum_1k.py`). "
        f"Datos: {exid} spot 1d, {len(px)} días comunes "
        f"({px.index[0].date()} → {px.index[-1].date()}), {N_FOLDS} folds, "
        f"costos 0.15%/lado. Corrido: {hoy}._",
        "",
        "## Tabla resumen (capital simulado $1000)",
        "",
        "| Config | Ret total | maxDD | Sharpe | Folds+ | Turnover anual | Trades/año | Equity final |",
        "|--------|-----------|-------|--------|--------|----------------|-----------|--------------|",
    ]
    for name, m in results.items():
        star = " ✅" if name == winner and passing else (" (control)" if name == "base_top2" else "")
        lines.append(
            f"| {name}{star} | {m['ret']:+.0f}% | {m['maxdd']:.1f}% | {m['sharpe']:.2f} "
            f"| {m['folds_pos']}/{N_FOLDS} | {m['turnover_anual']:.1f}x | "
            f"{m['trades_anual']:.0f} | ${m['equity_final']:,.0f} |"
        )
    lines += [
        f"| b&h equiponderado | {(bh_eq.iloc[-1]-1)*100:+.0f}% | "
        f"{(((bh_peak-bh_eq)/bh_peak).max())*100:.1f}% | "
        f"{bh_ret.mean()/bh_ret.std()*np.sqrt(365):.2f} | — | — | — | "
        f"${BUDGET*bh_eq.iloc[-1]:,.0f} |",
        "",
        "## Veredicto contra los criterios ex-ante",
        "",
        "| Config | (a) folds≥4/6 | (b) Sharpe≥base+0.05 | (c) maxDD≤base | (d) turnover≤2x | Pasa |",
        "|--------|----|----|----|----|------|",
    ]
    for name, c in verdicts.items():
        chk = lambda b: "✓" if b else "✗"
        lines.append(
            f"| {name} | {chk(c['a_folds'])} | {chk(c['b_sharpe'])} | "
            f"{chk(c['c_maxdd'])} | {chk(c['d_turnover'])} | "
            f"{'**SÍ**' if all(c.values()) else 'no'} |"
        )
    lines += [
        "",
        f"**Config elegida para la cuenta de $1000: `{winner}`**"
        + ("" if passing else " (ninguna variante superó al baseline en los 4 criterios; "
           "se mantiene la regla de producción)"),
        "",
        "## Detalle por fold",
        "",
        "| Config | " + " | ".join(f"F{j+1}" for j in range(N_FOLDS)) + " |",
        "|--------|" + "----|" * N_FOLDS,
    ]
    for name, m in results.items():
        lines.append(f"| {name} | " + " | ".join(f"{f*100:+.0f}%" for f in m["folds"]) + " |")
    lines += [
        "",
        "_Notas: mecánica idéntica a producción (decisión diaria, se opera solo al "
        "cambiar el conjunto; voltarget refresca escala los lunes). Pesos constantes "
        "entre operaciones, misma aproximación que validate_momentum.py. El fold 1 "
        "incluye el warmup de la SMA-100._",
    ]

    out = os.path.join(os.path.dirname(__file__), "..", "..", "VALIDACION_1K.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nEscrito {os.path.abspath(out)}")


if __name__ == "__main__":
    main()
