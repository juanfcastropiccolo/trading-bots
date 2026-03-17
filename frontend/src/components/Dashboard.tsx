import { useState, useCallback } from "react";
import { ResponsiveGridLayout, useContainerWidth, type Layouts, type Layout } from "react-grid-layout";
import type { AgentData, TickData } from "../App";
import AgentCard from "./AgentCard";
import CandlestickChart from "./CandlestickChart";
import TradeLog from "./TradeLog";
import SignalLog from "./SignalLog";
import PerformanceMetrics from "./PerformanceMetrics";
import GridPanel from "./GridPanel";

const STORAGE_KEY = "dashboard-layouts";

const DEFAULT_LAYOUTS: Layouts = {
  lg: [
    { i: "agent", x: 0, y: 0, w: 3, h: 5, minW: 2, minH: 3 },
    { i: "performance", x: 0, y: 5, w: 3, h: 7, minW: 2, minH: 4 },
    { i: "chart", x: 3, y: 0, w: 9, h: 12, minW: 4, minH: 6 },
    { i: "signals", x: 0, y: 12, w: 6, h: 8, minW: 3, minH: 4 },
    { i: "trades", x: 6, y: 12, w: 6, h: 8, minW: 3, minH: 4 },
  ],
  md: [
    { i: "agent", x: 0, y: 0, w: 4, h: 5, minW: 2, minH: 3 },
    { i: "performance", x: 0, y: 5, w: 4, h: 7, minW: 2, minH: 4 },
    { i: "chart", x: 4, y: 0, w: 8, h: 12, minW: 4, minH: 6 },
    { i: "signals", x: 0, y: 12, w: 6, h: 8, minW: 3, minH: 4 },
    { i: "trades", x: 6, y: 12, w: 6, h: 8, minW: 3, minH: 4 },
  ],
  sm: [
    { i: "agent", x: 0, y: 0, w: 12, h: 4, minW: 2, minH: 3 },
    { i: "performance", x: 0, y: 4, w: 12, h: 6, minW: 2, minH: 4 },
    { i: "chart", x: 0, y: 10, w: 12, h: 10, minW: 4, minH: 6 },
    { i: "signals", x: 0, y: 20, w: 12, h: 7, minW: 3, minH: 4 },
    { i: "trades", x: 0, y: 27, w: 12, h: 7, minW: 3, minH: 4 },
  ],
  xs: [
    { i: "agent", x: 0, y: 0, w: 12, h: 4, minW: 2, minH: 3 },
    { i: "performance", x: 0, y: 4, w: 12, h: 6, minW: 2, minH: 4 },
    { i: "chart", x: 0, y: 10, w: 12, h: 10, minW: 4, minH: 6 },
    { i: "signals", x: 0, y: 20, w: 12, h: 7, minW: 3, minH: 4 },
    { i: "trades", x: 0, y: 27, w: 12, h: 7, minW: 3, minH: 4 },
  ],
};

function loadLayouts(): Layouts {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved);
  } catch {}
  return DEFAULT_LAYOUTS;
}

function resetLayouts() {
  localStorage.removeItem(STORAGE_KEY);
  window.location.reload();
}

function ResetButton() {
  return (
    <button
      onClick={resetLayouts}
      className="px-3 py-1 text-xs rounded font-medium bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors"
    >
      Reset Layout
    </button>
  );
}

interface Props {
  agent: AgentData | null;
  ticks: TickData[];
}

function Dashboard({ agent, ticks }: Props) {
  const [layouts, setLayouts] = useState<Layouts>(loadLayouts);
  const { width, containerRef } = useContainerWidth({ initialWidth: 1280 });

  const handleLayoutChange = useCallback((_layout: Layout[], allLayouts: Layouts) => {
    setLayouts(allLayouts);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(allLayouts));
    } catch {}
  }, []);

  // Always render the container div so the ref is attached and width is measured
  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      {!agent ? (
        <div className="flex items-center justify-center h-64 text-gray-500">
          Waiting for agent data...
        </div>
      ) : (
        <ResponsiveGridLayout
          className="layout"
          layouts={layouts}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480 }}
          cols={{ lg: 12, md: 12, sm: 12, xs: 12 }}
          rowHeight={30}
          width={width}
          margin={[8, 8]}
          containerPadding={[8, 8]}
          compactType="vertical"
          dragConfig={{ enabled: true, handle: ".drag-handle", cancel: ".no-drag" }}
          resizeConfig={{ enabled: true, handles: ["s", "w", "e", "n", "sw", "nw", "se", "ne"] }}
          onLayoutChange={handleLayoutChange}
        >
          <div key="agent">
            <GridPanel title="Agent">
              <AgentCard agent={agent} lastTick={ticks[ticks.length - 1]} />
            </GridPanel>
          </div>
          <div key="performance">
            <GridPanel title="Performance">
              <PerformanceMetrics agent={agent} />
            </GridPanel>
          </div>
          <div key="chart">
            <div key={`chart-${agent.id}`} className="h-full">
              <GridPanel title={`${agent.symbol} Chart`}>
                <CandlestickChart ticks={ticks} symbol={agent.symbol} />
              </GridPanel>
            </div>
          </div>
          <div key="signals">
            <GridPanel title="Signals">
              <SignalLog ticks={ticks} agentId={agent.id} />
            </GridPanel>
          </div>
          <div key="trades">
            <GridPanel title="Trades">
              <TradeLog ticks={ticks} agentId={agent.id} />
            </GridPanel>
          </div>
        </ResponsiveGridLayout>
      )}
    </div>
  );
}

Dashboard.ResetButton = ResetButton;
export default Dashboard;
