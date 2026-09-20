"""Batería de seis preguntas tipadas y los jueces que la responden (Sección V).

Las preguntas son atómicas (un factor cada una) y se componen en código
(policy.py). Los tres primitivos del modelo:
  Noul   → probabilidad en [0, 1] de que una afirmación sobre el estado sea cierta
  Choice → distribución sobre opciones predefinidas
  Score  → nivel en una rúbrica ordinal + distribución

Jueces con la misma interfaz `judge(snap, truth) -> Judgment | None`:
  JevJudge     el modelo real vía typesafe-sdk (necesita TYPESAFE_API_KEY y red)
  RulesJudge   heurísticas determinísticas: baseline "reglas" y último escalón
               de la escalera de fallback cuando el modelo no está disponible
  OracleJudge  solo con el mercado sintético: responde a partir de los latentes
               verdaderos con informatividad `a` y probabilidades calibradas
               por construcción (posterior bayesiano exacto). Sirve para
               responder "qué calidad de juicio hace falta para que el loop
               sea rentable" sin depender de la API.
  DelayedJudge envuelve otro juez y entrega su respuesta `delay` bloques tarde:
               baseline "LLM de frontera" (inteligente pero stale).
"""
from __future__ import annotations

import math
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field

REGIMES = ("trending", "mean_reverting", "high_vol", "crisis")
DIRECTIONS = ("up", "down", "neutral")
QUOTE_ENV = ("No", "Marginal", "Standard", "Excellent")            # 0..3
INVENTORY = ("None", "Mild", "Skew", "Reduce now")                 # 0..3

# Especificación declarativa; los objetos del SDK se construyen a demanda para
# que el resto del sistema no dependa de tener typesafe-sdk instalado.
QUESTION_SPECS = {
    "regime": {"type": "choice",
               "instructions": "Which regime best describes the current market state?",
               "criteria": {r: None for r in REGIMES}},
    "direction": {"type": "choice",
                  "instructions": "Where is the mid price more likely to be after the decision horizon?",
                  "criteria": {d: None for d in DIRECTIONS}},
    "toxic_flow": {"type": "noul", "instructions": "Is aggressive flow informed?"},
    "liquidity_stressed": {"type": "noul", "instructions": "Book thinner than 24h norm?"},
    "quote_env": {"type": "score",
                  "instructions": "How good is the current environment for posting two-sided quotes?",
                  "criteria": list(QUOTE_ENV)},
    "inventory_pressure": {"type": "score",
                           "instructions": "How urgently should inventory be reduced?",
                           "criteria": list(INVENTORY)},
}


def build_questions() -> dict:
    from typesafe_sdk import Choice, Noul, Score  # import tardío a propósito

    out = {}
    for name, spec in QUESTION_SPECS.items():
        if spec["type"] == "noul":
            out[name] = Noul(instructions=spec["instructions"])
        elif spec["type"] == "choice":
            out[name] = Choice(instructions=spec["instructions"], criteria=spec["criteria"])
        else:
            out[name] = Score(instructions=spec["instructions"], criteria=spec["criteria"])
    return out


@dataclass
class Answer:
    kind: str                      # noul | choice | score
    p: float | None = None         # noul
    choice: str | None = None      # choice
    score: int | None = None       # score (índice en la rúbrica)
    dist: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        if self.kind == "noul":
            return max(self.p, 1 - self.p)
        return max(self.dist.values()) if self.dist else 0.0

    @property
    def noul(self) -> float:
        return self.p


Judgment = dict[str, Answer]


def _choice(dist: dict) -> Answer:
    best = max(dist, key=dist.get)
    return Answer("choice", choice=best, dist=dict(dist))


def _score(dist: dict) -> Answer:
    best = max(dist, key=dist.get)
    return Answer("score", score=int(best), dist=dict(dist))


