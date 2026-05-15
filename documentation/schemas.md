# Output Schemas

Reference for every column in the gold-layer parquet files. For an overview of the pipelines that produce these outputs, see the [project README](../README.md).

---

## Public School Coordinates

File: `data/gold/public_school_coordinates.parquet` (also `.csv` and `.xlsx`)

| Column | Description |
|---|---|
| `school_id` | Canonical (most recent) DepEd LIS School ID. Always 6-digit. |
| `school_name` | Best available school name |
| `latitude` | Final latitude (WGS84). Null if no coordinate source has data. |
| `longitude` | Final longitude (WGS84). Null if no coordinate source has data. |
| `coord_source` | Which source provided the coordinates: `monitoring_validated`, `osmapaaralan`, `nsbi_2324`, `geolocation_deped`, `drrms_imrs`, or null (enrollment-only) |
| `coord_fallback_from` | If non-null, the original higher-priority source whose coordinates were rejected as suspect; the published coords come from the next lower-priority source whose coords passed the municipal check |
| `monitoring_chosen_source` | If `coord_source=monitoring_validated`: which sub-source the validator chose (OSMapaaralan, NSBI, or New coordinates). Null otherwise. |
| `sources_available` | Comma-separated list of all sources that had coordinates for this school; `enrollment_only` if only known from enrollment |
| `coord_status` | `valid`, `fixed_swap` (lat/lon auto-corrected), `suspect`, or `no_coords` |
| `coord_rejection_reason` | If suspect: `wrong_municipality`, `outside_all_polygons`, `round_coordinates`, `placeholder_default`, or `coordinate_cluster`. If no_coords: `no_coordinate_source`. Null otherwise. |
| `region` | Administrative region (NIR-aware) |
| `old_region` | Pre-NIR region naming (Negros Occidental → Region VI, Negros Oriental/Siquijor → Region VII) |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `location_source` | Which source provided the admin fields |
| `enrollment_status` | `active` (in SY 2024-2025 enrollment) or `no_enrollment_reported` |
| `school_management` | DepEd, Non-Sectarian, Sectarian, SUC, LUC, etc. |
| `annex_status` | Standalone/Mother/Annex/Mobile |
| `offers_es` | Offers Elementary (True/False) |
| `offers_jhs` | Offers JHS (True/False) |
| `offers_shs` | Offers SHS (True/False) |
| `shs_strand_offerings` | Comma-delimited SHS strands (ABM, HUMSS, STEM, TVL, etc.) |
| `psgc_region` | 10-digit PSGC region code |
| `psgc_province` | 10-digit PSGC province code |
| `psgc_municity` | 10-digit PSGC municipality/city code |
| `psgc_barangay` | 10-digit PSGC barangay code (claimed) |
| `psgc_observed_barangay` | 10-digit PSGC barangay (observed from point-in-polygon) |
| `psgc_observed_municity` | 7-digit PSGC municipality (observed from point-in-polygon). Null if outside all polygons. |
| `psgc_validation` | `psgc_match`, `psgc_mismatch`, or `psgc_no_validation`. Respects `coord_status` — suspect rows always yield `psgc_no_validation`. |
| `urban_rural` | Urban/Rural classification (2020 Census of Population and Housing) |
| `income_class` | Municipal income class (1st–5th, DOF D.O. 74, S. 2024) |

---

## School ID Crosswalk

File: `data/gold/public_school_id_crosswalk.parquet`

