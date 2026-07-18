"""Datos históricos de futuros perpetuos USDT-M: klines 1d y funding rates.

Fuente: bulk mensual de data.binance.vision (público, sin API key, sin
geo-block). Cache en backend/data/cache/. El mes en curso no tiene archivo
mensual todavía: la historia llega hasta el último mes completo, suficiente
para validación.

Convención de funding: rate positivo → los longs pagan a los shorts. La
agregación diaria suma los settlements del día (no asume 3×8h: el CSV trae
el intervalo).

Uso:  python scripts/futures_data.py   # descarga/actualiza todo y reporta sanity checks
"""
import io
import os
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date

import pandas as pd

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "LINK/USDT", "AVAX/USDT", "LTC/USDT",
]
START_MONTH = (2020, 9)  # SOL y AVAX listan sus perps en sep-2020

BASE = "https://data.binance.vision/data/futures/um/monthly"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def perp_symbol(spot: str) -> str:
    return spot.replace("/", "")


def _months(start: tuple[int, int]) -> list[str]:
    """Meses YYYY-MM desde start hasta el último mes completo."""
    today = date.today()
    end = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    out, (y, m) = [], start
    while (y, m) <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def _download_zip_csv(url: str, retries: int = 4) -> pd.DataFrame | None:
    """Baja un zip con un CSV adentro; None si el mes no existe (404)."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
        except (TimeoutError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        with zf.open(zf.namelist()[0]) as f:
            df = pd.read_csv(f, header=None)
    # algunos meses traen fila de header y otros no
    if not str(df.iloc[0, 0]).replace(".", "").isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    return df


def _load_or_build(cache_name: str, builder) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path):
        return pd.read_csv(path, parse_dates=["date"])
    df = builder()
    df.to_csv(path, index=False)
    return df


def fetch_perp_klines(spot: str) -> pd.DataFrame:
    """OHLCV diario del perp. Columnas: date, open, high, low, close, volume."""
    sym = perp_symbol(spot)

    def build():
        frames = []
        for month in _months(START_MONTH):
            df = _download_zip_csv(f"{BASE}/klines/{sym}/1d/{sym}-1d-{month}.zip")
            if df is None:
                continue
            df.columns = KLINE_COLS
            frames.append(df)
        if not frames:
            raise SystemExit(f"Sin klines de perp para {sym}")
        full = pd.concat(frames, ignore_index=True)
        # open_time viene en ms (o µs en meses recientes)
        ts = pd.to_numeric(full["open_time"])
        unit = "us" if ts.iloc[-1] > 1e14 else "ms"
        out = pd.DataFrame({
            "date": pd.to_datetime(ts, unit=unit).dt.normalize(),
            "open": pd.to_numeric(full["open"]),
            "high": pd.to_numeric(full["high"]),
            "low": pd.to_numeric(full["low"]),
            "close": pd.to_numeric(full["close"]),
            "volume": pd.to_numeric(full["volume"]),
        })
        return out.drop_duplicates("date").sort_values("date").reset_index(drop=True)

    return _load_or_build(f"perp_{sym}_1d.csv", build)


def fetch_funding_daily(spot: str) -> pd.DataFrame:
    """Funding agregado por día calendario UTC. Columnas: date, funding, n_settlements."""
    sym = perp_symbol(spot)

    def build():
        frames = []
        for month in _months(START_MONTH):
            df = _download_zip_csv(f"{BASE}/fundingRate/{sym}/{sym}-fundingRate-{month}.zip")
            if df is None:
                continue
            df.columns = ["calc_time", "funding_interval_hours", "rate"][: df.shape[1]]
            frames.append(df)
        if not frames:
            raise SystemExit(f"Sin funding para {sym}")
        full = pd.concat(frames, ignore_index=True)
        ts = pd.to_numeric(full["calc_time"])
        unit = "us" if ts.iloc[-1] > 1e14 else "ms"
        day = pd.to_datetime(ts, unit=unit).dt.normalize()
        rate = pd.to_numeric(full["rate"])
        g = rate.groupby(day)
        return pd.DataFrame({
            "date": g.sum().index,
            "funding": g.sum().values,
            "n_settlements": g.count().values,
        }).sort_values("date").reset_index(drop=True)

    return _load_or_build(f"funding_{sym}_1d.csv", build)


def build_matrices() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Matrices alineadas (fechas × símbolos): close, high, low, ret 1d, funding."""
    closes, highs, lows, fundings = {}, {}, {}, {}
    for s in SYMBOLS:
        k = fetch_perp_klines(s).set_index("date")
        closes[s], highs[s], lows[s] = k["close"], k["high"], k["low"]
        fundings[s] = fetch_funding_daily(s).set_index("date")["funding"]
    px = pd.DataFrame(closes).dropna()
    hi = pd.DataFrame(highs).reindex(px.index)
    lo = pd.DataFrame(lows).reindex(px.index)
    # días sin settlement (raro) = funding 0
    fund = pd.DataFrame(fundings).reindex(px.index).fillna(0.0)
    ret = px.pct_change().fillna(0)
    return px, hi, lo, ret, fund


def main():
    print("Descargando/verificando klines de perps y funding (bulk mensual Binance)…")
    for s in SYMBOLS:
        k = fetch_perp_klines(s)
        f = fetch_funding_daily(s)
        gaps = k["date"].diff().dt.days.fillna(1)
        max_gap = int(gaps.max())
        odd_days = int(((f["n_settlements"] < 1) | (f["n_settlements"] > 24)).sum())
        ann = f["funding"].mean() * 365 * 100
        print(f"{s:10s} klines {k['date'].iloc[0].date()} → {k['date'].iloc[-1].date()} "
              f"({len(k)}d, gap máx {max_gap}d) | funding {len(f)}d, "
              f"media anualizada {ann:+6.2f}%, días con settlements raros: {odd_days}")

    px, hi, lo, ret, fund = build_matrices()
    print(f"\nMatriz alineada: {px.shape[0]} días × {px.shape[1]} símbolos "
          f"({px.index[0].date()} → {px.index[-1].date()})")
    print(f"Funding cross-sectional medio anualizado: {fund.mean(axis=1).mean() * 365 * 100:+.2f}%")


if __name__ == "__main__":
    main()
