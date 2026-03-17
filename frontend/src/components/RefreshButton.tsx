import { useState, useRef, useEffect } from "react";

const INTERVALS = [
  { label: "Off", value: 0 },
  { label: "10s", value: 10 },
  { label: "30s", value: 30 },
  { label: "1m", value: 60 },
  { label: "5m", value: 300 },
];

interface Props {
  onRefresh: () => void;
  interval: number;
  onIntervalChange: (seconds: number) => void;
}

export default function RefreshButton({ onRefresh, interval, onIntervalChange }: Props) {
  const [open, setOpen] = useState(false);
  const [spinning, setSpinning] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleRefresh = () => {
    setSpinning(true);
    onRefresh();
    setTimeout(() => setSpinning(false), 600);
  };

  const activeLabel = INTERVALS.find((i) => i.value === interval)?.label ?? "Off";

  return (
    <div className="relative" ref={dropdownRef}>
      <div className="flex items-center">
        {/* Refresh button */}
        <button
          onClick={handleRefresh}
          className="px-2 py-1 text-xs rounded-l font-medium bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors border-r border-gray-700"
          title="Refresh now"
        >
          <svg
            className={`w-3.5 h-3.5 ${spinning ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M20.016 4.356v4.992"
            />
          </svg>
        </button>
        {/* Dropdown toggle */}
        <button
          onClick={() => setOpen(!open)}
          className={`px-2 py-1 text-xs rounded-r font-medium transition-colors flex items-center gap-1 ${
            interval > 0
              ? "bg-blue-600/30 text-blue-400 hover:bg-blue-600/40"
              : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
          }`}
          title="Auto-refresh interval"
        >
          {interval > 0 && <span>{activeLabel}</span>}
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </button>
      </div>

      {/* Dropdown menu */}
      {open && (
        <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded shadow-lg z-50 py-1 min-w-[120px]">
          <div className="px-3 py-1.5 text-xs text-gray-500 font-semibold uppercase tracking-wider">
            Auto-refresh
          </div>
          {INTERVALS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                onIntervalChange(opt.value);
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-1.5 text-xs transition-colors ${
                interval === opt.value
                  ? "bg-blue-600/20 text-blue-400"
                  : "text-gray-300 hover:bg-gray-700"
              }`}
            >
              {opt.label}
              {opt.value > 0 && interval === opt.value && (
                <span className="float-right text-blue-400">&#10003;</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
