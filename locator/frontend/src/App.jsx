import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { MapPin, Map, Table2, BarChart3, List } from "lucide-react";
import SearchBar from "./components/SearchBar";
import SchoolMap from "./components/SchoolMap";
import SchoolTable from "./components/SchoolTable";
import StatsBar from "./components/StatsBar";
import ResultsList from "./components/ResultsList";
import FilterPanel from "./components/FilterPanel";
import SummaryCard from "./components/SummaryCard";
import SchoolDetail from "./components/SchoolDetail";
import { useSchools } from "./hooks/useSchools";
import "./index.css";

/**
 * Interaction modes:
 *   "idle"   — no search or filter active, map shows Philippines
 *   "search" — user typed a search query
 *   "filter" — user selected location filters
 */

const SECTOR_TOGGLE_CONFIG = [
  { key: "ched", label: "CHED", color: "#7c3aed" },
  { key: "tesda", label: "TESDA", color: "#f97316" },
];

function SectorToggle({ label, active, color, onToggle }) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
      style={
        active
          ? { backgroundColor: color, color: "white" }
          : { backgroundColor: "var(--secondary)", color: "var(--secondary-foreground)" }
      }
    >
      <span
        className="inline-block h-2 w-2 rounded-full shrink-0"
        style={{ backgroundColor: active ? "white" : color }}
      />
      {label}
    </button>
  );
}

