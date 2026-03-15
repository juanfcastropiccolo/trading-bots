import { useState, useEffect } from "react";
import type { TickData } from "../App";

interface Props {
  ticks: TickData[];
  agentId?: number;
}

interface HistoricalSignal {
  id: number;
  direction: string;
  confidence: number;
  reason: string | null;
  llm_reasoning: string | null;
  llm_recommendation: string | null;
  risk_approved: boolean | null;
  risk_reason: string | null;
  created_at: string;
}

type DirectionFilter = "ALL" | "BUY" | "SELL" | "HOLD";

export default function SignalLog({ ticks, agentId }: Props) {
  const [historicalSignals, setHistoricalSignals] = useState<HistoricalSignal[]>([]);
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [showLLM, setShowLLM] = useState(true);

  useEffect(() => {
    if (!agentId) return;
    fetch(`/api/agents/${agentId}/signals?limit=50`)
      .then((r) => r.json())
      .then((data: HistoricalSignal[]) => setHistoricalSignals(data))
      .catch(() => {});
  }, [agentId]);

  // Build unified signal list
  const liveSignals = ticks
    .filter((t) => t.signal !== null)
    .reverse()
    .slice(0, 50);

  type UnifiedSignal = {
    key: string;
    direction: string;
    confidence: number;
    reason: string | null;
    llmReasoning: string | null;
    riskApproved: boolean | null;
    riskReason: string | null;
    timestamp: string;
  };

  const signals: UnifiedSignal[] = liveSignals.length > 0
    ? liveSignals.map((t, i) => ({
        key: `live-${i}`,
        direction: t.signal!.direction,
        confidence: t.signal!.confidence,
        reason: t.signal!.reason,
        llmReasoning: t.llm_reasoning,
        riskApproved: t.risk?.approved ?? null,
        riskReason: t.risk?.rejection_reason ?? null,
        timestamp: t.timestamp,
      }))
    : historicalSignals.map((s) => ({
        key: `hist-${s.id}`,
        direction: s.direction,
        confidence: s.confidence,
        reason: s.reason,
        llmReasoning: s.llm_reasoning,
        riskApproved: s.risk_approved,
        riskReason: s.risk_reason,
        timestamp: s.created_at,
      }));

  const filtered = signals.filter(
    (s) => dirFilter === "ALL" || s.direction === dirFilter
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-400">Signal Log</h2>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {(["ALL", "BUY", "SELL", "HOLD"] as DirectionFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setDirFilter(f)}
                className={`px-2 py-0.5 text-xs rounded transition-colors ${
                  dirFilter === f
                    ? f === "BUY" ? "bg-green-900/50 text-green-400"
                    : f === "SELL" ? "bg-red-900/50 text-red-400"
                    : f === "HOLD" ? "bg-gray-700 text-gray-300"
                    : "bg-blue-900/50 text-blue-400"
                    : "bg-gray-800/50 text-gray-500 hover:text-gray-300"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowLLM(!showLLM)}
            className={`px-2 py-0.5 text-xs rounded transition-colors ${
              showLLM ? "bg-purple-900/30 text-purple-300" : "bg-gray-800/50 text-gray-500"
            }`}
          >
            LLM
          </button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-gray-500 text-sm">
          {signals.length === 0 ? "No signals yet. Waiting for first tick..." : "No signals match filter."}
        </p>
      ) : (
        <div className="space-y-2">
          {filtered.map((sig) => (
            <SignalCard key={sig.key} sig={sig} showLLM={showLLM} />
          ))}
        </div>
      )}
    </div>
  );
}

function SignalCard({
  sig,
  showLLM,
}: {
  sig: {
    direction: string;
    confidence: number;
    reason: string | null;
    llmReasoning: string | null;
    riskApproved: boolean | null;
    riskReason: string | null;
    timestamp: string;
  };
  showLLM: boolean;
}) {
  const dirColor =
    sig.direction === "BUY"
      ? "text-green-400 bg-green-900/30"
      : sig.direction === "SELL"
      ? "text-red-400 bg-red-900/30"
      : "text-gray-400 bg-gray-800/30";

  let llmText = "";
  if (sig.llmReasoning) {
    try {
      const parsed = JSON.parse(sig.llmReasoning);
      llmText = parsed.reasoning || sig.llmReasoning;
    } catch {
      llmText = sig.llmReasoning;
    }
  }

  const showRisk = sig.direction !== "HOLD" && sig.riskApproved !== null;

  return (
    <div className="border border-gray-800 rounded p-2 text-xs">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-xs font-bold ${dirColor}`}>
            {sig.direction}
          </span>
          {sig.confidence > 0 && (
            <span className="text-gray-500">conf: {(sig.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {showRisk && (
            <span
              className={`px-1.5 py-0.5 rounded text-xs ${
                sig.riskApproved ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"
              }`}
            >
              {sig.riskApproved ? "APPROVED" : "REJECTED"}
            </span>
          )}
          <span className="text-gray-600">{new Date(sig.timestamp).toLocaleTimeString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })}</span>
        </div>
      </div>
      {sig.reason && <p className="text-gray-400">{sig.reason}</p>}
      {showLLM && llmText && (
        <p className="text-blue-400/80 mt-1 italic">LLM: {llmText}</p>
      )}
      {showRisk && !sig.riskApproved && sig.riskReason && (
        <p className="text-red-400/70 mt-1">Risk: {sig.riskReason}</p>
      )}
    </div>
  );
}