# ------------------------------------------------------------------ Jev real
class JevJudge:
    """Una llamada, seis preguntas, un snapshot. Timeout = deadline del bloque:
    una respuesta que llega después del deadline se descarta (Sección VI.C)."""

    name = "jev"

    def __init__(self, api_key: str | None = None, model: str = "jev-latest",
                 deadline_ms: float = 250.0, usd_per_mtok: float = 0.042):
        from typesafe_sdk import TypeSafeClient

        self.client = TypeSafeClient(api_key=api_key or os.environ.get("TYPESAFE_API_KEY"),
                                     timeout=deadline_ms / 1000)
        self.model = model
        self.questions = build_questions()
        self.deadline_ms = deadline_ms
        self.usd_per_mtok = usd_per_mtok
        self.calls = self.errors = self.late = 0
        self.tokens = 0
        self.latency_ms = 0.0

    @property
    def cost_usd(self) -> float:
        return self.tokens / 1e6 * self.usd_per_mtok

    def judge(self, snap: dict, truth: dict | None = None) -> Judgment | None:
        t0 = time.perf_counter()
        self.calls += 1
        try:
            res = self.client.system_one(snap, self.questions, model=self.model)
        except Exception:
            self.errors += 1
            self.latency_ms = (time.perf_counter() - t0) * 1000
            return None
        self.latency_ms = (time.perf_counter() - t0) * 1000
        self.tokens += getattr(res.usage, "input_tokens", 0) or 0
        if self.latency_ms > self.deadline_ms:
            self.late += 1
            return None
        return parse_sdk_response(res)


def parse_sdk_response(res) -> Judgment:
    """Traduce SystemOneResponse del SDK a nuestro Judgment. Se mantiene aparte
    para poder testearlo con un objeto simulado."""
    out: Judgment = {}
    for name, spec in QUESTION_SPECS.items():
        if spec["type"] == "noul":
            a = res.nouls[name]
            out[name] = Answer("noul", p=float(a.probability))
        elif spec["type"] == "choice":
            a = res.choices[name]
            out[name] = Answer("choice", choice=a.choice, dist={k: float(v) for k, v in a.probabilities.items()})
        else:
            a = res.scores[name]
            dist = {int(k): float(v) for k, v in a.probabilities.items()}
            out[name] = Answer("score", score=int(a.score), dist=dist)
    return out


# --------------------------------------------------------------------- reglas
def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def inventory_pressure(snap: dict, max_position: float) -> Answer:
    """Computable, no juicio: la misma para todos los jueces."""
    u = abs(snap["inventory"]) / max_position if max_position else 0.0
    lvl = 0 if u < 0.25 else 1 if u < 0.5 else 2 if u < 0.8 else 3
    dist = {k: (1.0 if k == lvl else 0.0) for k in range(4)}
    return Answer("score", score=lvl, dist=dist)


class RulesJudge:
    """Heurísticas de libro clásicas, expresadas como probabilidades para que
    el policy engine no cambie. Es el baseline "reglas determinísticas" de la
    Tabla VI y el fallback cuando Jev no responde."""

    name = "rules"

    def __init__(self, max_position: float = 1.0):
        self.max_position = max_position
        self.calls = 0
        self.latency_ms = 0.0
        self.cost_usd = 0.0

    def judge(self, snap: dict, truth: dict | None = None) -> Judgment:
        self.calls += 1
        flow = snap["aggr_buy"] - snap["aggr_sell"]
        intensity_z = snap["trade_intensity"]
        toxic = _sig(6 * (abs(flow) - 0.45) + 0.3 * (snap["vol_regime"] - 1))
        thin = snap["depth_3"] / snap["depth_norm"] if snap["depth_norm"] else 1.0
        stressed = _sig(8 * (0.6 - thin))
        d = 4 * flow + 2 * snap["imbalance"] + 200 * snap["ret_1m"]
        up, down = math.exp(d), math.exp(-d)
        neu = math.exp(0.6)
        z = up + down + neu
        direction = {"up": up / z, "down": down / z, "neutral": neu / z}
        vr = snap["vol_regime"]
        regime = {"trending": _sig(6 * abs(snap["ret_5m"]) * 100 - 1),
                  "mean_reverting": _sig(1 - vr), "high_vol": _sig(3 * (vr - 1.5)),
                  "crisis": _sig(3 * (vr - 3))}
        zr = sum(regime.values())
        regime = {k: v / zr for k, v in regime.items()}
        good = (1 - toxic) * (1 - stressed) * _sig(2 - vr) * _sig(snap["spread_bps"] - 1)
        lvl = 3 if good > 0.5 else 2 if good > 0.25 else 1 if good > 0.1 else 0
        qe = {k: 0.05 for k in range(4)}
        qe[lvl] = 0.85
        return {
            "regime": _choice(regime),
            "direction": _choice(direction),
            "toxic_flow": Answer("noul", p=toxic),
            "liquidity_stressed": Answer("noul", p=stressed),
            "quote_env": _score(qe),
            "inventory_pressure": inventory_pressure(snap, self.max_position),
        }


