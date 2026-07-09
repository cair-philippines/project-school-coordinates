# Bronze — Frozen

One-off source files that are not expected to be replaced.

| Filename | Description | Used by |
|---|---|---|
| `02. DepEd Data Encoding Monitoring Sheet.xlsx` | University-validated coordinates for ~11,331 flagged schools (5 sheets). One-time validation exercise. | `modules/load_monitoring.py` → priority 1 coords |
| `osmapaaralan_overpass_turbo_export.geojson` | Point-in-time OpenStreetMap extract of school footprints (~44K features). Re-extracting would produce a different file but is a deliberate, not periodic, action. | `modules/load_osmapaaralan.py` → priority 2 coords |
| `Geolocation of Public Schools_DepEd.xlsx` | Internal DepEd geolocation file. Contains two sheets: `Geolocations` (coordinates, ~47K schools) and `School ID Mapping` (historical-to-canonical ID transitions, ~67K schools). | `modules/load_geolocation.py` (priority 4 coords) + `modules/build_crosswalk.py` (crosswalk Layer 1 source) |
| `SY 2024-2025 School Level Database WITH PSGC.xlsx` | School-to-PSGC crosswalk (60,094 schools, Q4 2024 PSGC). One-off — no current DepEd mechanism guarantees PSGC maintenance. | `modules/load_psgc.py` → PSGC attachment |
| `HEIs_with_Regions_latlong_Programs_Disciplines.xlsx` | CHED HEI snapshot (AY unknown, received ~2026-05): 22,473 rows of institution × program data. **Superseded by Annex A file below.** Retained for lineage. | `scripts/build_hei_coordinates.py` (v1) |
| `Annex A - CHED Template of the Requested Data_Table.xlsx` | CHED HEI snapshot AY 2024-2025 (received 2026-07): 25,058 rows, single sheet "Table", header on row 3. Supersedes the file above. See `documentation/hei_source_registry.md` for full lineage. | `scripts/build_hei_coordinates.py` (current) |
| `TESDA Assessment Centers and Assessors.xlsx` | TESDA snapshot: 31,577 rows of institution × program accreditation data (sheet: "Assessment Centers Data as of N"). Includes coordinates, classification (TVI/TTI/HEI/etc.), institution role (Both/Provider Only/Assessment Center Only), sector, and accreditation dates. Source for the silver TESDA × program table and the gold TESDA coordinates file. | `scripts/build_tesda_coordinates.py` |

**If a file here changes unexpectedly**, that's a signal worth pausing the build for — nothing should overwrite these quietly.
