"""Tests del rebalanceo del paper trader long-only (momentum_paper.py).

Regresión del bug de "posiciones fantasma" (ago 2026): con el portafolio 100%
en una moneda, al entrar una segunda al target se compraba con $0 y quedaba
una clave con qty=0 que bloqueaba compras posteriores.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from momentum_paper import COST, TOP_K, rebalance  # noqa: E402

PRICES = {"LINK/USDT": 11.5, "XRP/USDT": 3.2, "ADA/USDT": 0.222, "ETH/USDT": 4500.0}


def value(state, s):
    return state["holdings"].get(s, 0.0) * PRICES[s]


def equity(state):
    return state["cash"] + sum(value(state, s) for s in state["holdings"])


def test_entrante_con_portafolio_lleno_se_financia_recortando_al_que_queda():
    # Caso real del 24 ago 2026: 100% LINK, entra XRP al target.
    state = {"cash": 0.0, "holdings": {"LINK/USDT": 9.58395816}, "history": [], "last_run": None}
    rebalance(state, ["XRP/USDT", "LINK/USDT"], PRICES)

    assert set(state["holdings"]) == {"XRP/USDT", "LINK/USDT"}
    assert all(q > 0 for q in state["holdings"].values()), "no debe haber posiciones con qty 0"
    # partes iguales (tolerancia por costos de 0.15% por lado)
    assert abs(value(state, "XRP/USDT") - value(state, "LINK/USDT")) < equity(state) * 0.01
    assert state["cash"] < 0.5


def test_repara_posicion_fantasma_existente_y_usa_el_cash_ocioso():
    # Estado real del 25 ago 2026: XRP con qty 0 y $55.60 ociosos.
    state = {"cash": 55.60, "holdings": {"XRP/USDT": 0.0, "ADA/USDT": 250.449},
             "history": [], "last_run": None}
    rebalance(state, ["ADA/USDT", "XRP/USDT"], PRICES)

    assert state["holdings"]["XRP/USDT"] > 0
    assert state["holdings"]["ADA/USDT"] > 0
    assert state["cash"] < 0.5


def test_un_solo_pick_deja_la_otra_mitad_en_cash_como_el_backtest():
    state = {"cash": 100.0, "holdings": {}, "history": [], "last_run": None}
    rebalance(state, ["ADA/USDT"], PRICES)

    assert set(state["holdings"]) == {"ADA/USDT"}
    assert abs(value(state, "ADA/USDT") - 50.0 * (1 - COST)) < 0.01
    assert abs(state["cash"] - 50.0) < 0.01


def test_sin_cambio_de_target_no_opera():
    state = {"cash": 0.0, "holdings": {"LINK/USDT": 4.0, "XRP/USDT": 15.0}, "history": [], "last_run": None}
    before = dict(state["holdings"]), state["cash"]
    trades = rebalance(state, ["XRP/USDT", "LINK/USDT"], PRICES)

    assert trades == []
    assert (dict(state["holdings"]), state["cash"]) == before


def test_salida_total_a_cash():
    state = {"cash": 0.0, "holdings": {"LINK/USDT": 4.0, "XRP/USDT": 15.0}, "history": [], "last_run": None}
    rebalance(state, [], PRICES)

    assert state["holdings"] == {}
    assert abs(state["cash"] - (4.0 * 11.5 + 15.0 * 3.2) * (1 - COST)) < 1e-6


def test_top_k_es_dos():
    assert TOP_K == 2
