import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
}

export default function GridPanel({ title, children }: Props) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full flex flex-col overflow-hidden">
      <div className="drag-handle flex items-center gap-2 px-3 py-2 border-b border-gray-800 cursor-grab active:cursor-grabbing select-none shrink-0">
        <svg
          className="w-4 h-4 text-gray-600"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <circle cx="4" cy="3" r="1.5" />
          <circle cx="10" cy="3" r="1.5" />
          <circle cx="4" cy="8" r="1.5" />
          <circle cx="10" cy="8" r="1.5" />
          <circle cx="4" cy="13" r="1.5" />
          <circle cx="10" cy="13" r="1.5" />
        </svg>
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          {title}
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-3 no-drag">{children}</div>
    </div>
  );
}
