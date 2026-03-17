import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type SeriesMarker,
  type Time,
  type ISeriesMarkersPluginApi,
} from "lightweight-charts";
import type { TickData } from "../App";
import { API_BASE } from "../config";

interface Props {
  ticks: TickData[];
  symbol?: string;
}

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const TIMEFRAMES = [
  { label: "1m", value: "1m" },
  { label: "1H", value: "1h" },
  { label: "1D", value: "1d" },
  { label: "1W", value: "1w" },
];

// --- Indicator calculations ---

function calcEMA(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const result: (number | null)[] = [];
  let ema: number | null = null;
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else if (ema === null) {
      // Seed with SMA
      let sum = 0;
      for (let j = i - period + 1; j <= i; j++) sum += closes[j];
      ema = sum / period;
      result.push(ema);
    } else {
      ema = closes[i] * k + ema * (1 - k);
      result.push(ema);
    }
  }
  return result;
}

function calcRSI(closes: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [null];
  const gains: number[] = [];
  const losses: number[] = [];

  for (let i = 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? -change : 0);

    if (i < period) {
      result.push(null);
    } else if (i === period) {
      let avgGain = 0, avgLoss = 0;
      for (let j = 0; j < period; j++) {
        avgGain += gains[j];
        avgLoss += losses[j];
      }
      avgGain /= period;
      avgLoss /= period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(100 - 100 / (1 + rs));
    } else {
      // Use previous RSI to calculate smoothed
      const prevIdx = result.length - 1;
      const prevRsi = result[prevIdx];
      if (prevRsi === null) {
        result.push(null);
        continue;
      }
      // Wilder's smoothing
      const lastGain = gains[gains.length - 1];
      const lastLoss = losses[losses.length - 1];
      // We need to track avgGain/avgLoss separately for proper Wilder smoothing
      // Simplified: recalculate from scratch for accuracy
      let avgGain = 0, avgLoss = 0;
      for (let j = gains.length - period; j < gains.length; j++) {
        avgGain += gains[j];
        avgLoss += losses[j];
      }
      avgGain /= period;
      avgLoss /= period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push(100 - 100 / (1 + rs));
    }
  }
  return result;
}

