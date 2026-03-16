import { useState } from "react";

const SYMBOLS = [
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
  "ADA/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT", "MATIC/USDT",
];

const PROFILES: Record<string, {
  max_trade_usd: number;
  max_position_pct: number;
  drawdown_limit_pct: number;
  cooldown_minutes: number;
  max_consecutive_losses: number;
  rsi_buy_max: number;
  rsi_sell_min: number;
}> = {
  conservative: {
    max_trade_usd: 5, max_position_pct: 30, drawdown_limit_pct: 10,
    cooldown_minutes: 10, max_consecutive_losses: 2, rsi_buy_max: 65, rsi_sell_min: 35,
  },
  moderate: {
    max_trade_usd: 10, max_position_pct: 50, drawdown_limit_pct: 20,
    cooldown_minutes: 5, max_consecutive_losses: 3, rsi_buy_max: 70, rsi_sell_min: 30,
  },
  aggressive: {
    max_trade_usd: 20, max_position_pct: 75, drawdown_limit_pct: 30,
    cooldown_minutes: 2, max_consecutive_losses: 5, rsi_buy_max: 80, rsi_sell_min: 20,
  },
};

interface Props {
  open: boolean;
  existingSymbols: string[];
  onClose: () => void;
  onCreate: (data: Record<string, unknown>) => void;
}

export default function AddAgentModal({ open, existingSymbols, onClose, onCreate }: Props) {
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [budget, setBudget] = useState(100);
  const [profile, setProfile] = useState("moderate");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxTrade, setMaxTrade] = useState(10);
  const [maxPosition, setMaxPosition] = useState(50);
  const [drawdown, setDrawdown] = useState(20);
  const [cooldown, setCooldown] = useState(5);
  const [maxLosses, setMaxLosses] = useState(3);
  const [rsiBuyMax, setRsiBuyMax] = useState(70);
  const [rsiSellMin, setRsiSellMin] = useState(30);
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const applyProfile = (p: string) => {
    setProfile(p);
    const vals = PROFILES[p];
    if (vals) {
      setMaxTrade(vals.max_trade_usd);
      setMaxPosition(vals.max_position_pct);
      setDrawdown(vals.drawdown_limit_pct);
      setCooldown(vals.cooldown_minutes);
      setMaxLosses(vals.max_consecutive_losses);
      setRsiBuyMax(vals.rsi_buy_max);
      setRsiSellMin(vals.rsi_sell_min);
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !symbol) return;
    setSubmitting(true);
    onCreate({
      name: name.trim(),
      symbol,
      budget_usd: budget,
      max_trade_usd: maxTrade,
      risk_profile: profile,
      max_position_pct: maxPosition / 100,
      drawdown_limit_pct: drawdown / 100,
      daily_loss_limit_pct: profile === "conservative" ? 0.03 : profile === "aggressive" ? 0.10 : 0.05,
      cooldown_minutes: cooldown,
      max_consecutive_losses: maxLosses,
      rsi_buy_max: rsiBuyMax,
      rsi_sell_min: rsiSellMin,
    });
    setSubmitting(false);
  };

  const availableSymbols = SYMBOLS.filter((s) => !existingSymbols.includes(s));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-gray-100 mb-4">Add Agent</h2>

        {/* Name */}
        <label className="block text-xs text-gray-400 mb-1">Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="My SOL Agent"
          className="w-full mb-3 px-3 py-2 rounded bg-gray-800 border border-gray-700 text-gray-100 text-sm focus:outline-none focus:border-blue-500"
        />

        {/* Symbol */}
        <label className="block text-xs text-gray-400 mb-1">Symbol</label>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="w-full mb-3 px-3 py-2 rounded bg-gray-800 border border-gray-700 text-gray-100 text-sm focus:outline-none focus:border-blue-500"
        >
          <option value="">Select...</option>
          {availableSymbols.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        {/* Budget */}
        <label className="block text-xs text-gray-400 mb-1">Budget (USD)</label>
        <input
          type="number"
          value={budget}
          onChange={(e) => setBudget(Number(e.target.value))}
          min={10}
          className="w-full mb-3 px-3 py-2 rounded bg-gray-800 border border-gray-700 text-gray-100 text-sm focus:outline-none focus:border-blue-500"
        />

        {/* Risk Profile */}
        <label className="block text-xs text-gray-400 mb-1">Risk Profile</label>
        <div className="flex gap-2 mb-3">
          {(["conservative", "moderate", "aggressive"] as const).map((p) => (
            <button
              key={p}
              onClick={() => applyProfile(p)}
              className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${
                profile === p
                  ? p === "conservative" ? "bg-green-600/30 text-green-300 border border-green-500/50"
                  : p === "moderate" ? "bg-blue-600/30 text-blue-300 border border-blue-500/50"
                  : "bg-red-600/30 text-red-300 border border-red-500/50"
                  : "bg-gray-800 text-gray-400 border border-gray-700 hover:bg-gray-700"
              }`}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>

        {/* Advanced toggle */}
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-xs text-gray-500 hover:text-gray-300 mb-2"
        >
          {showAdvanced ? "\u25BC" : "\u25B6"} Advanced Settings
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Max Trade (USD)</label>
              <input type="number" value={maxTrade} onChange={(e) => setMaxTrade(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Max Position %</label>
              <input type="number" value={maxPosition} onChange={(e) => setMaxPosition(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Drawdown Limit %</label>
              <input type="number" value={drawdown} onChange={(e) => setDrawdown(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Cooldown (min)</label>
              <input type="number" value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">RSI Buy Max</label>
              <input type="number" value={rsiBuyMax} onChange={(e) => setRsiBuyMax(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">RSI Sell Min</label>
              <input type="number" value={rsiSellMin} onChange={(e) => setRsiSellMin(Number(e.target.value))}
                className="w-full px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-200 text-xs" />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded text-sm bg-gray-800 text-gray-400 hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!name.trim() || !symbol || submitting}
            className="px-4 py-1.5 rounded text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? "Creating..." : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