# -------------------------------------------------------------------- oráculo
class OracleJudge:
    """Juez calibrado por construcción sobre el mercado sintético.

    Para cada pregunta observa una señal ruidosa s_k ~ N(a·1[k = y], 1) por
    clase y responde el posterior bayesiano exacto
        P(y = k | s) ∝ π_k · exp(a·s_k),
    de modo que la probabilidad reportada es calibrada (eq. 5) y `a` controla
    cuánta información tiene: a = 0 es el prior (inútil), a → ∞ es el oráculo.
    Los priors π se estiman de los latentes del propio feed (base rates).
    """

    name = "oracle"

    def __init__(self, a: float, max_position: float, seed: int = 0, priors: dict | None = None,
                 latency_ms: float = 120.0, usd_per_call: float = 240 / 1e6 * 0.042):
        self.a = a
        self.max_position = max_position
        self.rng = random.Random(seed)
        self.priors = priors or {}
        self.latency_ms = latency_ms
        self.usd_per_call = usd_per_call
        self.calls = 0

    @property
    def cost_usd(self) -> float:
        return self.calls * self.usd_per_call

    def _posterior(self, labels: tuple, y, prior_key: str) -> dict:
        pri = self.priors.get(prior_key) or {k: 1 / len(labels) for k in labels}
        logits = {}
        for k in labels:
            s = self.a * (1.0 if k == y else 0.0) + self.rng.gauss(0, 1)
            logits[k] = math.log(max(pri.get(k, 1e-6), 1e-6)) + self.a * s
        m = max(logits.values())
        w = {k: math.exp(v - m) for k, v in logits.items()}
        z = sum(w.values())
        return {k: v / z for k, v in w.items()}

    def judge(self, snap: dict, truth: dict | None = None) -> Judgment:
        self.calls += 1
        t = truth or {}
        toxic = self._posterior((1, 0), int(t.get("toxic", 0)), "toxic")[1]
        stressed = self._posterior((1, 0), int(t.get("stressed", 0)), "stressed")[1]
        direction = self._posterior(DIRECTIONS, t.get("direction", "neutral"), "direction")
        regime = self._posterior(REGIMES, t.get("regime", "mean_reverting"), "regime")
        qe = self._posterior((0, 1, 2, 3), int(t.get("quote_env", 2)), "quote_env")
        return {
            "regime": _choice(regime),
            "direction": _choice(direction),
            "toxic_flow": Answer("noul", p=toxic),
            "liquidity_stressed": Answer("noul", p=stressed),
            "quote_env": _score(qe),
            "inventory_pressure": inventory_pressure(snap, self.max_position),
        }


class DelayedJudge:
    """Baseline "LLM de frontera": la misma calidad de juicio pero la respuesta
    llega `delay` bloques después y se aplica sobre un mercado que ya cambió."""

    def __init__(self, inner, delay: int, latency_ms: float | None = None):
        self.inner = inner
        self.delay = delay
        self.buf: deque[Judgment] = deque()
        self.name = f"delayed({inner.name},{delay})"
        self.latency_ms = latency_ms if latency_ms is not None else delay * 300.0
        self.calls = 0

    @property
    def cost_usd(self) -> float:
        return self.inner.cost_usd * 20  # tokens de salida + prompt largo: ~20× el costo de Jev

    def judge(self, snap: dict, truth: dict | None = None) -> Judgment | None:
        self.calls += 1
        self.buf.append(self.inner.judge(snap, truth))
        if len(self.buf) <= self.delay:
            return None
        j = self.buf.popleft()
        if j is not None:
            j["inventory_pressure"] = inventory_pressure(snap, self.inner.max_position)
        return j
