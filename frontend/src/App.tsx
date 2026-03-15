import { useState, useEffect } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./components/Dashboard";
import StatusBar from "./components/StatusBar";

export interface TickData {
  agent_id: number;
  price: number;
  features: { ema_fast: number; ema_slow: number; rsi: number; atr: number; close: number } | null;
  signal: { direction: string; confidence: number; reason: string } | null;
  risk: { approved: boolean; rejection_reason: string | null } | null;
  trade: { side: string; quantity: number; price: number; fee: number; total_cost: number } | null;
  portfolio: {
    cash: number;
    equity: number;
    total_pnl: number;
    total_pnl_pct: number;
    max_drawdown: number;
    win_count: number;
    loss_count: number;
    total_trades: number;
  } | null;
  llm_reasoning: string | null;
  timestamp: string;
}

export interface AgentData {
  id: number;
  name: string;
  symbol: string;
  strategy: string;
  budget_usd: number;
  mode: string;
  is_active: boolean;
  cash: number;
  equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  win_count: number;
  loss_count: number;
  total_trades: number;
  max_drawdown: number;
}

export default function App() {
  const [agent, setAgent] = useState<AgentData | null>(null);
  const [ticks, setTicks] = useState<TickData[]>([]);
  const { lastMessage, isConnected } = useWebSocket("/ws/live");

  // Fetch agent on mount
  useEffect(() => {
    fetch("/api/agents")
      .then((r) => r.json())
      .then((data: AgentData[]) => {
        if (data.length > 0) setAgent(data[0]);
      })
      .catch(() => {});
  }, []);

  // Process WS messages
  useEffect(() => {
    if (!lastMessage) return;
    try {
      const msg = JSON.parse(lastMessage);
      if (msg.type === "tick" && msg.data) {
        const tick = msg.data as TickData;
        setTicks((prev) => [...prev.slice(-299), tick]);

        // Update agent summary from tick
        if (tick.portfolio) {
          setAgent((prev) =>
            prev
              ? {
                  ...prev,
                  cash: tick.portfolio!.cash,
                  equity: tick.portfolio!.equity,
                  total_pnl: tick.portfolio!.total_pnl,
                  total_pnl_pct: tick.portfolio!.total_pnl_pct,
                  max_drawdown: tick.portfolio!.max_drawdown,
                  win_count: tick.portfolio!.win_count,
                  loss_count: tick.portfolio!.loss_count,
                  total_trades: tick.portfolio!.total_trades,
                }
              : prev
          );
        }
      }
    } catch {}
  }, [lastMessage]);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      <header className="border-b border-gray-800 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-xl font-bold tracking-tight">
          Mission Control
          <span className="text-gray-500 font-normal ml-2 text-sm">PAPER MODE</span>
        </h1>
        <div className="flex items-center gap-3">
          <StatusBar isConnected={isConnected} lastTick={ticks[ticks.length - 1]} />
          <Dashboard.ResetButton />
        </div>
      </header>
      <main className="flex-1 overflow-auto">
        <Dashboard agent={agent} ticks={ticks} />
      </main>
    </div>
  );
}
