# Piring — Institution Locator

Interactive web application for searching and visualizing Philippine educational institutions across DepEd (public and private schools), CHED (higher education institutions), and TESDA (technical-vocational training and assessment centers). Built on the unified coordinates datasets produced by this project's pipelines. "Piring" means blindfold in Filipino — the app reveals what's hidden in the data.

## Features

- **Search** — debounced type-ahead search by school name or ID with ranked results (exact ID > starts-with > contains); matching schools appear as passive markers on the map without auto-zooming; map flies to a school only when the user explicitly clicks one in the dropdown
- **Non-intrusive school selection** — selecting a school (via search or results list) highlights it with an enlarged marker + pulsing ring + "i" badge. Clicking the enlarged marker opens the detail panel. The detail panel does not auto-open.
- **Cascading location filters** — Region → Province → Municipality → Barangay dropdowns with exact matching; map auto-zooms to the selected area
- **Sidebar tabs** — when a location filter is active, the left sidebar has two tabs:
  - **Schools** — scrollable results list with school name, location, sector, and coordinate status badges
  - **Overview** — summary stats: total schools, public/private split, coordinate coverage %, coordinate status distribution bar (valid/suspect/no coords), and coordinate sources bar
- **Interactive map** — Leaflet map with three base layers (Light, OpenStreetMap, Satellite), coord-status-aware colored markers, context-aware zoom, proportional sector sampling, IQR-based outlier-robust bounds
- **Sector toggles** — DepEd institutions are always visible; CHED and TESDA default off and must be activated via pill buttons in the toolbar. Toggling a sector hides/shows it in both the map and results list without re-querying the API.
- **Sector-aware markers** — 5 distinct colors:
  - Solid green dot — DepEd public school
  - Solid blue dot — DepEd private school
  - Solid violet dot — CHED public (SUC / LUC / Special HEI)
  - Solid light-violet dot — CHED private (Sectarian / Non-Sectarian)
  - Solid orange dot — TESDA institution
  - Coord-status overlays (ring / pulse / ×) apply to DepEd schools only; CHED and TESDA coordinates are considered authoritative
- **Sector badges** — results list and detail panel show a colored sector badge (DepEd / CHED / TESDA) per institution
- **Sector-aware detail panels** — DepEd: full coordinate lineage, GASTPE flags, enrollment status; CHED: academic discipline groups; TESDA: institution classification and program sectors
- **Map legend** — collapsible legend in the bottom-left corner showing all sector colors and coord-status overlays
- **Table view** — togglable tabular view showing all matching institutions including those without coordinates (invisible on the map). Sortable columns (click header to cycle asc/desc/clear): ID, name, sector, municipality, province, region, coord status, PSGC validation, enrollment status. Click a row to locate on the map (or zoom to locality if no coordinates).
- **School popups** — clicking a school dot shows a popup with labeled fields (Barangay, City/Muni, Province, Region), coordinates, and source. Includes a "View Details →" link to open the full detail panel.
- **School detail panel** — overlay panel with full school profile: location hierarchy, coordinate lineage (source, trust level, validator notes), suspect coordinate alert with plain-English explanation, GASTPE flags, enrollment status
- **Coordinate lineage inspector** — for each school, shows which source provided coordinates, trust level, available sources, and for monitoring-validated schools, which sub-source the validator chose
- **Base map toggle** — three tile layers: Light (CARTO, default), OpenStreetMap, and Satellite (Esri World Imagery). Layers control at bottom-right.
- **Stats bar** — live summary of total institutions, DepEd public, DepEd private, CHED, TESDA counts, and coordinate coverage

## Architecture

```
Browser
  └── React SPA (Vite + Tailwind)
        ├── SearchBar (debounced type-ahead)
        ├── FilterPanel (cascading dropdowns)
        ├── SummaryCard (overview stats + status/source bars)
        ├── SchoolMap (react-leaflet, coord-status markers, legend)
        ├── MapLegend (collapsible dot visual reference)
        ├── SchoolTable (tabular view with data quality indicators)
        ├── ResultsList
        ├── SchoolDetail (lineage inspector + suspect alerts)
        └── StatsBar
              │
              ▼
        FastAPI backend (Python)
              └── loads parquet files at startup (~70K institutions in memory)
```

