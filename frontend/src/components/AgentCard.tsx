import type { AgentData, TickData } from "../App";

interface Props {
  agent: AgentData;
  lastTick?: TickData;
}

export default function AgentCard({ agent, lastTick }: Props) {
  const pnlColor = agent.total_pnl >= 0 ? "text-green-400" : "text-red-400";
  const price = lastTick?.price ?? 0;
  const posQty = agent.position_qty ?? 0;
  const posValue = posQty * price;
  const coinSymbol = agent.symbol.split("/")[0]; // "BTC" from "BTC/USDT"
  // More decimals for tiny fractions (BTC), fewer for larger holdings (ADA)
  const qtyDecimals = posQty === 0 ? 0 : posQty < 0.001 ? 8 : posQty < 1 ? 6 : posQty < 100 ? 4 : 2;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold">{agent.name}</h2>
          <span className="text-xs text-gray-500">{agent.symbol} / {agent.strategy}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${agent.is_active ? "bg-green-500" : "bg-red-500"}`} />
          <span className="text-xs uppercase bg-yellow-900 text-yellow-300 px-2 py-0.5 rounded">
            {agent.mode}
          </span>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-gray-500">Price</span>
          <span className="text-sm font-mono font-semibold">${price.toLocaleString()}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-gray-500">Equity</span>
          <div className="text-right">
            <span className="text-sm font-mono font-semibold">${agent.equity.toFixed(2)}</span>
            <div className="flex items-center gap-2 justify-end text-xs text-gray-500 font-mono">
              <span>${agent.cash.toFixed(2)} USD</span>
              <span className="text-gray-700">+</span>
              <span className={posQty > 0 ? "text-blue-400" : ""}>
                {posQty > 0 ? posQty.toFixed(qtyDecimals) : "0"} {coinSymbol}
                {" "}(${posValue.toFixed(2)})
              </span>
            </div>
          </div>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-gray-500">PnL</span>
          <span className={`text-sm font-mono font-semibold ${pnlColor}`}>
            {agent.total_pnl >= 0 ? "+" : ""}${agent.total_pnl.toFixed(2)}
            <span className="text-xs ml-1 text-gray-500">({agent.total_pnl_pct.toFixed(2)}%)</span>
          </span>
        </div>
      </div>
    </div>
  );
}
