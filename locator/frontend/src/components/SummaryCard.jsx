import { useEffect, useState } from "react";
import {
  Building2,
  MapPin,
  Users,
  BarChart3,
  Eye,
  GraduationCap,
} from "lucide-react";

function Stat({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${color || "text-[var(--muted-foreground)]"}`} />
      <div>
        <div className="text-lg font-semibold leading-tight">{value}</div>
        <div className="text-[11px] text-[var(--muted-foreground)]">{label}</div>
        {sub && <div className="text-[11px] text-[var(--muted-foreground)]">{sub}</div>}
      </div>
    </div>
  );
}

function SourceBar({ sources }) {
  if (!sources || Object.keys(sources).length === 0) return null;
  const total = Object.values(sources).reduce((a, b) => a + b, 0);
  const colors = {
    monitoring_validated: "#10b981",
    osmapaaralan: "#3b82f6",
    nsbi_2324: "#8b5cf6",
    geolocation_deped: "#f59e0b",
    tosf_self_reported: "#ec4899",
    none: "#d1d5db",
  };
  const labels = {
    monitoring_validated: "Monitoring",
    osmapaaralan: "OSMapaaralan",
    nsbi_2324: "NSBI",
    geolocation_deped: "Geolocation",
    tosf_self_reported: "TOSF",
    none: "No coords",
  };

  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1">
        <Eye className="h-3 w-3" />
        Coordinate Sources
      </div>
      <div className="flex h-2 rounded-full overflow-hidden bg-gray-100">
        {Object.entries(sources)
          .sort(([, a], [, b]) => b - a)
          .map(([src, count]) => (
            <div
              key={src}
              style={{
                width: `${(count / total) * 100}%`,
                backgroundColor: colors[src] || "#94a3b8",
              }}
              title={`${labels[src] || src}: ${count.toLocaleString()}`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {Object.entries(sources)
          .sort(([, a], [, b]) => b - a)
          .map(([src, count]) => (
            <div key={src} className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
              <div
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: colors[src] || "#94a3b8" }}
              />
              {labels[src] || src}: {count.toLocaleString()}
            </div>
          ))}
      </div>
    </div>
  );
}

function StatusBar({ statuses }) {
  if (!statuses || Object.keys(statuses).length === 0) return null;
  const total = Object.values(statuses).reduce((a, b) => a + b, 0);
  const colors = {
    valid: "#22c55e",
    fixed_swap: "#22c55e",
    suspect: "#f97316",
    no_coords: "#d1d5db",
    unknown: "#94a3b8",
  };
  const labels = {
    valid: "Valid",
    fixed_swap: "Fixed swap",
    suspect: "Suspect",
    no_coords: "No coords",
    unknown: "Unknown",
  };

  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1">
        <MapPin className="h-3 w-3" />
        Coordinate Status
      </div>
      <div className="flex h-2 rounded-full overflow-hidden bg-gray-100">
        {Object.entries(statuses)
          .sort(([, a], [, b]) => b - a)
          .map(([st, count]) => (
            <div
              key={st}
              style={{
                width: `${(count / total) * 100}%`,
                backgroundColor: colors[st] || "#94a3b8",
              }}
              title={`${labels[st] || st}: ${count.toLocaleString()}`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {Object.entries(statuses)
          .sort(([, a], [, b]) => b - a)
          .map(([st, count]) => (
            <div key={st} className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
              <div
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: colors[st] || "#94a3b8" }}
              />
              {labels[st] || st}: {count.toLocaleString()}
            </div>
          ))}
      </div>
    </div>
  );
}

export default function SummaryCard({ activeFilters }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const hasFilter = activeFilters && Object.values(activeFilters).some(Boolean);
    if (!hasFilter) {
      setSummary(null);
      return;
    }

    setLoading(true);
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(activeFilters)) {
      if (v) qs.set(k, v);
    }
    fetch(`/api/summary?${qs}`)
      .then((r) => r.json())
      .then((data) => setSummary(data))
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [activeFilters]);

  if (!summary) return null;
  if (loading) {
    return (
      <div className="p-3 border-b border-[var(--border)] text-xs text-[var(--muted-foreground)] animate-pulse">
        Loading summary...
      </div>
    );
  }

  const label = [
    activeFilters?.municipality,
    activeFilters?.province,
    activeFilters?.region,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="p-3 bg-gradient-to-b from-[var(--accent)] to-[var(--card)] space-y-3">
      <div className="text-xs font-medium text-[var(--muted-foreground)]">
        {label || "Summary"}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat icon={Building2} label="Total" value={summary.total.toLocaleString()} color="text-[var(--primary)]" />
        <Stat
          icon={MapPin}
          label="With Coords"
          value={`${summary.coverage_pct}%`}
          sub={`${summary.with_coordinates.toLocaleString()} of ${summary.total.toLocaleString()}`}
          color="text-green-600"
        />
        <Stat
          icon={Building2}
          label="DepEd Public"
          value={summary.public.toLocaleString()}
          color="text-green-600"
        />
        <Stat
          icon={Building2}
          label="DepEd Private"
          value={summary.private.toLocaleString()}
          color="text-blue-600"
        />
        {summary.ched > 0 && (
          <Stat
            icon={GraduationCap}
            label="CHED"
            value={summary.ched.toLocaleString()}
            color="text-violet-600"
          />
        )}
        {summary.tesda > 0 && (
          <Stat
            icon={BarChart3}
            label="TESDA"
            value={summary.tesda.toLocaleString()}
            color="text-orange-600"
          />
        )}
      </div>

      <StatusBar statuses={summary.coord_status} />
      <SourceBar sources={summary.coord_sources} />
    </div>
  );
}