function App() {
  const {
    results,
    total,
    loading,
    stats,
    filters,
    searchSchools,
    fetchFilters,
    fetchStats,
  } = useSchools();

  const [mode, setMode] = useState("idle");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [selectedSchool, setSelectedSchool] = useState(null);
  const [detailSchool, setDetailSchool] = useState(null);
  const [flyToTrigger, setFlyToTrigger] = useState(0);
  const [searchClearSignal, setSearchClearSignal] = useState(0);
  const [viewMode, setViewMode] = useState("map");
  const [sidebarTab, setSidebarTab] = useState("schools");
  const [sectorVisibility, setSectorVisibility] = useState({ ched: false, tesda: false });

  const filterChangeIsReset = useRef(false);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  useEffect(() => {
    if (mode === "search" && searchQuery) {
      searchSchools({ q: searchQuery, limit: 200 });
    } else if (mode === "filter") {
      const hasLocation =
        activeFilters.region || activeFilters.province ||
        activeFilters.municipality || activeFilters.barangay;
      if (hasLocation) {
        searchSchools({ ...activeFilters });
      } else {
        searchSchools({ _clear: true });
        setMode("idle");
      }
    } else if (mode === "idle") {
      searchSchools({ _clear: true });
    }
  }, [mode, searchQuery, activeFilters, searchSchools]);

  // Filter results by active sector toggles (DepEd always visible)
  const visibleResults = useMemo(() => {
    return results.filter((s) => {
      const sec = s.sector;
      if (sec === "public" || sec === "private") return true;
      if (sec === "ched_public" || sec === "ched_private") return sectorVisibility.ched;
      if (sec === "tesda") return sectorVisibility.tesda;
      return true;
    });
  }, [results, sectorVisibility]);

  // --- Search handlers ---
  const handleSearch = useCallback((query) => {
    if (query && query.length >= 2) {
      setSearchQuery(query);
      setMode("search");
      setSelectedSchool(null);
      filterChangeIsReset.current = true;
      setActiveFilters({});
    } else {
      setSearchQuery("");
      setMode((prev) => (prev === "search" ? "idle" : prev));
      setSelectedSchool(null);
    }
  }, []);

  const handleSearchSelect = useCallback((school) => {
    if (school) {
      setSelectedSchool(school);
      setDetailSchool(null);
      setFlyToTrigger((c) => c + 1);
    } else {
      setSearchQuery("");
      setSelectedSchool(null);
      setDetailSchool(null);
      setMode("idle");
    }
  }, []);

  // --- Filter handlers ---
  const handleFilterChange = useCallback(
    (newFilters) => {
      if (filterChangeIsReset.current) {
        filterChangeIsReset.current = false;
        return;
      }
      const hasLocation =
        newFilters.region || newFilters.province ||
        newFilters.municipality || newFilters.barangay;
      if (hasLocation) {
        if (mode === "search") searchSchools({ _clear: true });
        setSearchQuery("");
        setSearchClearSignal((c) => c + 1);
        setSelectedSchool(null);
        setActiveFilters(newFilters);
        setMode("filter");
      } else {
        setActiveFilters(newFilters);
        setMode("idle");
        setSelectedSchool(null);
      }
    },
    [mode, searchSchools]
  );

  const handleSelectFromList = useCallback(
    (school) => {
      setSelectedSchool(school);
      setDetailSchool(null);
      setFlyToTrigger((c) => c + 1);
      if (viewMode === "table") setViewMode("map");
    },
    [viewMode]
  );

  const handleOpenDetail = useCallback((school) => {
    setDetailSchool(school);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setDetailSchool(null);
  }, []);

  const toggleSector = useCallback((key) => {
    setSectorVisibility((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="shrink-0 border-b border-[var(--border)] bg-[var(--card)]">
        <div className="px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <div className="h-8 w-8 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <MapPin className="h-4.5 w-4.5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold leading-tight">Institution Locator</h1>
              <p className="text-[11px] text-[var(--muted-foreground)] leading-tight">
                Philippine Educational Institutions
              </p>
            </div>
          </div>
          <div className="flex-1 max-w-xl">
            <SearchBar
              onSearch={handleSearch}
              onSelect={handleSearchSelect}
              results={mode === "search" ? visibleResults : []}
              loading={mode === "search" && loading}
              externalClear={searchClearSignal}
            />
          </div>
        </div>
        <div className="px-4 pb-2">
          <StatsBar stats={stats} />
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex min-h-0 relative">
        {/* Left sidebar */}
        <aside className="w-80 shrink-0 border-r border-[var(--border)] bg-[var(--card)] flex flex-col min-h-0">
          <FilterPanel
            onFilterChange={handleFilterChange}
            fetchFilters={fetchFilters}
            filters={filters}
          />

          {mode === "filter" && (
            <div className="flex border-b border-[var(--border)] shrink-0">
              <button
                onClick={() => setSidebarTab("schools")}
                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
                  sidebarTab === "schools"
                    ? "text-[var(--foreground)] border-b-2 border-[var(--primary)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                }`}
              >
                <List className="h-3.5 w-3.5" />
                Institutions
              </button>
              <button
                onClick={() => setSidebarTab("overview")}
                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
                  sidebarTab === "overview"
                    ? "text-[var(--foreground)] border-b-2 border-[var(--primary)]"
                    : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                }`}
              >
                <BarChart3 className="h-3.5 w-3.5" />
                Overview
              </button>
            </div>
          )}

          <div className="flex-1 min-h-0 overflow-hidden">
            {mode === "filter" && sidebarTab === "overview" ? (
              <div className="overflow-y-auto h-full">
                <SummaryCard activeFilters={activeFilters} />
              </div>
            ) : (
              <ResultsList
                results={mode !== "idle" ? visibleResults : []}
                total={mode !== "idle" ? visibleResults.length : 0}
                loading={loading}
                onSelect={handleSelectFromList}
                selectedId={selectedSchool?.school_id}
              />
            )}
          </div>
        </aside>

        {/* Main view area */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Toolbar: view toggle + sector toggles */}
          <div className="shrink-0 flex items-center gap-1 px-2 pt-2">
            <button
              onClick={() => setViewMode("map")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                viewMode === "map"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--accent)]"
              }`}
            >
              <Map className="h-3.5 w-3.5" />
              Map
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                viewMode === "table"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--accent)]"
              }`}
            >
              <Table2 className="h-3.5 w-3.5" />
              Table
            </button>

            {/* Sector toggles */}
            <div className="w-px h-4 bg-[var(--border)] mx-1" />
            {SECTOR_TOGGLE_CONFIG.map(({ key, label, color }) => (
              <SectorToggle
                key={key}
                label={label}
                active={sectorVisibility[key]}
                color={color}
                onToggle={() => toggleSector(key)}
              />
            ))}
          </div>

          {/* Map + Table + Detail overlay share the same space */}
          <div className="flex-1 p-2 min-h-0 relative">
            <div
              className={`absolute inset-2 ${viewMode === "map" ? "z-10" : "z-0 opacity-0 pointer-events-none"}`}
            >
              <SchoolMap
                schools={mode !== "idle" ? visibleResults : []}
                selectedSchool={selectedSchool}
                onOpenDetail={handleOpenDetail}
                mode={mode}
                flyToTrigger={flyToTrigger}
              />
            </div>

            {viewMode === "table" && (
              <div className="absolute inset-2 z-10">
                <SchoolTable
                  schools={mode !== "idle" ? visibleResults : []}
                  onSelect={handleSelectFromList}
                  selectedId={selectedSchool?.school_id}
                />
              </div>
            )}

            {detailSchool && (
              <div className="absolute top-4 right-4 bottom-4 z-20">
                <SchoolDetail school={detailSchool} onClose={handleCloseDetail} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
