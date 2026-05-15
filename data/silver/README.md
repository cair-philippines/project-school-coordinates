# Silver — Preprocessed DepEd Sources

The silver layer sits between bronze (raw DepEd files, original filenames) and gold (canonical published outputs). Each silver file is the output of a loader's `preprocess()` function: a bronze file has been read, parsed, type-coerced, normalized, and written here as a parquet with a standardized filename and schema.

Silver is committed to the repository. Downstream consumers can read silver directly without having bronze files on hand.

## Files

| Silver | Bronze source | Produced by | Rows (typical) |
|---|---|---|---:|
| `monitoring.parquet` | `frozen/02. DepEd Data Encoding Monitoring Sheet.xlsx` | `modules/load_monitoring.preprocess()` | ~7,700 |
| `osmapaaralan.parquet` | `frozen/osmapaaralan_overpass_turbo_export.geojson` | `modules/load_osmapaaralan.preprocess()` | ~44,500 |
| `nsbi.parquet` | `live/SY 2023-2024 LIST OF SCHOOLS...xlsx` | `modules/load_nsbi.preprocess()` | ~47,000 |
| `geolocation.parquet` | `frozen/Geolocation of Public Schools_DepEd.xlsx` (Geolocations sheet) | `modules/load_geolocation.preprocess()` | ~47,400 |
| `sos_mapping.parquet` | `frozen/Geolocation of Public Schools_DepEd.xlsx` (School ID Mapping sheet) | `modules/load_sos_mapping.preprocess()` | ~67,600 |
| `drrms.parquet` | `live/DRRMS IMRS data 2025.csv` | `modules/load_drrms.preprocess()` | ~16,100 |
| `private_tosf_universe.parquet` | `live/Private School Seats and TOSF...xlsx` (SCHOOLS WITHOUT SUBMISSION sheet) | `modules/load_private_tosf.preprocess()` | ~12,000 |
| `private_tosf_coords.parquet` | `live/Private School Seats and TOSF...xlsx` (RAW DATA sheet, Pass 1–4 cleaning applied) | `modules/load_private_tosf.preprocess()` | ~9,600 |
| `private_tosf_coords_stats.json` | sidecar for `private_tosf_coords.parquet` — Pass 1–4 cleaning counts | `modules/load_private_tosf.preprocess()` | — |
| `psgc_crosswalk.parquet` | `frozen/SY 2024-2025 School Level Database WITH PSGC.xlsx` | `modules/load_psgc.preprocess()` | ~60,100 |
| `enrollment.parquet` | `live/project_bukas_enrollment_2024-25.csv` | `modules/load_enrollment.preprocess()` | ~60,000 |
| `hei_programs.parquet` | `frozen/HEIs_with_Regions_latlong_Programs_Disciplines.xlsx` | `scripts/build_hei_coordinates.py` | 22,473 |

## Regenerating

```bash
python scripts/build.py --stage=silver
```

This reads from `data/bronze/` and rewrites every silver file. The gold stage subsequently reads from silver only — it never reads bronze directly.

## Schema stability contract

Silver columns and dtypes are the contract between bronze loaders and the cascade algorithm. If a bronze file changes its schema, only the preprocessor changes; silver remains stable. Downstream projects that read silver can rely on this contract.

## Notes

- `enrollment.parquet` preserves ALL sectors including PSO. Callers that need to exclude PSO do so explicitly (`read_silver(sector="public")`, `load_full_metadata()`).
- `private_tosf_coords_stats.json` carries Pass 2/3 rejection counts that cannot be recovered from the parquet alone (rejected rows have their coordinates nulled).
- The `_was_swapped` signal column on coord sources is preserved through to silver.
