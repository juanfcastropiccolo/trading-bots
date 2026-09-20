"""Tests de la POC de market making con Jev (backend/jev).

Cubren lo que el paper exige que sea determinístico y verificable en código:
snapshot causal y compacto, vetos antes que señales, Kelly y A-S, post-only
con cola, calibración medida sobre las triples y consistencia de resultados.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jev.battery import (Answer, DelayedJudge, OracleJudge, RulesJudge,  # noqa: E402
                         parse_sdk_response)
from jev.calibration import brier, ece, platt_apply, platt_fit  # noqa: E402
from jev.feeds import MARKETS, MarketParams, SyntheticMarket, read_jsonl, write_jsonl  # noqa: E402
from jev.loop import LoopConfig, run  # noqa: E402
from jev.policy import (Action, Thresholds, avellaneda_stoikov, compose,  # noqa: E402
                        kelly_fraction, price_quotes)
from jev.risk import Limits, RiskEngine  # noqa: E402
from jev.state import BlockEvent, PortfolioView, StateEngine, approx_tokens  # noqa: E402
from jev.venue import PaperVenue, VenueCosts  # noqa: E402

TICK = 1e-6


def book(bid=1.0000, ask=1.0016, size=1000.0, prints=(), block=0):
    bids = [(bid - i * TICK, size * (i + 1)) for i in range(3)]
    asks = [(ask + i * TICK, size * (i + 1)) for i in range(3)]
    return BlockEvent(block, block * 0.3, bids, asks, list(prints))


@pytest.fixture(scope="module")
def market():
    mk = SyntheticMarket(MARKETS["hostil"].params, 6000, seed=7)
    return mk, mk.generate()


def snapshot_fixture():
    eng = StateEngine(w_1m=20, w_5m=50, w_30m=100, w_regime=200)
    for i in range(60):
        eng.update(book(block=i, prints=[("buy", 1.0016, 100.0)] if i % 3 == 0 else []))
    snap = eng.snapshot(PortfolioView())
    assert snap is not None
    return snap


# ------------------------------------------------------------------ estado
def test_snapshot_compacto_y_causal():
    snap = snapshot_fixture()
    assert approx_tokens(snap) < 400
    assert set(snap) >= {"mid", "microprice", "spread_bps", "imbalance", "depth_3", "aggr_buy",
                         "rvol_5m", "vol_regime", "inventory", "drawdown", "fill_ratio", "latency_ms"}
    assert abs(snap["mid"] - 1.0008) < 1e-9
    assert abs(snap["spread_bps"] - 0.0016 / 1.0008 * 1e4) < 1e-3
    assert snap["aggr_buy"] == 1.0 and snap["aggr_sell"] == 0.0


def test_snapshot_invalido_se_rechaza_no_se_manda():
    eng = StateEngine(w_1m=20, w_5m=50, w_30m=100, w_regime=200)
    assert eng.snapshot(PortfolioView()) is None            # sin warmup
    for i in range(60):
        eng.update(book(block=i))
    assert eng.snapshot(PortfolioView()) is not None
    eng.update(BlockEvent(61, 61 * 0.3, [(1.0, 0.0)], [(1.0016, 5.0)]))   # tamaño 0 en el mejor bid
    assert eng.snapshot(PortfolioView()) is None
    assert eng.rejections >= 2


# ----------------------------------------------------------------- política
def answers(toxic=0.1, stressed=0.1, qe=2, qconf=0.9, direction="neutral", dprob=0.5, inv_lvl=0):
    qd = {k: (1 - qconf) / 3 for k in range(4)}
    qd[qe] = qconf
    dd = {"up": (1 - dprob) / 2, "down": (1 - dprob) / 2, "neutral": (1 - dprob) / 2}
    dd[direction] = dprob
    inv = {k: (1.0 if k == inv_lvl else 0.0) for k in range(4)}
    return {"regime": Answer("choice", choice="mean_reverting", dist={"mean_reverting": 1.0}),
            "direction": Answer("choice", choice=direction, dist=dd),
            "toxic_flow": Answer("noul", p=toxic), "liquidity_stressed": Answer("noul", p=stressed),
            "quote_env": Answer("score", score=qe, dist=qd),
            "inventory_pressure": Answer("score", score=inv_lvl, dist=inv)}


def test_vetos_preceden_a_las_senales():
    snap = {"drawdown": 0.2, "inventory": 0.0}
    assert compose(answers(qe=3, qconf=0.99), snap, max_dd=0.1).action == Action.KILL
    snap["drawdown"] = 0.0
    assert compose(answers(toxic=0.7, qe=3, qconf=0.99), snap, 0.1).action == Action.PULL_QUOTES
    assert compose(answers(stressed=0.8, qe=3, qconf=0.99), snap, 0.1).action == Action.WIDEN
    assert compose(answers(qe=2, qconf=0.9), snap, 0.1).action == Action.QUOTE_BOTH
    assert compose(answers(qe=2, qconf=0.6), snap, 0.1).action == Action.QUOTE_WIDE   # baja confianza → reduce
    assert compose(answers(qe=1, qconf=0.9), snap, 0.1).action == Action.QUOTE_WIDE
    assert compose(answers(qe=0, qconf=0.9), snap, 0.1).action == Action.STAND_DOWN
    assert compose(None, snap, 0.1, mode="always").action == Action.QUOTE_BOTH


def test_pull_keep_reducing_solo_cotiza_el_lado_que_reduce():
    snap = {"drawdown": 0.0, "inventory": 150.0}
    d = compose(answers(toxic=0.9), snap, 0.1, Thresholds(pull_keep_reducing=True))
    assert d.action == Action.QUOTE_BOTH and d.size_bid == 0.0 and d.size_ask == 1.0


def test_kelly_fraccional_y_skew_de_inventario():
    assert kelly_fraction(0.5) == 0.0
    assert kelly_fraction(0.9) == pytest.approx(0.25 * 0.8)
    assert kelly_fraction(1.0, c=0.5) == 0.5
    snap = {"drawdown": 0.0, "inventory": 0.0}
    d = compose(answers(direction="up", dprob=0.9), snap, 0.1)
    assert d.size_bid > 1.0 > d.size_ask
    d = compose(answers(inv_lvl=3), {"drawdown": 0.0, "inventory": 300.0}, 0.1)
    assert d.size_bid == 0.0 and d.size_ask > 0          # "Reduce now" con inventario largo


def test_avellaneda_stoikov_formulas():
    r, delta = avellaneda_stoikov(mid=100.0, q=0.0, gamma=0.1, sigma=2.0, horizon=10.0, kappa=1.5)
    assert r == 100.0
    assert delta == pytest.approx(0.1 * 4 * 10 + 2 / 0.1 * math.log(1 + 0.1 / 1.5))
    r_long, _ = avellaneda_stoikov(100.0, q=1.0, gamma=0.1, sigma=2.0, horizon=10.0, kappa=1.5)
    assert r_long < r                                     # inventario largo → reserva más baja


def test_price_quotes_nunca_cruza_el_touch():
    snap = snapshot_fixture()
    snap["rvol_5m"] = 0.01
    dec = compose(answers(qe=3, qconf=0.95), {**snap, "drawdown": 0.0}, 0.1)
    bid, ask = price_quotes(snap, dec, TICK, 0.0, 200.0, __import__("jev.policy", fromlist=["PricingParams"]).PricingParams(),
                            best_bid=1.0, best_ask=1.0016)
    assert bid[0] <= 1.0016 - TICK + 1e-12 and ask[0] >= 1.0 + TICK - 1e-12
    assert bid[0] < ask[0]


# ------------------------------------------------------------------- riesgo
def test_riesgo_recorta_y_veta():
    lim = Limits(max_position=400, max_order=200, max_daily_loss=10, max_dd=0.1)
    eng = RiskEngine(lim)
    bid, ask = eng.clip_orders(inventory=300, bid=(1.0, 200), ask=(1.001, 200))
    assert bid[1] == 100 and ask[1] == 200                # solo entra lo que cabe
    v = eng.check(inventory=0, daily_pnl=-11, drawdown=0, stale_s=0, error_rate=0, latency_ms=0,
                  pos_age_s=0, bid=None, ask=None)
    assert not v.ok and v.kill
    v = eng.check(inventory=0, daily_pnl=0, drawdown=0, stale_s=0, error_rate=0, latency_ms=900,
                  pos_age_s=0, bid=(1.0, 100), ask=None)
    assert not v.ok and not v.kill and v.reason == "decision_latency"


# -------------------------------------------------------------------- venue
def test_post_only_con_cola_y_prints():
    ven = PaperVenue(VenueCosts(gas_usd_per_tx=0.001), TICK)
    ev0 = book(block=0)
    assert ven.replace(0, (1.0, 200.0), (1.0016, 200.0), ev0)            # nos unimos al touch: cola = L1
    assert ven.bid.queue_ahead == 1000.0
    assert ven.txs == 1 and ven.gas_usd == 0.001
    assert ven.on_block(book(block=0, prints=[("sell", 1.0, 5000)])) == []   # mismo bloque: todavía no descansa
    fills = ven.on_block(book(block=1, prints=[("sell", 1.0, 900)]))
    assert fills == [] and ven.bid.queue_ahead == 100.0                  # la cola absorbe el print
    fills = ven.on_block(book(block=2, prints=[("sell", 1.0, 250)]))
    assert len(fills) == 1 and fills[0].size == 150.0 and fills[0].side == "bid"
    assert ven.on_block(book(block=3, bid=0.9990, ask=0.9992)) and ven.bid is None   # el libro pasó a través: nos toman el resto
    ven2 = PaperVenue(VenueCosts(), TICK)
    assert not ven2.replace(0, (1.0016, 100.0), None, ev0)               # cruzaría el ask: rechazada
    assert ven2.rejected_post_only == 1 and ven2.bid is None
    assert not ven2.replace(1, None, None, ev0)                          # nada que hacer: sin tx


# ------------------------------------------------------------- calibración
def test_metricas_de_calibracion():
    ps = [0.9, 0.9, 0.1, 0.1]
    ys = [1, 1, 0, 0]
    assert brier(ps, ys) == pytest.approx(0.01)
    assert ece(ps, ys) == pytest.approx(0.1)
    assert ece([0.5] * 100, [1] * 50 + [0] * 50) == pytest.approx(0.0)
    a, b = platt_fit([0.7] * 50 + [0.3] * 50, [1] * 30 + [0] * 20 + [1] * 10 + [0] * 40)
    assert platt_apply(0.7, (a, b)) < 0.7                # estaba sobreconfiado → Platt lo baja


def test_oraculo_calibrado_y_reglas_no(market):
    mk, events = market
    lim = Limits(max_position=400, max_order=200, max_daily_loss=20, max_dd=0.15)
    cfg = LoopConfig(tick=mk.tick, base_size=200, limits=lim, costs=VenueCosts())
    r = run(events, OracleJudge(2.0, 400, seed=3, priors=mk.priors), cfg)
    cal = r.calibration
    assert cal["toxic_flow"]["ece"] < 0.05 and cal["direction"]["ece"] < 0.05
    assert cal["toxic_flow"]["accuracy"] > 0.8
    r0 = run(events, OracleJudge(0.0, 400, seed=3, priors=mk.priors), cfg)
    assert abs(r0.calibration["toxic_flow"]["accuracy"] - max(mk.priors["toxic"][0], mk.priors["toxic"][1])) < 0.05
    # las reglas son un juicio no calibrado: ECE claramente mayor
    rr = run(events, RulesJudge(400), cfg)
    assert rr.calibration["toxic_flow"]["ece"] > cal["toxic_flow"]["ece"]


def test_outcomes_del_loop_coinciden_con_la_verdad_del_feed(market):
    mk, events = market
    lim = Limits(max_position=400, max_order=200, max_daily_loss=20, max_dd=0.15)
    r = run(events, OracleJudge(2.0, 400, seed=3, priors=mk.priors),
            LoopConfig(tick=mk.tick, base_size=200, limits=lim, costs=VenueCosts()))
    assert len(r.triples) > 4000
    ok = sum(t["outcome"]["toxic_flow"] == t["truth"]["toxic"] and t["outcome"]["direction"] == t["truth"]["direction"]
             and t["outcome"]["liquidity_stressed"] == t["truth"]["stressed"] for t in r.triples)
    assert ok / len(r.triples) > 0.97


# ---------------------------------------------------------------------- loop
def test_loop_contabilidad_y_deadline(market):
    mk, events = market
    lim = Limits(max_position=400, max_order=200, max_daily_loss=20, max_dd=0.15)
    costs = VenueCosts(gas_usd_per_tx=0.0008, taker_fee_bps=10)
    cfg = LoopConfig(tick=mk.tick, base_size=200, limits=lim, costs=costs, policy_mode="always")
    r = run(events, RulesJudge(400), cfg)
    assert r.txs > 0 and r.gas == pytest.approx(r.txs * 0.0008)
    assert r.end_inventory == 0.0                                   # flatten al final
    assert r.max_tokens < 400
    # juez tarde con deadline → HOLD en todos los bloques, ninguna orden
    late = OracleJudge(2.0, 400, seed=3, priors=mk.priors, latency_ms=900)
    cfg2 = LoopConfig(tick=mk.tick, base_size=200, limits=lim, costs=costs, deadline_ms=250)
    r2 = run(events, late, cfg2)
    assert r2.fills == 0 and r2.txs == 0 and r2.holds > 5000
    # mismo juez sin deadline (baseline LLM) sí opera
    cfg2.enforce_deadline = False
    assert run(events, DelayedJudge(late, 10), cfg2).txs > 0


def test_kill_switch_aplana_y_para(market):
    mk, events = market
    lim = Limits(max_position=400, max_order=200, max_daily_loss=0.05, max_dd=0.15)
    cfg = LoopConfig(tick=mk.tick, base_size=200, limits=lim, costs=VenueCosts(gas_usd_per_tx=0.01), policy_mode="always")
    r = run(events, RulesJudge(400), cfg)
    assert r.killed and r.end_inventory == 0.0
    assert r.txs < 100                                              # paró enseguida


def test_feed_sintetico_reproducible_y_serializable(tmp_path):
    a = SyntheticMarket(MarketParams(), 300, seed=5).generate()
    b = SyntheticMarket(MarketParams(), 300, seed=5).generate()
    assert [e.mid for e in a] == [e.mid for e in b]
    p = tmp_path / "feed.jsonl"
    write_jsonl(a, str(p))
    c = list(read_jsonl(str(p)))
    assert len(c) == 300 and c[10].bids == a[10].bids and c[10].prints == a[10].prints


def test_parse_sdk_response_con_objeto_simulado():
    class A:  # imita typesafe_sdk: nouls[name].probability, choices[name].choice/probabilities, scores[name].score
        def __init__(self, **kw):
            self.__dict__.update(kw)

    res = A(nouls={"toxic_flow": A(probability=0.7), "liquidity_stressed": A(probability=0.2)},
            choices={"regime": A(choice="trending", probabilities={"trending": 0.6, "mean_reverting": 0.4}),
                     "direction": A(choice="up", probabilities={"up": 0.55, "down": 0.3, "neutral": 0.15})},
            scores={"quote_env": A(score=2, probabilities={"0": 0.1, "1": 0.1, "2": 0.7, "3": 0.1}),
                    "inventory_pressure": A(score=0, probabilities={"0": 1.0})})
    j = parse_sdk_response(res)
    assert j["toxic_flow"].p == 0.7 and j["direction"].choice == "up"
    assert j["quote_env"].score == 2 and j["quote_env"].confidence == 0.7
    assert compose(j, {"drawdown": 0.0, "inventory": 0.0}, 0.1).action == Action.PULL_QUOTES
