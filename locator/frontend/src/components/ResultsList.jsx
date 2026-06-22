import { MapPin, School, ChevronRight } from "lucide-react";

const SECTOR_ICON_COLOR = {
  public: "text-green-600",
  private: "text-blue-600",
  ched_public: "text-violet-600",
  ched_private: "text-violet-400",
  tesda: "text-orange-500",
};

const SECTOR_BADGE = {
  public:      { label: "DepEd",  bg: "bg-green-50",  text: "text-green-700" },
  private:     { label: "DepEd",  bg: "bg-blue-50",   text: "text-blue-700" },
  ched_public: { label: "CHED",   bg: "bg-violet-50", text: "text-violet-700" },
  ched_private:{ label: "CHED",   bg: "bg-violet-50", text: "text-violet-700" },
  tesda:       { label: "TESDA",  bg: "bg-orange-50", text: "text-orange-700" },
};

export default function ResultsList({ results, total, loading, onSelect, selectedId }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-[var(--muted-foreground)]">
        <div className="animate-pulse">Loading...</div>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-sm text-[var(--muted-foreground)] gap-2 px-4 text-center">
        <MapPin className="h-8 w-8 opacity-30" />
        <span>Search by name or select a region to see institutions</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs text-[var(--muted-foreground)] border-b border-[var(--border)] shrink-0">
        {total.toLocaleString()} institution{total !== 1 ? "s" : ""} found
        {results.length < total && ` (showing ${results.length})`}
      </div>
      <div className="flex-1 overflow-y-auto">
        {results.map((school) => {
          const iconColor = SECTOR_ICON_COLOR[school.sector] || "text-gray-500";
          const badge = SECTOR_BADGE[school.sector];
          return (
            <button
              key={school.school_id}
              onClick={() => onSelect(school)}
              className={`w-full text-left px-3 py-2.5 border-b border-[var(--border)] hover:bg-[var(--accent)] transition-colors flex items-start gap-2.5 group ${
                selectedId === school.school_id ? "bg-[var(--accent)]" : ""
              }`}
            >
              <School className={`h-4 w-4 mt-0.5 shrink-0 ${iconColor}`} />
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate leading-tight">
                  {school.school_name || "Unnamed"}
                </div>
                <div className="text-xs text-[var(--muted-foreground)] mt-0.5 truncate">
                  {[school.municipality, school.province].filter(Boolean).join(", ") || "No location"}
                </div>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  {badge && (
                    <span className={`inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full ${badge.bg} ${badge.text}`}>
                      {badge.label}
                    </span>
                  )}
                  {school.latitude ? (
                    <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-green-50 text-green-700">
                      <MapPin className="h-2.5 w-2.5 mr-0.5" />coords
                    </span>
                  ) : (
                    <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">
                      no coords
                    </span>
                  )}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 mt-1 shrink-0 text-[var(--muted-foreground)] opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