Single container for deployment. The backend serves both the API and the built React static files.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, lucide-react |
| Map | Leaflet + react-leaflet, CARTO Light / OSM / Esri Satellite |
| Backend | FastAPI, pandas, pyarrow |
| Data | Parquet files from `data/gold/` |

## Running the App

### Production Mode (backend only)

Build the frontend once, then run the backend — it serves both the API and the static frontend files:

```bash
# From the devcontainer (where npm is available):
cd locator/frontend
npm install
npm run build

# From a Jupyter terminal (DS container):
cd /workspace/project_coordinates/locator/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000`. After any frontend code changes, re-run `npm run build` and refresh the browser.

### Development Mode (both servers)

For active frontend development with hot reload:

```bash
# Terminal 1 — DS container (Jupyter):
cd /workspace/project_coordinates/locator/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — devcontainer (where npm exists):
cd locator/frontend
npm run dev
```

Visit `http://localhost:5173`. The Vite proxy forwards `/api/*` to the backend.

### Deploying to Cloud Run

```bash
source /home/jupyter/google-cloud-sdk/path.bash.inc
cd /workspace/project_coordinates/locator
bash prepare_deploy.sh
gcloud run deploy school-locator --source . --region asia-southeast1 --allow-unauthenticated --memory 1Gi --min-instances 0 --max-instances 2
```

### Port Requirements

The DS container's `docker-compose.yml` must expose ports 8000 and 5173:

```yaml
ports:
  - "8888:8888"
  - "8000:8000"
  - "5173:5173"
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/schools?q=&region=&...` | Search and filter schools; omit `limit` for all results |
| `GET /api/schools/{school_id}` | Single school detail |
| `GET /api/filters?region=&...` | Cascading filter options (exact match) |
| `GET /api/stats` | Global summary statistics |
| `GET /api/summary?region=&province=&...` | Admin-level summary (coord sources, coord status, enrollment) |

## Design Decisions

### Interaction Modes

The app operates in one of three modes at a time, preventing state conflicts:
- **Idle** — no search or filter active; map shows the Philippines, no markers
- **Search** — user typed a query; matching schools appear as passive markers on the map (no auto-zoom); map only flies to a school when the user explicitly clicks one in the dropdown
- **Filter** — user selected location dropdowns; results from exact location matching; map auto-zooms to fit all markers in the selected area

Starting a search clears filters. Selecting a filter clears the search. This eliminates the class of bugs where stale state from one mode bleeds into another.

### School Selection (Non-Intrusive)

Selecting a school (via search dropdown, results list, or table row) does NOT auto-open the detail panel. Instead, the school's marker becomes enlarged with a pulsing ring and an "i" info badge. Clicking the enlarged marker opens the detail panel. Closing the detail panel keeps the map at the current position — it does not reset the view.

This separation of `selectedSchool` (highlighted on map) from `detailSchool` (panel open) prevents the panel from obstructing the map and gives the user control over when to see details.

### Map View Controller

The map's zoom behavior is managed by two independent effects:

1. **Fly-to effect** — triggered by a `flyToTrigger` counter that increments only when a user explicitly clicks a school (from search dropdown, results list, or table row). This is the highest priority zoom action. Calls `map.stop()` first to cancel any in-progress animation.
2. **Bounds effect** — triggered when the marker signature changes (filter results updated or cleared). Fits bounds to all markers in filter mode; does nothing in search mode.

These two effects don't interfere because they watch different signals. The fly-to trigger is a monotonic counter, not a reactive dependency chain — it can't be accidentally fired by unrelated state changes.

The map is always mounted (never unmounts when switching to table view). It's hidden with `opacity-0` and `pointer-events-none` behind the table, preserving the Leaflet instance and all its state. When clicking a school in the table, the map is revealed and the fly-to effect fires on the already-mounted map.

**Key invariant**: `handleFilterChange`'s React callback dependencies must NOT include `selectedSchool`. Including it causes the callback to regenerate when a school is selected, which triggers FilterPanel's effect, which re-invokes the filter handler, which clears and re-fetches results, which triggers a bounds fit that overrides the fly-to.

### Location Filtering

All location filters use **case-insensitive exact matching** (not substring). This prevents:
- "Region V" matching Region VI, VII, VIII
- "CAR" matching CARAGA
- "Alfonso" matching "Alfonso Castañeda"

