import { useState, useEffect } from "react";
import type { TickData } from "../App";

interface Props {
  ticks: TickData[];
  agentId?: number;
}

interface HistoricalTrade {
  id: number;
  side: string;
  quantity: number;
  price: number;
  fee: number;
  total_cost: number;
  status: string;
  mode: string;
  created_at: string;
}

type SideFilter = "ALL" | "BUY" | "SELL";

export default function TradeLog({ ticks, agentId }: Props) {
  const [historicalTrades, setHistoricalTrades] = useState<HistoricalTrade[]>([]);
  const [sideFilter, setSideFilter] = useState<SideFilter>("ALL");

  useEffect(() => {
    if (!agentId) return;
    fetch(`/api/agents/${agentId}/trades?limit=50`)
      .then((r) => r.json())
      .then((data: HistoricalTrade[]) => setHistoricalTrades(data))
      .catch(() => {});
  }, [agentId]);

  // Build unified list
  type UnifiedTrade = {
    key: string;
    side: string;
    quantity: number;
    price: number;
    fee: number;
    totalCost: number;
    timestamp: string;
  };

  const liveTrades: UnifiedTrade[] = ticks
    .filter((t) => t.trade !== null)
    .reverse()
    .map((t, i) => ({
      key: `live-${i}`,
      side: t.trade!.side,
      quantity: t.trade!.quantity,
      price: t.trade!.price,
      fee: t.trade!.fee,
      totalCost: t.trade!.total_cost,
      timestamp: t.timestamp,
    }));

  const histTrades: UnifiedTrade[] = historicalTrades.map((t) => ({
    key: `hist-${t.id}`,
    side: t.side,
    quantity: t.quantity,
    price: t.price,
    fee: t.fee,
    totalCost: t.total_cost,
    timestamp: t.created_at,
  }));

  const allTrades = liveTrades.length > 0 ? liveTrades : histTrades;

  const filtered = allTrades.filter(
    (t) => sideFilter === "ALL" || t.side.toUpperCase() === sideFilter
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-400">Trade Log</h2>
        <div className="flex gap-1">
          {(["ALL", "BUY", "SELL"] as SideFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setSideFilter(f)}
              className={`px-2 py-0.5 text-xs rounded transition-colors ${
                sideFilter === f
                  ? f === "BUY" ? "bg-green-900/50 text-green-400"
                  : f === "SELL" ? "bg-red-900/50 text-red-400"
                  : "bg-blue-900/50 text-blue-400"
                  : "bg-gray-800/50 text-gray-500 hover:text-gray-300"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-gray-500 text-sm">
          {allTrades.length === 0 ? "No trades yet. Waiting for signals..." : "No trades match filter."}
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-xs border-b border-gray-800">
              <th className="text-left py-1">Time</th>
              <th className="text-left py-1">Side</th>
              <th className="text-right py-1">Qty</th>
              <th className="text-right py-1">Price</th>
              <th className="text-right py-1">Fee</th>
              <th className="text-right py-1">Total</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((trade) => (
              <tr key={trade.key} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="py-1 text-gray-400 font-mono text-xs">
                  {new Date(trade.timestamp).toLocaleTimeString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })}
                </td>
                <td className={`py-1 font-semibold ${trade.side === "buy" ? "text-green-400" : "text-red-400"}`}>
                  {trade.side.toUpperCase()}
                </td>
                <td className="py-1 text-right font-mono">{trade.quantity.toFixed(6)}</td>
                <td className="py-1 text-right font-mono">${trade.price.toLocaleString()}</td>
                <td className="py-1 text-right font-mono text-gray-500">${trade.fee.toFixed(4)}</td>
                <td className="py-1 text-right font-mono">${trade.totalCost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
