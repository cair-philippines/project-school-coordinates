# Unified Coordinates — Philippine Educational Institutions

Reproducible pipelines that consolidate geolocation data from DepEd and CHED sources into canonical coordinates tables for Philippine public schools, private schools, and higher education institutions (HEIs).

## Problem

DepEd maintains school coordinates across multiple systems that frequently disagree — sometimes by kilometers. School IDs also change over time (e.g., when a school's curricular offering is reclassified), making it difficult to track the same physical school across datasets. There is no single authoritative source for public schools, and the only private school coordinate source is self-reported with significant quality issues. CHED HEI coordinates are scattered across program-level administrative data with no standalone coordinates file.

## Solution

Three separate pipelines address the distinct challenges of each sector.

### Public Schools

1. **Normalizes** five coordinate sources into a common schema
2. **Resolves historical school ID changes** via a crosswalk built from official mappings and spatial+name deduplication
3. **Selects coordinates** through a trust-based priority cascade reflecting DepEd's valuation of each source
4. **Falls back** to the next-priority source when the primary coordinate is flagged suspect (wrong municipality or outside all land polygons)
5. **Expands the school universe** using enrollment data to include schools with active enrollment but no geolocation data
6. **Attaches administrative location columns** (region, province, municipality, barangay) from the best available source
7. **Tracks lineage** so every coordinate can be traced back to its origin

### Private Schools

1. **Cleans self-reported coordinates** (fixes swapped lat/lon, rejects invalid and out-of-bounds values, flags suspect patterns)
2. **Merges** cleaned coordinates with the official LIS universe to ensure complete coverage
3. **Preserves GASTPE participation flags** (ESC, SHS VP, JDVP) for policy analysis
4. **Tracks cleaning status** so every coordinate carries its provenance

### Higher Education Institutions (HEIs)

1. **Normalizes** the CHED HEI dataset from a program-level Excel file into a clean silver table (one row per HEI × program)
2. **Deduplicates** to one row per campus in the gold output, preserving multi-campus institutions as separate rows
3. **Flags** institutions with missing UII codes and multi-campus HEIs for downstream awareness
4. **Validates** coordinates against the Philippine bounding box

### Architecture

The project uses a medallion layout:

- **Bronze** (`data/bronze/`) — raw DepEd source files, original filenames preserved. Partitioned into `frozen/` (one-off snapshots) and `live/` (expected to refresh).
- **Silver** (`data/silver/`) — preprocessed, normalized parquets with standardized filenames; a stable contract between DepEd's noise and the cascade algorithm.
- **Gold** (`data/gold/`) — canonical published outputs consumed by downstream projects.
- **Reference** (`data/reference/`) — external reference data (the PSA barangay shapefile used for spatial validation).

Each loader module has a `preprocess()` function (bronze → silver) and a `read_silver()` function (silver → memory). The cascade, crosswalk, and validation algorithms read silver only.

## Data Sources

### Public Schools (5 coordinate sources + enrollment expansion)

| Priority | Source | Description | Schools |
|---|---|---|---|
| 1 | DepEd Data Encoding Monitoring Sheet | University-validated coordinates for flagged mismatches | ~7,700 |
| 2 | OSMapaaralan (OpenStreetMap) | Human-validated school footprints via OSM mapping | ~44,400 |
| 3 | SY 2023-2024 List of Schools (NSBI) | Official school infrastructure inventory | ~47,200 |
| 4 | Geolocation of Public Schools | Internal DepEd office revision | ~47,400 |
| 5 | DRRMS IMRS 2025 | Self-reported via disaster incident reports | ~16,100 |
| — | SY 2024-2025 Enrollment Data | Universe expansion and metadata enrichment (no coordinates) | ~60,000 |

### Private Schools

| Source | Description | Schools |
|---|---|---|
| Private School Seats and TOSF (Oct 2025) | Self-reported via Google Forms + LIS master list | 12,011 |
| SY 2024-2025 Enrollment Data | Universe expansion + enrollment status tagging | ~10,000 |

### Higher Education Institutions

| Source | Description | HEIs |
|---|---|---|
| CHED HEI Dataset (snapshot) | Program offerings, disciplines, and coordinates per institution | 2,422 campuses |

## Output

### Public Schools — 48,254 schools (46,537 valid · 1 fixed_swap · 1,136 suspect · 580 no coords)

| File | Description |
|---|---|
| `data/gold/public_school_coordinates.parquet` | Canonical coordinates table |
| `data/gold/public_school_id_crosswalk.parquet` | Historical → canonical school ID mapping (71,822 entries, canonical IDs consistently 6-digit) |
| `data/gold/public_school_coordinates.csv` | CSV export |
| `data/gold/public_school_coordinates.xlsx` | Excel workbook (Metadata + Coordinates + Crosswalk) |
| `data/gold/build_public_metrics.json` | Structured run metrics for programmatic comparison |
| `output/build_public_report.txt` | Pipeline run summary and statistics |

### Private Schools — 12,167 schools (7,582 valid · 92 fixed_swap · 1,243 suspect · 3,250 no coords)

| File | Description |
|---|---|
| `data/gold/private_school_coordinates.parquet` | Cleaned coordinates table |
| `data/gold/private_school_coordinates.csv` | CSV export |
| `data/gold/private_school_coordinates.xlsx` | Excel workbook (Metadata + Private School Coordinates) |
| `data/gold/build_private_metrics.json` | Structured run metrics for programmatic comparison |
| `output/build_private_report.txt` | Pipeline run summary and statistics |

### Higher Education Institutions — 2,422 campuses (all valid coordinates)

| File | Description |
|---|---|
| `data/gold/hei_coordinates.parquet` | One row per HEI campus with coordinates and sector |
| `data/gold/hei_coordinates.csv` | CSV export |
| `data/gold/hei_coordinates.xlsx` | Excel workbook (Metadata + HEI Coordinates) |
| `data/gold/build_hei_metrics.json` | Structured run metrics for programmatic comparison |
| `data/silver/hei_programs.parquet` | Full HEI × program mapping (22,473 rows) — silver layer |
| `output/build_hei_report.txt` | Pipeline run summary and statistics |

### Schemas

Full column-level documentation in [documentation/schemas.md](documentation/schemas.md).

## Usage

### Prerequisites

Python 3.11+ with `pandas`, `openpyxl`, `pyarrow`, `numpy`, `geopandas`, `shapely`.

### Full rebuild

```bash
cd project_coordinates/
python scripts/build.py --stage=all
```

Stages:
- `--stage=silver` — preprocess bronze → silver only
- `--stage=gold` — silver → gold (assumes silver already exists)
- `--stage=all` — full rebuild (default)

Both pipelines are deterministic and re-runnable. Outputs are regenerated from the raw DepEd source files in `data/bronze/`.

### Rebuild with verification

```bash
bash scripts/rebuild_and_verify.sh
```

Runs the full rebuild, diffs the new metrics against the previous run, runs the regression test suite, and prints a single `PASS` / `REGRESSION` line. Exit 0 iff build and tests both succeed. Recommended after any change to `data/bronze/`.

### Tests

```bash
python -m unittest discover tests
```

46 regression tests covering `normalize_school_id`, swap-fix and PH-bounds helpers, crosswalk identity-preferred dedup (including the `101701` conflation scenario), suspect-coord detection, PSGC validation coord_status awareness, and preprocessor silver-schema contracts.

## Project Structure

```
project_coordinates/
├── data/
│   ├── bronze/                           # Raw DepEd source files (not committed)
│   │   ├── frozen/                       # One-off snapshots (monitoring, geolocation, OSM, PSGC crosswalk)
│   │   └── live/                         # Expected to refresh (NSBI, DRRMS, TOSF, enrollment)
│   ├── silver/                           # Preprocessed sources (committed)
│   ├── gold/                             # Canonical pipeline outputs (committed)
│   └── reference/                        # External reference data — PSA shapefile (not committed)
├── scripts/
│   ├── build.py                          # Unified entry point (--stage=all|silver|gold)
│   ├── build_coordinates.py              # Public pipeline (internal module, invoked by build.py)
│   ├── build_private_coordinates.py      # Private pipeline (internal module, invoked by build.py)
│   ├── build_hei_coordinates.py          # HEI pipeline (bronze → silver → gold)
│   ├── diff_metrics.py                   # Diff two build metrics JSON files
│   └── rebuild_and_verify.sh             # Wrapper: rebuild + diff + tests + PASS/REGRESSION summary
├── modules/
│   ├── build_crosswalk.py                # School ID crosswalk (Layer 1 + 2)
│   ├── build_metrics.py                  # Structured build-metrics emitter
│   ├── cascade_fallback.py               # Rescues suspect schools via lower-priority sources
│   ├── enrich_enrollment.py              # Shared enrollment metadata enrichment
│   ├── load_*.py                         # Per-source preprocess() + read_silver()
│   ├── load_sos_mapping.py               # School ID Mapping sheet preprocessor
│   ├── psgc_pipeline.py                  # Shared PSGC join + spatial validation
│   ├── suspect_coords.py                 # Pass 4 detection (placeholder/cluster/round)
│   ├── utils.py                          # Shared helpers (swap-fix, bounds, haversine, etc.)
│   └── validate_psgc.py                  # Shapefile-based spatial validation
├── tests/                                # 46 regression tests
├── documentation/
│   ├── pipeline_plan.md                  # Public pipeline design and decisions
│   ├── technical_notes.md                # Public processing and transformation details
│   ├── private_pipeline_plan.md          # Private pipeline design and decisions
│   ├── private_technical_notes.md        # Private processing and transformation details
│   ├── schemas.md                        # Column reference for gold outputs
│   ├── duplication_audit.md              # Audit of duplicate/near-duplicate records
│   ├── crosswalk_7digit_reconciliation.md  # 7-digit canonical ID bug fix — narrative + results
│   └── psgc_standardization_plan.md      # PSGC crosswalk + spatial validation design
├── locator/                              # Piring web app (Cloud Run)
├── notebooks/                            # Ad-hoc analysis
├── output/                               # Build reports (not committed; regenerated each run)
└── README.md
```

## Documentation

### Public Schools
- **[Pipeline Plan](documentation/pipeline_plan.md)** — objective, source descriptions, priority cascade rationale, step-by-step design, output schemas, and design decisions.
- **[Technical Notes](documentation/technical_notes.md)** — comprehensive processing details: source ingestion, column mappings, crosswalk algorithms, threshold choices, validation results, and known limitations.
- **[Schemas](documentation/schemas.md)** — column-by-column reference for all gold outputs.
- **[Duplication Audit](documentation/duplication_audit.md)** — audit of duplicate/near-duplicate records in the public dataset, with recommended actions per record. Reference for championing smarter school data practices.
- **[Crosswalk 7-Digit Reconciliation](documentation/crosswalk_7digit_reconciliation.md)** — traces the arc from a downstream school-transfer prediction project's bug report through implementation and pre/post results. Documents why canonical school IDs are now consistently 6-digit, the merge logic for intra-source duplicates, and the downstream impact for any project that joins on `school_id`.

### Private Schools
- **[Pipeline Plan](documentation/private_pipeline_plan.md)** — objective, source description, coordinate cleaning strategy, output schema, and design decisions.
- **[Technical Notes](documentation/private_technical_notes.md)** — comprehensive processing details: ingestion, four-pass coordinate cleaning, merge logic, validation results, and known limitations.

### Higher Education Institutions
- **[Schemas](documentation/schemas.md)** — column-by-column reference for `hei_coordinates.parquet` (gold) and `hei_programs.parquet` (silver).

## See also

- **[Piring — School Locator](locator/README.md)** — interactive web application for searching and visualizing these coordinates. Built on the unified gold datasets and deployed on Cloud Run.

## AI Disclosure

This project was developed with substantial assistance from **Claude** (Anthropic), used as a collaborative coding and technical writing partner throughout the project lifecycle. AI was used for:

- **Pipeline design and architecture** — iterating on the priority cascade, crosswalk strategy, and modular structure through conversation
- **Medallion refactor** — partitioning `data/` into bronze/silver/gold/reference layers and splitting loaders into `preprocess()` + `read_silver()` functions
- **Code implementation** — writing Python modules, orchestrator scripts, and data processing logic
- **Data quality audits and fixes** — identifying silent cross-school conflation bugs (e.g. the `101701` case), designing tie-break rules that prefer identity mappings, adding cascade fallback for suspect-coord schools, and raising ambiguous-mapping warnings at build time
- **Regression testing** — authoring the test suite that pins critical decision points against future regressions
- **Build infrastructure** — structured metrics JSON emission, the metrics diff tool, and the rebuild-and-verify wrapper
- **Data exploration and analysis** — inspecting raw datasets, profiling coordinate quality, and diagnosing cross-source discrepancies
- **Documentation** — drafting pipeline plans, technical notes, schemas reference, and this README
- **Decision support** — evaluating trade-offs (e.g., crosswalk thresholds, coordinate cleaning pass order, cascade fallback policy, medallion layer gitignore policy)

All design decisions, domain context (DepEd source valuation, school ID behavior, GASTPE program relevance), and data interpretation were directed by the human author. The AI did not have independent access to external systems or make unsupervised decisions about data handling.
