import { useState, useEffect, useCallback, useRef } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { API_BASE } from "./config";
import Dashboard from "./components/Dashboard";
import StatusBar from "./components/StatusBar";
import Sidebar from "./components/Sidebar";
import AddAgentModal from "./components/AddAgentModal";
import RefreshButton from "./components/RefreshButton";

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
    position_qty: number;
    position_side: string;
    entry_price: number;
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
  max_trade_usd: number;
  mode: string;
  is_active: boolean;
  is_protected: boolean;
  cash: number;
  equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  win_count: number;
  loss_count: number;
  total_trades: number;
  max_drawdown: number;
  position_qty: number;
  position_side: string;
  entry_price: number;
}

export default function App() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);
  const [ticksByAgent, setTicksByAgent] = useState<Record<number, TickData[]>>({});
  const [showAddModal, setShowAddModal] = useState(false);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState(0);
  const { lastMessage, isConnected } = useWebSocket("/ws/live");
  const selectedAgentIdRef = useRef(selectedAgentId);
  selectedAgentIdRef.current = selectedAgentId;

  const fetchAgents = useCallback(() => {
    fetch(`${API_BASE}/api/agents`)
      .then((r) => r.json())
      .then((data: AgentData[]) => {
        setAgents(data);
        if (data.length > 0 && selectedAgentIdRef.current === null) {
          setSelectedAgentId(data[0].id);
        }
      })
      .catch(() => {});
  }, []);

  // Fetch agents on mount
  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  // Auto-refresh interval
  useEffect(() => {
    if (autoRefreshInterval <= 0) return;
    const id = setInterval(fetchAgents, autoRefreshInterval * 1000);
    return () => clearInterval(id);
  }, [autoRefreshInterval, fetchAgents]);

  // Process WS messages — route by agent_id
  useEffect(() => {
    if (!lastMessage) return;
    try {
      const msg = JSON.parse(lastMessage);
      if (msg.type === "tick" && msg.data) {
        const tick = msg.data as TickData;
        const agentId = tick.agent_id;

        setTicksByAgent((prev) => ({
          ...prev,
          [agentId]: [...(prev[agentId] || []).slice(-299), tick],
        }));

        // Update agent summary from tick
        if (tick.portfolio) {
          setAgents((prev) =>
            prev.map((a) =>
              a.id === agentId
                ? {
                    ...a,
                    cash: tick.portfolio!.cash,
                    equity: tick.portfolio!.equity,
                    total_pnl: tick.portfolio!.total_pnl,
                    total_pnl_pct: tick.portfolio!.total_pnl_pct,
                    max_drawdown: tick.portfolio!.max_drawdown,
                    win_count: tick.portfolio!.win_count,
                    loss_count: tick.portfolio!.loss_count,
                    total_trades: tick.portfolio!.total_trades,
                    position_qty: tick.portfolio!.position_qty,
                    position_side: tick.portfolio!.position_side,
                    entry_price: tick.portfolio!.entry_price,
                  }
                : a
            )
          );
        }
      }
    } catch {}
  }, [lastMessage]);

  const selectedAgent = agents.find((a) => a.id === selectedAgentId) ?? null;
  const selectedTicks = selectedAgentId ? (ticksByAgent[selectedAgentId] || []) : [];
  const allTicks = Object.values(ticksByAgent).flat();
  const lastTick = allTicks.length > 0 ? allTicks[allTicks.length - 1] : undefined;

  const handleAddAgent = useCallback(async (data: Record<string, unknown>) => {
    try {
      const res = await fetch(`${API_BASE}/api/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        const newAgent: AgentData = await res.json();
        setAgents((prev) => [...prev, newAgent]);
        setSelectedAgentId(newAgent.id);
        setShowAddModal(false);
      }
    } catch {}
  }, []);

  const handleDeleteAgent = useCallback(async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/agents/${id}`, { method: "DELETE" });
      if (res.ok) {
        setAgents((prev) => prev.filter((a) => a.id !== id));
        setSelectedAgentId((prev) => {
          if (prev === id) {
            const remaining = agents.filter((a) => a.id !== id);
            return remaining.length > 0 ? remaining[0].id : null;
          }
          return prev;
        });
      }
    } catch {}
  }, [agents]);

  const handleToggleAgent = useCallback(async (id: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/agents/${id}/toggle`, { method: "PATCH" });
      if (res.ok) {
        const updated: AgentData = await res.json();
        setAgents((prev) => prev.map((a) => (a.id === id ? updated : a)));
      }
    } catch {}
  }, []);

  const handleAddFunds = useCallback(async (id: number) => {
    const input = prompt("Amount (USD) to add:");
    if (!input) return;
    const amount = parseFloat(input);
    if (isNaN(amount) || amount <= 0) return;
    try {
      const res = await fetch(`${API_BASE}/api/agents/${id}/add-funds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount }),
      });
      if (res.ok) {
        const updated: AgentData = await res.json();
        setAgents((prev) => prev.map((a) => (a.id === id ? updated : a)));
      }
    } catch {}
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col">
      <header className="border-b border-gray-800 px-4 py-2 flex items-center justify-between shrink-0">
        <h1 className="text-xl font-bold tracking-tight">
          Mission Control
          <span className="text-gray-500 font-normal ml-2 text-sm">PAPER MODE</span>
        </h1>
        <div className="flex items-center gap-3">
          <StatusBar isConnected={isConnected} lastTick={lastTick} />
          <Dashboard.ResetButton />
          <RefreshButton
            onRefresh={fetchAgents}
            interval={autoRefreshInterval}
            onIntervalChange={setAutoRefreshInterval}
          />
        </div>
      </header>
      <main className="flex-1 flex overflow-auto">
        <Sidebar
          agents={agents}
          selectedId={selectedAgentId}
          onSelect={setSelectedAgentId}
          onAddAgent={() => setShowAddModal(true)}
          onDeleteAgent={handleDeleteAgent}
          onAddFunds={handleAddFunds}
          onToggleAgent={handleToggleAgent}
        />
        <div className="flex-1 overflow-auto">
          <Dashboard agent={selectedAgent} ticks={selectedTicks} />
        </div>
      </main>
      <AddAgentModal
        open={showAddModal}
        existingSymbols={agents.map((a) => a.symbol)}
        onClose={() => setShowAddModal(false)}
        onCreate={handleAddAgent}
      />
    </div>
  );
}
