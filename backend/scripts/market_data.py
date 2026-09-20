"""Fuente de datos única para las pruebas A-E: mercado sintético o datos
reales, detrás de la misma interfaz (`synthetic_market.Market`).

    from market_data import load_market, parse_cli
    cfg = parse_cli("Prueba X")            # --source synthetic|real, --cache-dir, --seeds
    mk = load_market(cfg.source, seed=42)   # .close .high .low .funding (fecha × símbolo)

Datos reales: perpetuos USDT-M de Binance (klines 1d + funding diario) vía
`futures_data.py`, que baja el bulk mensual de data.binance.vision (público,
sin API key, sin geo-block en los runners de GitHub Actions) y lo cachea en
backend/data/cache/. Historia desde sep-2020 (cuando listan SOL y AVAX)
hasta el último mes completo, los mismos 10 majors del resto del repo.

Con `--source real` hay UNA sola historia, así que las "semillas" pasan a
ser una sola (42): la semilla solo alimenta al baseline aleatorio y al
random_state de los modelos, no a los datos. Los resultados se guardan con
sufijo `_real` para no pisar los sintéticos.

Sin red (como este entorno de desarrollo), `--source real` funciona igual
si backend/data/cache/ ya tiene los CSV: por eso el workflow
abcde-real.yml los commitea después de descargarlos.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

import pandas as pd

from synthetic_market import SYMBOLS, Market, generate_market

SOURCES = ("synthetic", "real")
DEFAULT_SEEDS = (42, 7, 123)
REAL_SEED = 42


@dataclass
class RunConfig:
    source: str = "synthetic"
    seeds: tuple = DEFAULT_SEEDS
    cache_dir: str | None = None

    @property
    def suffix(self) -> str:
        return "_real" if self.source == "real" else ""

    def results_path(self, base_path: str) -> str:
        root, ext = os.path.splitext(base_path)
        return f"{root}{self.suffix}{ext}"

    @property
    def label(self) -> str:
        return "datos REALES (perps Binance, bulk mensual)" if self.source == "real" else "mercado SINTÉTICO"


def parse_cli(description: str = "", argv: list[str] | None = None) -> RunConfig:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--source", choices=SOURCES, default="synthetic",
                    help="synthetic (default) o real (perps Binance vía futures_data.py)")
    ap.add_argument("--cache-dir", default=None,
                    help="directorio de cache de futures_data (default backend/data/cache)")
    ap.add_argument("--seeds", default=None,
                    help="semillas separadas por coma (default 42,7,123 sintético; 42 real)")
    a, _unknown = ap.parse_known_args(argv)   # tolera los argv de pytest cuando un test llama a main()
    if a.seeds:
        seeds = tuple(int(s) for s in a.seeds.split(","))
    else:
        seeds = (REAL_SEED,) if a.source == "real" else DEFAULT_SEEDS
    return RunConfig(source=a.source, seeds=seeds, cache_dir=a.cache_dir)


def load_real_market(cache_dir: str | None = None, symbols: list[str] | None = None) -> Market:
    """Matrices alineadas de perps reales. Descarga si falta cache (necesita
    red hacia data.binance.vision); si el cache está completo no toca la red."""
    import futures_data

    if cache_dir:
        futures_data.CACHE_DIR = cache_dir
    symbols = list(symbols or SYMBOLS)
    if symbols != list(futures_data.SYMBOLS):
        futures_data.SYMBOLS = symbols
    px, hi, lo, _ret, fund = futures_data.build_matrices()
    px = px[symbols]
    hi, lo, fund = hi[symbols], lo[symbols], fund[symbols]
    px.index.name = hi.index.name = lo.index.name = fund.index.name = None
    if len(px) < 400:
        raise SystemExit(f"Historia real demasiado corta ({len(px)} días): revisá el cache/descarga")
    # high/low faltantes (raro): los rellenamos con close para no romper ATR/Donchian
    hi = hi.fillna(px)
    lo = lo.fillna(px)
    regime = pd.Series(-1, index=px.index)   # no existe en la realidad
    return Market(close=px, high=hi, low=lo, funding=fund, regime=regime)


def load_market(source: str = "synthetic", seed: int = 42, n_days: int = 2190,
                cache_dir: str | None = None) -> Market:
    if source == "synthetic":
        return generate_market(n_days=n_days, seed=seed)
    if source == "real":
        return load_real_market(cache_dir)
    raise ValueError(f"source desconocida: {source!r} (opciones: {SOURCES})")


def describe(mk: Market) -> str:
    c = mk.close
    return (f"{len(c)} días ({c.index[0].date()} → {c.index[-1].date()}), {c.shape[1]} activos; "
            f"funding medio anualizado {mk.funding.mean().mean() * 365 * 100:+.1f}%")
