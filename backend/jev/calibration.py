"""Calibración (Sección VII.D): Brier, ECE, curva de confiabilidad y Platt.

RLCD calibra al modelo contra la distribución de entrenamiento del vendor; la
de un venue, instrumento y fraseo concretos no es esa. El policy engine asume
que p reportada ≡ frecuencia realizada, y eso se verifica acá sobre las
triples (estado, decisión, resultado) logueadas, por pregunta.
"""
from __future__ import annotations

import math


def brier(ps: list[float], ys: list[int]) -> float:
    """Eq. (10)."""
    n = len(ps)
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / n if n else float("nan")


def reliability(ps: list[float], ys: list[int], bins: int = 10) -> list[tuple[int, float, float, int]]:
    """Por bin: (bin, confianza media, accuracy, n). Base de la curva y del ECE."""
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        s = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if not s:
            continue
        conf = sum(p for p, _ in s) / len(s)
        acc = sum(y for _, y in s) / len(s)
        out.append((b, conf, acc, len(s)))
    return out


def ece(ps: list[float], ys: list[int], bins: int = 10) -> float:
    """Eq. (11): promedio ponderado del |accuracy − confianza| por bin."""
    n = len(ps)
    if not n:
        return float("nan")
    return sum(cnt / n * abs(acc - conf) for _, conf, acc, cnt in reliability(ps, ys, bins))


def log_loss(ps: list[float], ys: list[int], eps: float = 1e-6) -> float:
    n = len(ps)
    if not n:
        return float("nan")
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in zip(ps, ys)) / n


def platt_fit(ps: list[float], ys: list[int], iters: int = 200, lr: float = 0.5) -> tuple[float, float]:
    """Ajusta p' = σ(a·logit(p) + b) por descenso de gradiente sobre la log-loss.
    Recalibración monótona que se aplica en la capa de política antes de
    dimensionar (nunca se reentrena el modelo)."""
    if not ps:
        return 1.0, 0.0
    xs = [_logit(p) for p in ps]
    a, b = 1.0, 0.0
    n = len(xs)
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in zip(xs, ys):
            e = _sig(a * x + b) - y
            ga += e * x
            gb += e
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


def platt_apply(p: float, ab: tuple[float, float]) -> float:
    a, b = ab
    return _sig(a * _logit(p) + b)


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def summarize(triples: list[dict]) -> dict:
    """Métricas por pregunta sobre las triples resueltas del loop.

    Cada triple trae `answers` (p por pregunta binaria, dist para direction) y
    `outcome` (y por pregunta). Devuelve {pregunta: {brier, ece, log_loss,
    n, base_rate, accuracy}}."""
    out = {}
    for q in ("toxic_flow", "liquidity_stressed"):
        ps = [t["answers"][q] for t in triples if q in t["outcome"]]
        ys = [t["outcome"][q] for t in triples if q in t["outcome"]]
        if ps:
            out[q] = _binary_metrics(ps, ys)
    # direction: se evalúa como "la opción elegida fue la correcta" con su p
    ps = [t["answers"]["direction_p"] for t in triples if "direction" in t["outcome"]]
    ys = [int(t["answers"]["direction"] == t["outcome"]["direction"]) for t in triples if "direction" in t["outcome"]]
    if ps:
        out["direction"] = _binary_metrics(ps, ys)
    return out


def _binary_metrics(ps, ys) -> dict:
    return {"n": len(ps), "brier": round(brier(ps, ys), 4), "ece": round(ece(ps, ys), 4),
            "log_loss": round(log_loss(ps, ys), 4), "base_rate": round(sum(ys) / len(ys), 4),
            "accuracy": round(sum(int((p >= 0.5) == bool(y)) for p, y in zip(ps, ys)) / len(ys), 4)}
