"""Tests del camino de datos reales de las pruebas A-E (market_data.py).

No hay red en el entorno de desarrollo, así que el "cache real" se fabrica
con real_cache_fixture.py (mismo formato de CSV que escribe futures_data.py)
y se verifica que load_market('real') y las pruebas lo consumen igual que
al mercado sintético.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from market_data import RunConfig, describe, load_market, parse_cli  # noqa: E402
from real_cache_fixture import write_fixture  # noqa: E402
from synthetic_market import SYMBOLS  # noqa: E402


@pytest.fixture(scope="module")
def cache_dir(tmp_path_factory):
    return write_fixture(str(tmp_path_factory.mktemp("cache")), n_days=700, seed=3)


def test_parse_cli_defaults_y_real():
    cfg = parse_cli("x", argv=[])
    assert cfg.source == "synthetic" and cfg.seeds == (42, 7, 123) and cfg.suffix == ""
    cfg = parse_cli("x", argv=["--source", "real", "--cache-dir", "/tmp/c"])
    assert cfg.source == "real" and cfg.seeds == (42,) and cfg.cache_dir == "/tmp/c"
    assert cfg.results_path("/x/breakout_results.json") == "/x/breakout_results_real.json"
    cfg = parse_cli("x", argv=["--seeds", "1,2", "-q", "tests/algo.py"])   # argv de pytest: se ignora
    assert cfg.seeds == (1, 2)


def test_load_market_real_desde_cache(cache_dir):
    mk = load_market("real", cache_dir=cache_dir)
    assert list(mk.close.columns) == SYMBOLS
    assert mk.close.shape == mk.high.shape == mk.low.shape == mk.funding.shape == (700, 10)
    assert (mk.high >= mk.close).all().all() and (mk.low <= mk.close).all().all()
    assert mk.close.index.is_monotonic_increasing and mk.close.index.name is None
    assert "700 días" in describe(mk)
    with pytest.raises(ValueError):
        load_market("otra_cosa")


def test_load_market_real_rechaza_historia_corta(tmp_path):
    short = write_fixture(str(tmp_path / "c"), n_days=100, seed=1)
    with pytest.raises(SystemExit):
        load_market("real", cache_dir=short)


def test_prueba_carry_corre_sobre_datos_reales(cache_dir, monkeypatch):
    import validate_carry as vc
    monkeypatch.setattr(vc, "SOURCE", "real")
    monkeypatch.setattr(vc, "CACHE_DIR", cache_dir)
    r = vc.run_seed(42)
    assert r["source"] == "real" and "700 días" in r["period"]
    assert set(r["dollar_neutral"]) == {"conservador_0.15%", "realista_0.05%"}


def test_prueba_pairs_sin_oraculo_con_datos_reales(cache_dir, monkeypatch):
    import validate_pairs as vp
    monkeypatch.setattr(vp, "SOURCE", "real")
    monkeypatch.setattr(vp, "CACHE_DIR", cache_dir)
    r = vp.run_seed(42)
    assert r["oracle"] is None and r["screening"]["match_stats"] is None
    assert len(r["screening"]["pairs_by_fold"]) == vp.N_FOLDS


def test_runconfig_label():
    assert "REALES" in RunConfig(source="real").label and "SINT" in RunConfig().label
