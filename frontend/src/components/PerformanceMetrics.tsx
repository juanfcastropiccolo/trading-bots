import type { AgentData } from "../App";

interface Props {
  agent: AgentData;
}

export default function PerformanceMetrics({ agent }: Props) {
  const winRate =
    agent.total_trades > 0
      ? ((agent.win_count / agent.total_trades) * 100).toFixed(1)
      : "0.0";

  const profitFactor =
    agent.loss_count > 0 && agent.win_count > 0
      ? (agent.win_count / agent.loss_count).toFixed(2)
      : "-";

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-gray-400 mb-3">Performance</h2>
      <div className="grid grid-cols-2 gap-4 text-center flex-1 content-center">
        <Metric label="Win Rate" value={`${winRate}%`} />
        <Metric label="Total Trades" value={String(agent.total_trades)} />
        <Metric label="W / L" value={`${agent.win_count} / ${agent.loss_count}`} />
        <Metric label="Profit Factor" value={profitFactor} />
        <Metric label="Max Drawdown" value={`${(agent.max_drawdown * 100).toFixed(2)}%`} warn={agent.max_drawdown > 0.1} />
        <Metric label="Cash" value={`$${agent.cash.toFixed(2)}`} />
        <Metric label="Budget" value={`$${agent.budget_usd.toFixed(2)}`} />
        <Metric label="Equity" value={`$${agent.equity.toFixed(2)}`} />
      </div>
    </div>
  );
}

function Metric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-sm font-mono font-semibold ${warn ? "text-yellow-400" : "text-gray-200"}`}>
        {value}
      </p>
    </div>
  );
}