Location column values are normalized at data load time: title case for provinces/municipalities, preserved abbreviations for NCR/CAR/BARMM, collapsed whitespace, and normalized comma spacing (fixes duplicate NCR province entries from inconsistent source formatting).

### Map Marker Capping

The map caps rendered markers at 3,000 for performance. When results exceed this cap, markers are **sampled proportionally by sector** across all five sector types — the sample preserves each sector's relative share of the visible result set. This prevents any one sector from visually disappearing due to load order.

Only sectors currently toggled on contribute to the visible result set. CHED and TESDA markers default off, so capping only applies when those toggles are active.

Bounds calculation always uses the full (uncapped) result set to ensure correct zoom behavior.

### Sector Colors and Coord-Status Overlays

All five sector types have a distinct base color:

| Sector | Color |
|---|---|
| DepEd public | Green |
| DepEd private | Blue |
| CHED public (SUC/LUC/Special HEI) | Violet |
| CHED private (Sectarian/Non-Sectarian) | Light violet |
| TESDA | Orange |

Coord-status overlays apply **only to DepEd schools** (CHED and TESDA coordinates are considered authoritative source data):

| Overlay | coord_status | coord_rejection_reason | Meaning |
|---|---|---|---|
| No overlay | `valid` / `fixed_swap` | — | Confident coordinates |
| Static orange ring | `suspect` | `wrong_municipality` or `round_coordinates` | Needs investigation |
| Pulsing red ring | `suspect` | `outside_all_polygons` | Almost certainly wrong (over water, outside land) |
| Red × | `suspect` | `placeholder_default` or `coordinate_cluster` | Known fake coordinate |
| Gray dot | null/unknown | — | No coord_status data |

The sector color is always visible as the center dot. The ring/×/pulse overlay indicates the severity and type of coordinate issue.

### NCR Sub-District Normalization

NCR cities have PSGC sub-district codes (e.g., `1380601` = Manila District 1) in the PSGC crosswalk, while the shapefile uses city-level codes (e.g., `1380600` = City of Manila). The municipal validation normalizes these: codes that share the same first 5 digits where one side ends in `00` are treated as matching. This prevents false `wrong_municipality` flags for all NCR schools. Verified: zero non-NCR schools are affected by this normalization.

### Table View

A togglable tabular view that complements the map by showing **all** matching schools — including those without coordinates (invisible on the map). This surfaces data quality issues: schools with no coordinates, suspect coordinates, and inactive enrollment.

Clicking a row switches to map view and:
- **If the school has coordinates** — flies to the school at zoom 16, highlights with enlarged marker
- **If the school has no coordinates** — zooms to the school's municipality/province/region (best-effort locality zoom using other schools in the same area)

### Outlier-Robust Bounds

When zooming to a location, the map computes bounds using an **IQR-based filter** that excludes spatial outliers (schools with stray coordinates far from the cluster). This prevents a single mislocated school from stretching the zoom level to show the entire country.

## Project Structure

```
locator/
├── backend/
│   ├── main.py               # FastAPI app + routes + SPA serving
│   ├── data_loader.py         # Parquet loading + location normalization
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main layout + mode management + sidebar tabs
│   │   ├── components/
│   │   │   ├── SearchBar.jsx   # Debounced search with selection handling
│   │   │   ├── FilterPanel.jsx # Cascading location dropdowns
│   │   │   ├── SummaryCard.jsx # Overview stats + status/source bars
│   │   │   ├── MapLegend.jsx   # Collapsible dot visual legend
│   │   │   ├── SchoolMap.jsx   # Leaflet map + coord-status markers + legend
│   │   │   ├── SchoolTable.jsx  # Tabular view with sortable columns
│   │   │   ├── SchoolDetail.jsx # Detail panel + lineage + suspect alerts
│   │   │   ├── ResultsList.jsx  # Sidebar results list
│   │   │   └── StatsBar.jsx    # Global summary stats
│   │   └── hooks/
│   │       └── useSchools.js   # API client
│   ├── package.json
│   └── vite.config.js
├── Dockerfile                 # Multi-stage build for Cloud Run
├── .dockerignore
├── prepare_deploy.sh          # Copies parquet data for Docker build
└── README.md
```

## Roadmap

- **Future** — Nearby schools (radius search), choropleth dashboard, export to CSV/GeoJSON, bookmarkable URLs, mobile responsive
