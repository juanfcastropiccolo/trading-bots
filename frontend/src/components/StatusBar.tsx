import type { TickData } from "../App";

interface Props {
  isConnected: boolean;
  lastTick?: TickData;
}

export default function StatusBar({ isConnected, lastTick }: Props) {
  return (
    <div className="flex items-center gap-4 text-xs text-gray-400">
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`} />
        <span>{isConnected ? "WS Connected" : "WS Disconnected"}</span>
      </div>
      {lastTick && (
        <span>
          Last tick: {new Date(lastTick.timestamp).toLocaleTimeString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })}
        </span>
      )}
    </div>
  );
}