export default function CandlestickChart({ ticks, symbol }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema9SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema21SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi70Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const rsi30Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [timeframe, setTimeframe] = useState("1h");
  const [historicalCandles, setHistoricalCandles] = useState<Candle[]>([]);
  const [showIndicators, setShowIndicators] = useState(true);
  const shouldFitRef = useRef(true);

  const fitContent = useCallback(() => {
    chartRef.current?.timeScale().fitContent();
  }, []);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#111827" },
        textColor: "#9CA3AF",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 420,
      timeScale: { timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });

    // Price pane (0) — Candles + EMAs
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10B981",
      downColor: "#EF4444",
      borderUpColor: "#10B981",
      borderDownColor: "#EF4444",
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
    });

    const ema9Series = chart.addSeries(LineSeries, {
      color: "#3B82F6",
      lineWidth: 1,
      title: "EMA 9",
      crosshairMarkerVisible: false,
    });

    const ema21Series = chart.addSeries(LineSeries, {
      color: "#F97316",
      lineWidth: 1,
      title: "EMA 21",
      crosshairMarkerVisible: false,
    });

    // RSI pane (1) — separate panel below
    const rsiSeries = chart.addSeries(LineSeries, {
      color: "#A78BFA",
      lineWidth: 1,
      title: "RSI 14",
      priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(0) },
    }, 1);

    // RSI overbought/oversold levels
    const rsi70Series = chart.addSeries(LineSeries, {
      color: "#EF444466",
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(0) },
    }, 1);

    const rsi30Series = chart.addSeries(LineSeries, {
      color: "#10B98166",
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(0) },
    }, 1);

    const markers = createSeriesMarkers(candleSeries);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    ema9SeriesRef.current = ema9Series;
    ema21SeriesRef.current = ema21Series;
    rsiSeriesRef.current = rsiSeries;
    rsi70Ref.current = rsi70Series;
    rsi30Ref.current = rsi30Series;
    markersRef.current = markers;

    // Use ResizeObserver to react to container size changes (drag/resize panels)
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          chart.applyOptions({ width, height: Math.max(height, 200) });
        }
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, []);

  // Fetch historical candles when timeframe changes
  useEffect(() => {
    let cancelled = false;
    const pair = (symbol ?? "BTC/USDT").replace("/", "-");
    setHistoricalCandles([]);
    fetch(`${API_BASE}/api/market/${pair}/candles?timeframe=${timeframe}&limit=500`)
      .then((r) => r.json())
      .then((data: Candle[]) => {
        if (!cancelled) {
          shouldFitRef.current = true;
          setHistoricalCandles(data);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [timeframe, symbol]);

  // Update chart data
  useEffect(() => {
    if (!candleSeriesRef.current || !ema9SeriesRef.current || !ema21SeriesRef.current || !rsiSeriesRef.current) return;

    // Build candle data from historical + live
    const rawCandles = historicalCandles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const markerList: SeriesMarker<Time>[] = [];

    if (timeframe === "1m" && ticks.length > 0) {
      for (const tick of ticks) {
        if (!tick.features) continue;
        const time = (new Date(tick.timestamp).getTime() / 1000) as Time;
        rawCandles.push({
          time,
          open: tick.price * 0.9999,
          high: tick.price * 1.0002,
          low: tick.price * 0.9998,
          close: tick.price,
        });
        if (tick.trade) {
          markerList.push({
            time,
            position: tick.trade.side === "buy" ? "belowBar" : "aboveBar",
            color: tick.trade.side === "buy" ? "#10B981" : "#EF4444",
            shape: tick.trade.side === "buy" ? "arrowUp" : "arrowDown",
            text: tick.trade.side.toUpperCase(),
          });
        }
      }
    }

    // Deduplicate
    const seen = new Map<number, CandlestickData<Time>>();
    for (const c of rawCandles) seen.set(c.time as number, c);
    const candles = Array.from(seen.values()).sort((a, b) => (a.time as number) - (b.time as number));

    if (candles.length === 0) return;

    candleSeriesRef.current.setData(candles);
    if (markersRef.current) markersRef.current.setMarkers(markerList);

    // Calculate and set indicators
    if (showIndicators) {
      const closes = candles.map((c) => c.close);
      const times = candles.map((c) => c.time);

      const ema9 = calcEMA(closes, 9);
      const ema21 = calcEMA(closes, 21);
      const rsi = calcRSI(closes, 14);

      const ema9Data: LineData<Time>[] = [];
      const ema21Data: LineData<Time>[] = [];
      const rsiData: LineData<Time>[] = [];
      const rsi70Data: LineData<Time>[] = [];
      const rsi30Data: LineData<Time>[] = [];

      for (let i = 0; i < candles.length; i++) {
        if (ema9[i] !== null) ema9Data.push({ time: times[i], value: ema9[i]! });
        if (ema21[i] !== null) ema21Data.push({ time: times[i], value: ema21[i]! });
        if (rsi[i] !== null) {
          rsiData.push({ time: times[i], value: rsi[i]! });
          rsi70Data.push({ time: times[i], value: 70 });
          rsi30Data.push({ time: times[i], value: 30 });
        }
      }

      ema9SeriesRef.current.setData(ema9Data);
      ema21SeriesRef.current.setData(ema21Data);
      rsiSeriesRef.current!.setData(rsiData);
      rsi70Ref.current!.setData(rsi70Data);
      rsi30Ref.current!.setData(rsi30Data);
    } else {
      ema9SeriesRef.current.setData([]);
      ema21SeriesRef.current.setData([]);
      rsiSeriesRef.current!.setData([]);
      rsi70Ref.current!.setData([]);
      rsi30Ref.current!.setData([]);
    }
    // Auto-fit after new data loads (symbol change, timeframe change)
    if (shouldFitRef.current) {
      shouldFitRef.current = false;
      chartRef.current?.timeScale().fitContent();
    }
  }, [historicalCandles, ticks, timeframe, showIndicators]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 mb-2 shrink-0">
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
                timeframe === tf.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
        <div className="h-4 w-px bg-gray-700" />
        <button
          onClick={() => chartRef.current?.timeScale().fitContent()}
          className="px-2 py-1 text-xs rounded font-medium transition-colors bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
          title="Fit all candles"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9m11.25-5.25v4.5m0-4.5h-4.5m4.5 0L15 9m-11.25 11.25v-4.5m0 4.5h4.5m-4.5 0L9 15m11.25 5.25v-4.5m0 4.5h-4.5m4.5 0L15 15" />
          </svg>
        </button>
        <div className="h-4 w-px bg-gray-700" />
        <button
          onClick={() => setShowIndicators(!showIndicators)}
          className={`px-3 py-1 text-xs rounded font-medium transition-colors ${
            showIndicators
              ? "bg-purple-600/30 text-purple-300 border border-purple-500/50"
              : "bg-gray-800 text-gray-400 hover:bg-gray-700"
          }`}
        >
          Indicators
        </button>
        {showIndicators && (
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-blue-500 inline-block" /> EMA 9
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-orange-500 inline-block" /> EMA 21
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-purple-400 inline-block" /> RSI 14
            </span>
          </div>
        )}
      </div>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}
