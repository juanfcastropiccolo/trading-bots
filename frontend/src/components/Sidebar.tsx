import { useState, useEffect } from "react";
import type { AgentData } from "../App";

const STORAGE_KEY = "sidebar-collapsed";

interface Props {
  agents: AgentData[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onAddAgent: () => void;
  onDeleteAgent: (id: number) => void;
  onAddFunds: (id: number) => void;
  onToggleAgent: (id: number) => void;
}

export default function Sidebar({ agents, selectedId, onSelect, onAddAgent, onDeleteAgent, onAddFunds, onToggleAgent }: Props) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(collapsed));
    } catch {}
  }, [collapsed]);

  const handleDelete = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (confirm("Delete this agent? It will stop trading but data is preserved.")) {
      onDeleteAgent(id);
    }
  };

  const handleToggle = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    onToggleAgent(id);
  };

  const handleFunds = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    onAddFunds(id);
  };

  return (
    <div
      className="shrink-0 border-r border-gray-800 bg-gray-900 flex flex-col transition-all duration-200"
      style={{ width: collapsed ? 48 : 220 }}
    >
      {/* Header: collapse toggle */}
      <div className="flex items-center border-b border-gray-800 shrink-0">
        {!collapsed && (
          <span className="flex-1 pl-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Agents</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-2.5 text-gray-500 hover:text-gray-300 transition-colors text-xs ml-auto"
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "\u25B6" : "\u25C0"}
        </button>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto py-2">
        {agents.map((agent) => {
          const isSelected = agent.id === selectedId;
          const pnl = agent.total_pnl ?? 0;
          const pnlColor = pnl >= 0 ? "text-green-400" : "text-red-400";
          const symbolShort = agent.symbol.split("/")[0];
          const dotColor = agent.is_active ? "bg-green-500" : "bg-gray-600";

          return (
            <div
              key={agent.id}
              onClick={() => onSelect(agent.id)}
              className={`cursor-pointer px-2 py-2 mx-1 rounded transition-colors ${
                isSelected ? "bg-gray-800" : "hover:bg-gray-800/50"
              }`}
            >
              {collapsed ? (
                <div className="flex flex-col items-center gap-1">
                  <span className="text-xs font-bold text-gray-300">{symbolShort.slice(0, 3)}</span>
                  <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                      <span className="text-sm font-medium text-gray-200 truncate">{agent.name}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 pl-3">
                      <span className="text-xs text-gray-500">{symbolShort}</span>
                      <span className={`text-xs font-mono ${pnlColor}`}>
                        {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    <button
                      onClick={(e) => handleToggle(e, agent.id)}
                      className={`p-1 rounded transition-colors ${
                        agent.is_active
                          ? "text-green-400 hover:text-red-400 hover:bg-gray-700"
                          : "text-gray-600 hover:text-green-400 hover:bg-gray-700"
                      }`}
                      title={agent.is_active ? "Pause agent" : "Resume agent"}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
                      </svg>
                    </button>
                    <button
                      onClick={(e) => handleFunds(e, agent.id)}
                      className="p-1 rounded text-gray-600 hover:text-yellow-400 hover:bg-gray-700 transition-colors"
                      title="Add funds"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </button>
                    {!agent.is_protected && (
                      <button
                        onClick={(e) => handleDelete(e, agent.id)}
                        className="p-1 rounded text-gray-600 hover:text-red-400 hover:bg-gray-700 transition-colors"
                        title="Delete agent"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {/* Add agent — inline after last agent */}
        <button
          onClick={onAddAgent}
          className={`mx-1 mt-1 py-2 rounded text-sm font-medium transition-colors flex items-center justify-center gap-1.5 w-[calc(100%-0.5rem)] bg-gray-800/50 text-gray-500 hover:bg-blue-600/20 hover:text-blue-400 ${collapsed ? "px-1" : "px-2"}`}
          title="Add agent"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          {!collapsed && <span>Add Agent</span>}
        </button>
      </div>

    </div>
  );
}
