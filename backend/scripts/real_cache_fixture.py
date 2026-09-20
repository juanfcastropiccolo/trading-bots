"""Genera un cache de `futures_data` con el FORMATO de los datos reales
(perp_<SYM>_1d.csv y funding_<SYM>_1d.csv) a partir del mercado sintético.

Sirve para ejercitar el camino `--source real` de las cinco pruebas en un
entorno sin red (como este), y como fixture de tests: prueba que el
plumbing real (lectura de cache, alineación de matrices, high/low, funding)
funciona de punta a punta. NO son datos reales: la descarga real la hace
`futures_data.py` cuando hay salida hacia data.binance.vision.

Uso:  python scripts/real_cache_fixture.py --out /tmp/cache_fixture [--n-days 1500] [--seed 5]
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from synthetic_market import SYMBOLS, generate_market  # noqa: E402
from futures_data import perp_symbol  # noqa: E402


def write_fixture(out_dir: str, n_days: int = 1500, seed: int = 5, symbols=None) -> str:
    symbols = symbols or SYMBOLS
    os.makedirs(out_dir, exist_ok=True)
    mk = generate_market(n_days=n_days, seed=seed, symbols=symbols)
    for s in symbols:
        sym = perp_symbol(s)
        k = pd.DataFrame({
            "date": mk.close.index, "open": mk.close[s].shift(1).fillna(mk.close[s]).values,
            "high": mk.high[s].values, "low": mk.low[s].values, "close": mk.close[s].values,
            "volume": 1000.0,
        })
        k.to_csv(os.path.join(out_dir, f"perp_{sym}_1d.csv"), index=False)
        f = pd.DataFrame({"date": mk.funding.index, "funding": mk.funding[s].values, "n_settlements": 3})
        f.to_csv(os.path.join(out_dir, f"funding_{sym}_1d.csv"), index=False)
    return out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-days", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=5)
    a = ap.parse_args()
    write_fixture(a.out, a.n_days, a.seed)
    print(f"fixture con formato real escrito en {a.out} ({a.n_days} días, semilla {a.seed})")


if __name__ == "__main__":
    main()