| Column | Description |
|---|---|
| `historical_id` | Any school ID ever used |
| `canonical_id` | Most recent / current school ID (always 6-digit, with ~0.2% exceptions for closed/merged schools) |
| `match_method` | `official_mapping` (from DepEd's School ID Mapping tab) or `spatial_name` (heuristic: ≤100m proximity + ≥0.6 name similarity) |
| `year_first_seen` | Earliest SY this historical ID appears |
| `year_last_seen` | Latest SY this historical ID appears |

---

## HEI Coordinates (Gold)

File: `data/gold/hei_coordinates.parquet` (also `.csv` and `.xlsx`)

One row per HEI campus. Multi-campus institutions (same UII, different locations) appear as separate rows.

| Column | Description |
|---|---|
| `uii_code` | CHED Unique Institutional Identifier. Null for ~460 campuses with no UII in the source data. |
| `name` | Official HEI name (CHED) |
| `region` | Administrative region |
| `province` | Province |
| `city_municipality` | City or municipality |
| `sector` | Ownership sector: `Private`, `Public SUC Main`, `Public SUC Satellite`, `Public LUC`, `OGS` |
| `latitude` | Latitude (WGS84) |
| `longitude` | Longitude (WGS84) |
| `coord_status` | `valid` = within PH bounding box [4.5–21.5, 116–127]; `out_of_bounds` = outside bounds (none in current data) |
| `is_multi_campus` | `True` if this UII code appears at more than one distinct location |

**Note on duplicate UII codes**: Some institutions appear under two different UII codes in the CHED source (e.g., Stella Maris College: 10085 and 13191). This is a CHED data issue and is preserved as-is.

---

## HEI Programs (Silver)

File: `data/silver/hei_programs.parquet`

One row per HEI × program combination. 22,473 rows covering all program offerings per institution. Join to `hei_coordinates.parquet` on `(name, city_municipality)` or `uii_code` (where non-null) for spatial context.

| Column | Description |
|---|---|
| `uii_code` | CHED Unique Institutional Identifier (nullable) |
| `name` | Official HEI name |
| `region` | Administrative region |
| `province` | Province |
| `city_municipality` | City or municipality |
| `sector` | Ownership sector |
| `curriculum` | Curriculum level offered by the program (e.g., `Undergraduate`) |
| `latitude` | Latitude (WGS84) |
| `longitude` | Longitude (WGS84) |
| `program_level` | `Pre-baccalaureate`, `Baccalaureate`, `Post-baccalaureate`, `Master's`, `Doctorate` |
| `discipline_group` | CHED discipline group (e.g., `Business Administration and Related`) |
| `program_name` | PSCEd / specific program name (e.g., `Business Administration`) |
| `uii_missing` | `True` if `uii_code` is null for this row |

---

## Private School Coordinates

File: `data/gold/private_school_coordinates.parquet` (also `.csv` and `.xlsx`)

| Column | Description |
|---|---|
| `school_id` | Validated BEIS School ID |
| `school_name` | Official LIS school name |
| `latitude` | Cleaned latitude (null if rejected) |
| `longitude` | Cleaned longitude (null if rejected) |
| `coord_status` | `valid`, `fixed_swap`, `suspect`, or `no_coords` |
| `coord_rejection_reason` | If no_coords: `invalid`, `out_of_bounds`, `no_submission`, `not_in_lis`. If suspect: `placeholder_default`, `coordinate_cluster`, `round_coordinates`, `wrong_municipality`, `outside_all_polygons`. |
| `region` | Administrative region (NIR-aware) |
| `old_region` | Pre-NIR region naming |
| `division` | Division |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `esc_participating` | ESC program flag (1/0) |
| `shsvp_participating` | SHS VP flag (1/0) |
| `jdvp_participating` | JDVP flag (1/0) |
| `enrollment_status` | `active` (in SY 2024-2025 enrollment) or `no_enrollment_reported` |
| `school_management` | School management type |
| `annex_status` | Standalone/Mother/Annex/Mobile |
| `offers_es` | Offers Elementary (True/False) |
| `offers_jhs` | Offers JHS (True/False) |
| `offers_shs` | Offers SHS (True/False) |
| `shs_strand_offerings` | Comma-delimited SHS strands |
| `psgc_region` | 10-digit PSGC region code |
| `psgc_province` | 10-digit PSGC province code |
| `psgc_municity` | 10-digit PSGC municipality/city code |
| `psgc_barangay` | 10-digit PSGC barangay code (claimed) |
| `psgc_observed_barangay` | PSGC barangay from point-in-polygon |
| `psgc_observed_municity` | 7-digit PSGC municipality (observed from point-in-polygon) |
| `psgc_validation` | `psgc_match`, `psgc_mismatch`, or `psgc_no_validation`. Respects `coord_status`. |
| `urban_rural` | Urban/Rural classification |
| `income_class` | Municipal income class |
