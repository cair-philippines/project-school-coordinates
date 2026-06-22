# Bronze — Raw Source Files

This is the **bronze layer** of the medallion architecture. Files here are original source files from DepEd, CHED, and TESDA, preserved with their shipped filenames. Not committed to the repository (large, externally sourced). Drop new files here and the preprocessing stage will normalize them into `data/silver/`.

## Layout

```
bronze/
├── frozen/    # One-off snapshots — these files are not expected to change
└── live/      # Expected to refresh on a cadence (new school year, quarterly updates, etc.)
```

**Frozen** means the file is either a point-in-time historical artifact (e.g. OSM extract) or a completed one-off exercise (e.g. the university validation sheet) that will not get a replacement. If a frozen file changes, that's a signal worth investigating.

**Live** means a refreshed version is expected eventually, often as a new file with a different filename (`SY 2024-2025 List...` replacing `SY 2023-2024 List...`). The pipeline continues to work after the replacement as long as the RAW_PATH constant in each loader is updated.

## Expected files

See `frozen/README.md` and `live/README.md` for per-file details.

## Shapefile note

The barangay shapefile used for spatial validation is not bronze — it's external reference data from PSA via `cair-philippines/open-data-philippine-maps`. It lives in `data/reference/phl_admbnda_adm4_updated/`.
