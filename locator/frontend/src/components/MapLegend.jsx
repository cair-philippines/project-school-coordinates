import { useState } from "react";
import { Info, ChevronDown } from "lucide-react";

const LEGEND_ITEMS = [
  {
    visual: <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />,
    label: "DepEd Public",
  },
  {
    visual: <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-500" />,
    label: "DepEd Private",
  },
  {
    visual: (
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#7c3aed" }} />
    ),
    label: "CHED Public / SUC / Gov",
  },
  {
    visual: (
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#a78bfa" }} />
    ),
    label: "CHED Private",
  },
  {
    visual: (
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#f97316" }} />
    ),
    label: "TESDA",
  },
  {
    visual: (
      <span className="relative inline-block h-3 w-3">
        <span className="absolute inset-0.5 rounded-full bg-green-500" />
        <span className="absolute inset-0 rounded-full border-2 border-orange-400 opacity-70" />
      </span>
    ),
    label: "Wrong municipality / round coords",
  },
  {
    visual: (
      <span className="relative inline-block h-2.5 w-2.5">
        <span className="absolute inset-0 rounded-full bg-green-500" />
        <span className="absolute inset-0 rounded-full bg-red-400 animate-ping opacity-50" />
      </span>
    ),
    label: "Outside all polygons",
  },
  {
    visual: (
      <span className="relative inline-flex items-center justify-center h-3.5 w-3.5">
        <span className="absolute inset-0.5 rounded-full bg-blue-500" />
        <span
          className="relative text-[10px] font-black text-red-500 leading-none"
          style={{ textShadow: "0 0 1px white" }}
        >
          ×
        </span>
      </span>
    ),
    label: "Known fake coordinate",
  },
  {
    visual: <span className="inline-block h-2.5 w-2.5 rounded-full bg-gray-400" />,
    label: "Unknown status",
  },
];

export default function MapLegend() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="absolute bottom-3 left-3 z-[1000]">
      <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-md overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors w-full"
        >
          <Info className="h-3 w-3" />
          Legend
          <ChevronDown
            className={`h-3 w-3 ml-auto transition-transform ${expanded ? "rotate-180" : ""}`}
          />
        </button>

        {expanded && (
          <div className="px-2.5 pb-2 space-y-1.5 border-t border-[var(--border)] pt-1.5">
            {LEGEND_ITEMS.map(({ visual, label }) => (
              <div key={label} className="flex items-center gap-2">
                <div className="w-4 flex items-center justify-center shrink-0">
                  {visual}
                </div>
                <span className="text-[10px] text-[var(--muted-foreground)]">
                  {label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
