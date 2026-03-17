import { useState, useEffect, useRef, useCallback } from "react";
import type { TickData } from "../App";
import { API_BASE } from "../config";

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

const PAGE_SIZE = 50;

export default function SignalLog({ ticks, agentId }: Props) {
  const [historicalSignals, setHistoricalSignals] = useState<HistoricalSignal[]>([]);
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [showLLM, setShowLLM] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Fetch initial page
  useEffect(() => {
    if (!agentId) return;
    setHistoricalSignals([]);
    setHasMore(true);
    fetch(`${API_BASE}/api/agents/${agentId}/signals?limit=${PAGE_SIZE}&offset=0`)
      .then((r) => r.json())
      .then((data: HistoricalSignal[]) => {
        setHistoricalSignals(data);
        setHasMore(data.length >= PAGE_SIZE);
      })
      .catch(() => {});
  }, [agentId]);

  // Load more when scrolling to bottom
  const loadMore = useCallback(() => {
    if (!agentId || loading || !hasMore) return;
    setLoading(true);
    const offset = historicalSignals.length;
    fetch(`${API_BASE}/api/agents/${agentId}/signals?limit=${PAGE_SIZE}&offset=${offset}`)
      .then((r) => r.json())
      .then((data: HistoricalSignal[]) => {
        setHistoricalSignals((prev) => [...prev, ...data]);
        setHasMore(data.length >= PAGE_SIZE);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [agentId, loading, hasMore, historicalSignals.length]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Load more when within 100px of bottom
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
      loadMore();
    }
  }, [loadMore]);

  // Build unified signal list
  const liveSignals = ticks
    .filter((t) => t.signal !== null)
    .reverse();

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

  // Combine live (newest) + historical, dedup by timestamp (live wins)
  const allSignals: UnifiedSignal[] = [
    ...liveSignals.map((t, i) => ({
      key: `live-${i}`,
      direction: t.signal!.direction,
      confidence: t.signal!.confidence,
      reason: t.signal!.reason,
      llmReasoning: t.llm_reasoning,
      riskApproved: t.risk?.approved ?? null,
      riskReason: t.risk?.rejection_reason ?? null,
      timestamp: t.timestamp,
    })),
    ...historicalSignals.map((s) => ({
      key: `hist-${s.id}`,
      direction: s.direction,
      confidence: s.confidence,
      reason: s.reason,
      llmReasoning: s.llm_reasoning,
      riskApproved: s.risk_approved,
      riskReason: s.risk_reason,
      timestamp: s.created_at,
    })),
  ];

  // Sort newest first, then deduplicate by timestamp
  allSignals.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  const seen = new Set<string>();
  const signals: UnifiedSignal[] = [];
  for (const s of allSignals) {
    const ts = new Date(s.timestamp).getTime().toString();
    if (!seen.has(ts)) {
      seen.add(ts);
      signals.push(s);
    }
  }

  const filtered = signals.filter(
    (s) => dirFilter === "ALL" || s.direction === dirFilter
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 shrink-0">
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
        <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto space-y-2 min-h-0">
          {filtered.map((sig) => (
            <SignalCard key={sig.key} sig={sig} showLLM={showLLM} />
          ))}
          {loading && <p className="text-gray-500 text-xs text-center py-2">Loading more...</p>}
          {!hasMore && filtered.length > PAGE_SIZE && (
            <p className="text-gray-600 text-xs text-center py-2">No more signals</p>
          )}
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
