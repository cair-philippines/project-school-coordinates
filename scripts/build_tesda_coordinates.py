"""TESDA Coordinates Pipeline.

Processes the TESDA Assessment Centers dataset from bronze to silver
(institution × program table) and gold (one row per institution with
coordinates and PSGC).

Pipeline steps:
  1. Load bronze Excel (sheet: Assessment Centers Data as of N)
  2. Normalize localities: capture old_* values, harmonize to DepEd naming
  3. Assign institution IDs: stable TESDA00001-style IDs (source Unique ID is all null)
  4. Build silver: normalized institution × program table (~31,577 rows)
  5. Build gold: deduplicate to one row per institution (~8,239 rows)
  6. Attach PSGC: point-in-polygon spatial lookup (all 4 admin levels)
  7. Write outputs + report + metrics

Usage:
    cd project_coordinates/
    python scripts/build_tesda_coordinates.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "frozen"
    / "TESDA Assessment Centers and Assessors.xlsx"
)
SHEET_NAME = "Assessment Centers Data as of N"
SHAPEFILE_PATH = (
    PROJECT_ROOT
    / "data"
    / "reference"
    / "phl_admbnda_adm4_updated"
    / "phl_admbnda_adm4_updated.shp"
)
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "gold"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"

LAT_MIN, LAT_MAX = 4.5, 21.5
LON_MIN, LON_MAX = 116.0, 127.0

# TESDA region strings include descriptor suffixes not present in DepEd convention.
# e.g. "Region I - Ilocos" → "Region I", "Region IV-B - MIMAROPA" → "MIMAROPA"
# CAR, NCR, BARMM retain their abbreviations (their full forms are not used in DepEd either).
REGION_MAP = {
    "Region I - Ilocos": "Region I",
    "Region II - Cagayan Valley": "Region II",
    "Region III - Central Luzon": "Region III",
    "Region IV-A - CALABARZON": "Region IV-A",
    "Region IV-B - MIMAROPA": "MIMAROPA",
    "Region V - Bicol": "Region V",
    "Region VI - Western Visayas": "Region VI",
    "Region VII - Central Visayas": "Region VII",
    "Region VIII - Eastern Visayas": "Region VIII",
    "Region IX - Zamboanga Peninsula": "Region IX",
    "Region X - Northern Mindanao": "Region X",
    "Region XI - Davao": "Region XI",
    "Region XII - SOCCSKSARGEN": "Region XII",
    "Region XIII - CARAGA": "Region XIII",
    "Cordillera Administrative Region (CAR)": "CAR",
    "National Capital Region (NCR)": "NCR",
    "Bangsamoro Autonomous Region in Muslim Mindanao (BARMM)": "BARMM",
}

# Province name fixes: TESDA label → DepEd/PSA label (applied case-insensitively).
PROVINCE_MAP = {
    "MT. PROVINCE": "Mountain Province",
    # Tawi-Tawi has inconsistent casing in source (Tawi-tawi / Tawi-Tawi)
    "TAWI-TAWI": "Tawi-Tawi",
    # Compostela Valley was renamed Davao de Oro by RA 11000 (2019)
    "COMPOSTELA VALLEY": "Davao de Oro",
    # Western Samar parenthetical is a clarification, not the official name
    "SAMAR (WESTERN SAMAR)": "Samar",
    # Non-standard grouping covering Sarangani province and General Santos City
    "SARANGANI-GENSAN": "Sarangani",
}

# Independent component cities listed as province in Region IX — these are not
# PSA provinces. Null them; the spatial PSGC lookup will assign the correct code.
FAKE_PROVINCE_UPPER = {
    "CITY OF ISABELA (NOT A PROVINCE)",
    "ISABELA CITY, BASILAN",
    "ZAMBOANGA CITY",
}


# ---------------------------------------------------------------------------
# Step 1: Load bronze
# ---------------------------------------------------------------------------
def load_bronze():
    print(f"Loading bronze: {SOURCE_FILE.name}")
    raw = pd.read_excel(SOURCE_FILE, sheet_name=SHEET_NAME)
    print(f"  Raw rows: {len(raw):,}")

    raw = raw.rename(
        columns={
            "Region": "region",
            "PROVINCE": "province",
            "DISTRICT": "district",
            "MUNICIPALITY": "city_municipality",
            "MUNICIPALITY CLASS": "municipality_class",
            "NAME OF INSTITUTION": "name",
            "TYPE OF INSTITUTION": "type_of_institution",
            "CLASSIFICATION": "classification",
            "ADDRESS": "address",
            "LATITUDE": "latitude",
            "LONGITUDE": "longitude",
            "SECTOR": "sector",
            "PROGRAM": "program",
            "DATE ISSUED": "date_issued",
            "EXPIRATION DATE": "expiration_date",
            "INSTITUTION CLASSIFICATION": "institution_classification",
        }
    )
    # Drop the source Unique ID column — it is entirely null in the source file
    raw = raw.drop(columns=["Unique ID"], errors="ignore")

    str_cols = [
        "name", "region", "province", "district", "city_municipality",
        "municipality_class", "type_of_institution", "classification",
        "address", "sector", "program", "institution_classification",
    ]
    for col in str_cols:
        raw[col] = raw[col].astype(str).str.strip().replace("nan", None)

    # Coordinates: strip invisible Unicode characters (e.g. U+200E left-to-right mark
    # present in some source cells) before coercing to float
    for col in ("latitude", "longitude"):
        raw[col] = pd.to_numeric(
            raw[col].astype(str).str.extract(r"([-\d.]+)", expand=False),
            errors="coerce",
        )

    # Normalize type_of_institution casing (source has PRIVATE/Private, PUBLIC/Public)
    raw["type_of_institution"] = raw["type_of_institution"].str.title()

    # Normalize classification: only fix 'Farm school' → 'Farm School'
    raw["classification"] = raw["classification"].apply(
        lambda x: "Farm School" if pd.notna(x) and str(x).upper() == "FARM SCHOOL" else x
    )

    # Auto-swap reversed lat/lon pairs: many source rows have lat and lon
    # entered in the wrong columns. Detectable when the value in 'latitude'
    # falls in the valid PH longitude range [116, 127] and the value in
    # 'longitude' falls in the valid PH latitude range [4.5, 21.5].
    swap_mask = (
        raw["latitude"].between(LON_MIN, LON_MAX)
        & raw["longitude"].between(LAT_MIN, LAT_MAX)
    )
    n_swapped = int(swap_mask.sum())
    if n_swapped > 0:
        raw.loc[swap_mask, ["latitude", "longitude"]] = (
            raw.loc[swap_mask, ["longitude", "latitude"]].values
        )
        print(f"  Swapped reversed lat/lon pairs: {n_swapped:,} rows")

    return raw


# ---------------------------------------------------------------------------
# Step 2: Normalize localities
# ---------------------------------------------------------------------------
def normalize_localities(raw):
    """Capture original TESDA locality values, then harmonize to DepEd naming.

    Adds old_region, old_province, old_city_municipality columns. The canonical
    columns are updated so downstream joins across education sectors work without
    an extra harmonization layer.

    Changes applied:
    - region: descriptor suffix stripped (e.g. "Region I - Ilocos" → "Region I";
      "Cordillera Administrative Region (CAR)" → "CAR"). All 17 regions mapped.
    - province: five name fixes (case-insensitive). NCR province values are all
      district groupings (CaMaNaVa, PasMak, MuntiParLasTaPat, etc.) — PSA has no
      province layer for NCR, so all NCR province values are nulled. Three Region IX
      independent component cities listed as province are also nulled.
    - city_municipality: no suffix normalization needed (TESDA omits the
      " MUNICIPALITY" suffix that CHED used).
    """
    raw["old_region"] = raw["region"]
    raw["old_province"] = raw["province"]
    raw["old_city_municipality"] = raw["city_municipality"]

    raw["region"] = raw["region"].replace(REGION_MAP)

    # Case-insensitive province name fixes
    _prov_map_upper = {k.upper(): v for k, v in PROVINCE_MAP.items()}
    raw["province"] = raw["province"].apply(
        lambda x: _prov_map_upper.get(str(x).upper(), x) if pd.notna(x) else x
    )

    # NCR has no PSA province layer — all province values are internal TESDA
    # district groupings (CaMaNaVa, PasMak, etc.), not official PSA names
    ncr_mask = raw["region"].eq("NCR")
    n_ncr = int(ncr_mask.sum())
    raw.loc[ncr_mask, "province"] = None

    # Region IX: independent cities listed as province
    fake_mask = raw["province"].str.upper().isin(FAKE_PROVINCE_UPPER)
    n_fake = int(fake_mask.sum())
    raw.loc[fake_mask, "province"] = None

    changed_region = int((raw["old_region"] != raw["region"]).sum())
    changed_province = int(
        (raw["old_province"].fillna("") != raw["province"].fillna("")).sum()
    )
    changed_city = int(
        (raw["old_city_municipality"] != raw["city_municipality"]).sum()
    )

    print(f"\nLocality harmonization:")
    print(f"  Region values changed:              {changed_region:,}")
    print(f"  Province values changed (total):    {changed_province:,}")
    print(f"    of which NCR groupings nulled:    {n_ncr:,} rows")
    print(f"    of which fake province nulled:    {n_fake:,} rows")
    print(f"  City/municipality values changed:   {changed_city:,}")

    return raw


# ---------------------------------------------------------------------------
# Step 3: Assign institution IDs
# ---------------------------------------------------------------------------
def assign_institution_ids(raw):
    """Assign stable TESDA institution IDs (TESDA00001, ...) to each unique institution.

    Unique institution is defined as (name, latitude, longitude). IDs are assigned
    in order sorted by (region, province, city_municipality, name, latitude, longitude)
    so institutions in the same area are numerically adjacent.

    The source 'Unique ID' column is entirely null, hence the need for this step.
    """
    # Use sentinels for null lat/lon so they participate in deduplication
    lat_fill = raw["latitude"].fillna(-999.0)
    lon_fill = raw["longitude"].fillna(-999.0)
    raw = raw.assign(_lat_fill=lat_fill, _lon_fill=lon_fill)

    sort_cols = ["region", "province", "city_municipality", "name", "_lat_fill", "_lon_fill"]
    unique_insts = (
        raw.drop_duplicates(subset=["name", "_lat_fill", "_lon_fill"])
        .sort_values(sort_cols, na_position="last")
        .reset_index(drop=True)
    )
    unique_insts["tesda_inst_id"] = [
        f"TESDA{i + 1:05d}" for i in range(len(unique_insts))
    ]

    raw = raw.merge(
        unique_insts[["name", "_lat_fill", "_lon_fill", "tesda_inst_id"]],
        on=["name", "_lat_fill", "_lon_fill"],
        how="left",
    ).drop(columns=["_lat_fill", "_lon_fill"])

    print(f"\nInstitution IDs assigned: {raw['tesda_inst_id'].nunique():,} unique institutions")
    return raw


# ---------------------------------------------------------------------------
# Step 4: Build silver — normalized institution × program table
# ---------------------------------------------------------------------------
def build_silver(raw):
    silver = raw[
        [
            "tesda_inst_id", "name",
            "region", "old_region",
            "province", "old_province",
            "city_municipality", "old_city_municipality",
            "district", "municipality_class",
            "type_of_institution", "classification", "institution_classification",
            "address", "latitude", "longitude",
            "sector", "program", "date_issued", "expiration_date",
        ]
    ].copy()

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SILVER_DIR / "tesda_programs.parquet"
    silver.to_parquet(out_path, index=False)
    print(f"\nSilver written: {out_path} ({len(silver):,} rows)")
    print(f"  Null lat/lon rows: {silver['latitude'].isna().sum():,}")
    print(f"  Institution classification breakdown:")
    for val, count in silver["institution_classification"].value_counts(dropna=False).items():
        print(f"    {val}: {count:,}")

    return silver


# ---------------------------------------------------------------------------
# Step 5: Build gold — one row per institution
# ---------------------------------------------------------------------------
def build_gold(silver):
    inst_cols = [
        "tesda_inst_id", "name",
        "region", "old_region",
        "province", "old_province",
        "city_municipality", "old_city_municipality",
        "district", "municipality_class",
        "type_of_institution", "classification", "institution_classification",
        "address", "latitude", "longitude",
    ]
    # Sort so rows with non-null classification come first within each institution.
    # A handful of institutions have some rows with classification filled and others
    # null; this ensures drop_duplicates picks the informative row.
    gold = (
        silver[inst_cols]
        .sort_values(
            ["tesda_inst_id", "classification", "type_of_institution"],
            na_position="last",
        )
        .drop_duplicates(subset=["tesda_inst_id"])
        .reset_index(drop=True)
    )

    gold["coord_status"] = "valid"
    null_mask = gold["latitude"].isna() | gold["longitude"].isna()
    gold.loc[null_mask, "coord_status"] = "null_coords"
    oob_mask = (
        gold["latitude"].notna()
        & (
            (gold["latitude"] < LAT_MIN) | (gold["latitude"] > LAT_MAX)
            | (gold["longitude"] < LON_MIN) | (gold["longitude"] > LON_MAX)
        )
    )
    gold.loc[oob_mask, "coord_status"] = "out_of_bounds"
    # Rows corrected by the lat/lon swap heuristic show as valid now; they are
    # indistinguishable from original valid coords at gold level. The swap
    # count is reported at load_bronze time (row level, not institution level).

    print(f"\nGold: {len(gold):,} institutions")
    print(f"  Valid coordinates:   {(gold['coord_status'] == 'valid').sum():,}")
    print(f"  Null coordinates:    {(gold['coord_status'] == 'null_coords').sum():,}")
    print(f"  Out-of-bounds:       {(gold['coord_status'] == 'out_of_bounds').sum():,}")
    print(f"  Classification breakdown:")
    for val, count in gold["classification"].value_counts(dropna=False).items():
        print(f"    {val}: {count:,}")

    return gold


# ---------------------------------------------------------------------------
# Step 6: Attach PSGC via point-in-polygon
# ---------------------------------------------------------------------------
def attach_psgc(gold):
    """Spatial lookup against PSA barangay shapefile for all 4 admin levels.

    TESDA institutions have no administrative PSGC crosswalk (unlike DepEd schools),
    so all PSGC codes are observed — derived from which polygon each institution's
    coordinate falls in.

    Adds columns:
        psgc_observed_region, psgc_observed_province,
        psgc_observed_municity, psgc_observed_barangay
    All are None for institutions whose coordinates fall outside all polygons or
    have null coordinates.
    """
    print("\nAttaching PSGC codes via point-in-polygon...")
    print("  Loading shapefile...")

    gdf = gpd.read_file(SHAPEFILE_PATH)
    for col in ["ADM1_PCODE", "ADM2_PCODE", "ADM3_PCODE", "ADM4_PCODE"]:
        gdf[col] = gdf[col].str.replace("PH", "", regex=False)

    has_coords = gold["latitude"].notna() & gold["longitude"].notna()
    coords_df = gold[has_coords].copy()
    print(f"  Performing point-in-polygon for {len(coords_df):,} institutions...")

    inst_gdf = gpd.GeoDataFrame(
        index=coords_df.index,
        geometry=[
            Point(lon, lat)
            for lon, lat in zip(coords_df["longitude"], coords_df["latitude"])
        ],
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(
        inst_gdf,
        gdf[["ADM1_PCODE", "ADM2_PCODE", "ADM3_PCODE", "ADM4_PCODE", "geometry"]],
        how="left",
        predicate="within",
    )
    # Boundary institutions may match multiple polygons — keep first hit
    joined = joined[~joined.index.duplicated(keep="first")]

    gold["psgc_observed_region"] = joined["ADM1_PCODE"]
    gold["psgc_observed_province"] = joined["ADM2_PCODE"]
    gold["psgc_observed_municity"] = joined["ADM3_PCODE"]
    gold["psgc_observed_barangay"] = joined["ADM4_PCODE"]

    matched = int(gold["psgc_observed_barangay"].notna().sum())
    outside = int(has_coords.sum()) - matched
    print(f"  Matched to polygon:   {matched:,}")
    print(f"  Outside all polygons: {outside:,}")
    print(f"  Null coordinates (skipped): {int((~has_coords).sum()):,}")

    # Backfill province text for rows nulled during harmonization (NCR and fake
    # province rows). Use the shapefile's ADM2_EN field as authoritative text.
    null_province = gold["province"].isna() & gold["psgc_observed_province"].notna()
    if null_province.any():
        province_lookup = (
            gdf[["ADM2_PCODE", "ADM2_EN"]]
            .drop_duplicates("ADM2_PCODE")
            .set_index("ADM2_PCODE")["ADM2_EN"]
        )
        gold.loc[null_province, "province"] = (
            gold.loc[null_province, "psgc_observed_province"].map(province_lookup)
        )
        print(f"  Province backfilled from shapefile ADM2_EN: {int(null_province.sum()):,} institution(s)")

    return gold


# ---------------------------------------------------------------------------
# Step 7: Write gold outputs
# ---------------------------------------------------------------------------
def write_gold(gold):
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    parquet_path = OUTPUT_DATA_DIR / "tesda_coordinates.parquet"
    csv_path = OUTPUT_DATA_DIR / "tesda_coordinates.csv"
    xlsx_path = OUTPUT_DATA_DIR / "tesda_coordinates.xlsx"

    gold.to_parquet(parquet_path, index=False)
    gold.to_csv(csv_path, index=False)

    total = len(gold)
    valid = int((gold["coord_status"] == "valid").sum())
    null_coords = int((gold["coord_status"] == "null_coords").sum())
    oob = int((gold["coord_status"] == "out_of_bounds").sum())
    psgc_matched = int(gold["psgc_observed_barangay"].notna().sum())

    metadata = pd.DataFrame([
        {"field": "Pipeline", "value": "TESDA Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Source File", "value": SOURCE_FILE.name},
        {"field": "Source Sheet", "value": SHEET_NAME},
        {"field": "Total Institutions", "value": f"{total:,}"},
        {"field": "With Valid Coordinates", "value": f"{valid:,}"},
        {"field": "Null Coordinates", "value": f"{null_coords:,}"},
        {"field": "Out-of-Bounds Coordinates", "value": f"{oob:,}"},
        {"field": "PSGC Matched (spatial)", "value": f"{psgc_matched:,} / {total:,}"},
        {"field": "", "value": ""},
        {"field": "COLUMN DICTIONARY", "value": ""},
        {"field": "tesda_inst_id", "value": "Pipeline-assigned institution ID (TESDA00001 etc.). The source Unique ID column is entirely null in the raw file."},
        {"field": "name", "value": "Institution name (TESDA source: NAME OF INSTITUTION)"},
        {"field": "type_of_institution", "value": "Private or Public (title-cased; source had mixed PRIVATE/Private)"},
        {"field": "classification", "value": "Institution type: TVI (TVET Institution), TTI, HEI, Farm School, LGU, SUC, LUC, Enterprise, NGA, NGO, GOCC/GFI"},
        {"field": "institution_classification", "value": "Both = Training + Assessment provider; Provider Only = Training only; Assessment Center Only = Assessment only"},
        {"field": "address", "value": "Physical address string from source"},
        {"field": "latitude / longitude", "value": "Coordinates (WGS84). Null for ~3 institutions missing coords in source."},
        {"field": "coord_status", "value": "valid = within PH bounding box (includes auto-corrected lat/lon swaps); null_coords = missing lat/lon; out_of_bounds = outside bounds and not recoverable by swap"},
        {"field": "region", "value": "Administrative region — harmonized to DepEd convention (Region I, MIMAROPA, CAR, NCR, BARMM, etc.)"},
        {"field": "old_region", "value": "Original TESDA region string (e.g. 'Region I - Ilocos', 'Cordillera Administrative Region (CAR)')"},
        {"field": "province", "value": "Province — harmonized to DepEd/PSA naming. Null for NCR (no PSA province layer) and for independent cities listed as province. Backfilled from shapefile ADM2_EN after PSGC lookup."},
        {"field": "old_province", "value": "Original TESDA province string before harmonization"},
        {"field": "city_municipality", "value": "City or municipality name (no suffix normalization needed — TESDA matches DepEd convention)"},
        {"field": "old_city_municipality", "value": "Original TESDA municipality string (same as city_municipality; retained for pipeline consistency)"},
        {"field": "district", "value": "Congressional district (source: DISTRICT)"},
        {"field": "municipality_class", "value": "Income classification of the municipality (source: MUNICIPALITY CLASS)"},
        {"field": "psgc_observed_region", "value": "PSGC region code — from point-in-polygon against PSA shapefile"},
        {"field": "psgc_observed_province", "value": "PSGC province code — from point-in-polygon"},
        {"field": "psgc_observed_municity", "value": "PSGC municipality/city code (7-digit) — from point-in-polygon"},
        {"field": "psgc_observed_barangay", "value": "PSGC barangay code — from point-in-polygon. Null if institution falls outside all barangay polygons."},
        {"field": "", "value": ""},
        {"field": "PSGC NOTE", "value": "All PSGC codes are spatially observed — no administrative PSGC crosswalk exists for TESDA institutions."},
        {"field": "LOCALITY NOTE", "value": "NCR province values in the source are TESDA internal district groupings (CaMaNaVa, PasMak, etc.) not PSA provinces. They are nulled and backfilled from the shapefile."},
        {"field": "JOIN NOTE", "value": "Cross-sector joins on municipality: use psgc_observed_municity (7-digit) against psgc_municity.str[:7] (DepEd basic ed) or psgc_observed_municity (HEI)."},
        {"field": "RELATED FILE", "value": "data/silver/tesda_programs.parquet — full institution × program mapping (~31,577 rows)"},
    ])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
        gold.to_excel(writer, sheet_name="TESDA Coordinates", index=False)

    print(f"\nGold output written:")
    print(f"  {parquet_path} ({total:,} rows)")
    print(f"  {csv_path}")
    print(f"  {xlsx_path} (2 sheets)")


# ---------------------------------------------------------------------------
# Step 8: Build report + metrics
# ---------------------------------------------------------------------------
def write_report(silver, gold):
    total = len(gold)
    valid = int((gold["coord_status"] == "valid").sum())
    null_c = int((gold["coord_status"] == "null_coords").sum())
    oob = int((gold["coord_status"] == "out_of_bounds").sum())
    psgc_matched = int(gold["psgc_observed_barangay"].notna().sum())

    lines = [
        "=" * 60,
        "TESDA COORDINATES — BUILD REPORT",
        "=" * 60,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source:    {SOURCE_FILE.name}",
        f"Sheet:     {SHEET_NAME}",
        "",
        f"Silver (institution × program): {len(silver):,} rows",
        f"Gold (institutions):            {total:,}",
        "",
        "Coordinate status:",
        f"  valid:          {valid:,}",
        f"  null_coords:    {null_c:,}",
        f"  out_of_bounds:  {oob:,}",
        "",
        f"PSGC spatial match: {psgc_matched:,} / {total:,} institutions",
        "",
        "Locality harmonization (old → new):",
        f"  Region values changed:          {(gold['old_region'] != gold['region']).sum():,}",
        f"  Province values changed (total): {(gold['old_province'].fillna('') != gold['province'].fillna('')).sum():,}",
        f"  City/muni values changed:        {(gold['old_city_municipality'] != gold['city_municipality']).sum():,}",
        "",
        "Classification breakdown (gold):",
    ]
    for val, count in gold["classification"].value_counts(dropna=False).items():
        lines.append(f"  {val}: {count:,}")

    lines += ["", "Institution classification breakdown (gold):"]
    for val, count in gold["institution_classification"].value_counts(dropna=False).items():
        lines.append(f"  {val}: {count:,}")

    lines += ["", "Type of institution breakdown (gold):"]
    for val, count in gold["type_of_institution"].value_counts(dropna=False).items():
        lines.append(f"  {val}: {count:,}")

    lines += ["", "Regional distribution (harmonized, gold):"]
    for region, count in gold["region"].value_counts(dropna=False).items():
        lines.append(f"  {region}: {count:,}")

    report = "\n".join(lines)
    print(f"\n{report}")

    OUTPUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_REPORT_DIR / "build_tesda_report.txt"
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")


def write_metrics(silver, gold):
    def _vc(series):
        vc = series.fillna("__null__").value_counts().to_dict()
        return {str(k): int(v) for k, v in vc.items()}

    metrics = {
        "pipeline": "tesda",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "silver_row_count": int(len(silver)),
        "gold_institution_count": int(len(gold)),
        "coord_status": _vc(gold["coord_status"]),
        "psgc_matched": int(gold["psgc_observed_barangay"].notna().sum()),
        "psgc_outside_polygons": int(gold["psgc_observed_barangay"].isna().sum()),
        "locality_harmonization": {
            "region_changed": int((gold["old_region"] != gold["region"]).sum()),
            "province_changed": int(
                (gold["old_province"].fillna("") != gold["province"].fillna("")).sum()
            ),
            "city_municipality_changed": int(
                (gold["old_city_municipality"] != gold["city_municipality"]).sum()
            ),
        },
        "classification": _vc(gold["classification"]),
        "institution_classification": _vc(gold["institution_classification"]),
        "type_of_institution": _vc(gold["type_of_institution"]),
        "region": _vc(gold["region"]),
    }

    metrics_path = OUTPUT_DATA_DIR / "build_tesda_metrics.json"
    with metrics_path.open("w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"  Metrics written: {metrics_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    raw = load_bronze()
    raw = normalize_localities(raw)
    raw = assign_institution_ids(raw)
    silver = build_silver(raw)
    gold = build_gold(silver)
    gold = attach_psgc(gold)
    write_gold(gold)
    write_report(silver, gold)
    write_metrics(silver, gold)
    print("\nDone.")


if __name__ == "__main__":
    main()
