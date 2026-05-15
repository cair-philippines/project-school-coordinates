# Bronze — Frozen

One-off source files that are not expected to be replaced.

| Filename | Description | Used by |
|---|---|---|
| `02. DepEd Data Encoding Monitoring Sheet.xlsx` | University-validated coordinates for ~11,331 flagged schools (5 sheets). One-time validation exercise. | `modules/load_monitoring.py` → priority 1 coords |
| `osmapaaralan_overpass_turbo_export.geojson` | Point-in-time OpenStreetMap extract of school footprints (~44K features). Re-extracting would produce a different file but is a deliberate, not periodic, action. | `modules/load_osmapaaralan.py` → priority 2 coords |
| `Geolocation of Public Schools_DepEd.xlsx` | Internal DepEd geolocation file. Contains two sheets: `Geolocations` (coordinates, ~47K schools) and `School ID Mapping` (historical-to-canonical ID transitions, ~67K schools). | `modules/load_geolocation.py` (priority 4 coords) + `modules/build_crosswalk.py` (crosswalk Layer 1 source) |
| `SY 2024-2025 School Level Database WITH PSGC.xlsx` | School-to-PSGC crosswalk (60,094 schools, Q4 2024 PSGC). One-off — no current DepEd mechanism guarantees PSGC maintenance. | `modules/load_psgc.py` → PSGC attachment |
| `HEIs_with_Regions_latlong_Programs_Disciplines.xlsx` | CHED HEI snapshot: 22,473 rows of institution × program data including coordinates, sector, and discipline. Source for both the silver HEI × program table and the gold HEI coordinates file. | `scripts/build_hei_coordinates.py` |

**If a file here changes unexpectedly**, that's a signal worth pausing the build for — nothing should overwrite these quietly.
