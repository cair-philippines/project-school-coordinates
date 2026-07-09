"""HEI Coordinates Pipeline.

Processes the CHED HEI dataset from bronze to silver (HEI × program table)
and gold (one row per HEI campus with coordinates).

Pipeline steps:
  1. Load bronze Excel
  2. Normalize localities: capture old_* values, harmonize to DepEd naming
  3. Build silver: normalized HEI × program table
  4. Build gold: deduplicate to one row per HEI campus
  5. Attach PSGC: point-in-polygon spatial lookup (all 4 admin levels)
  6. Write outputs + report + metrics

Usage:
    cd project_coordinates/
    python scripts/build_hei_coordinates.py

(Run via `ds python3 scripts/build_hei_coordinates.py` from the devcontainer.)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import re

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "frozen"
    / "Annex A - CHED Template of the Requested Data_Table.xlsx"
)
V1_SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "frozen"
    / "HEIs_with_Regions_latlong_Programs_Disciplines.xlsx"
)

# v1 → v2 sector vocabulary mapping (used for BARMM backfill only)
V1_SECTOR_MAP = {
    "Private": "Private Non-Sectarian",
    "Public SUC Main": "SUC Main",
    "Public SUC Satellite": "SUC Satellite",
    "Public LUC": "LUC",
    "OGS": "Special HEI",
}
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

# HEI region format → DepEd convention (new file uses "NN - Name" style)
REGION_MAP = {
    "01 - Ilocos Region": "Region I",
    "02 - Cagayan Valley": "Region II",
    "03 - Central Luzon": "Region III",
    "04 - CALABARZON": "Region IV-A",
    "05 - Bicol Region": "Region V",
    "06 - Western Visayas": "Region VI",
    "07 - Central Visayas": "Region VII",
    "08 - Eastern Visayas": "Region VIII",
    "09 - Zamboanga Peninsula": "Region IX",
    "10 - Northern Mindanao": "Region X",
    "11 - Davao Region": "Region XI",
    "12 - Soccsksargen": "Region XII",
    "13 - Nat. Capital Region": "NCR",
    "14 - Cordillera Adm. Region": "CAR",
    "16 - Caraga": "CARAGA",
    "17 - MIMAROPA": "MIMAROPA",
    "18 - Negros Island Region": "NIR",
}

# Province name fixes: CHED label → DepEd label
PROVINCE_MAP = {
    "MT. PROVINCE": "MOUNTAIN PROVINCE",
    "COTABATO": "NORTH COTABATO",
    "QUEZON PROVINCE": "QUEZON",
}


def _fix_mojibake(s):
    """Decode Latin-1 bytes misread as UTF-8 (v1 source file issue only)."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


# ---------------------------------------------------------------------------
# Step 1: Load bronze
# ---------------------------------------------------------------------------
def load_bronze():
    print(f"Loading bronze: {SOURCE_FILE.name}")
    # Row 1: blank, Row 2: title ("AY 2024-2025 HEI Coordinates"), Row 3: headers
    # Column A is unnamed/empty — skip via usecols
    raw = pd.read_excel(SOURCE_FILE, skiprows=2, usecols=list(range(1, 12)))
    print(f"  Raw rows: {len(raw):,}")

    raw = raw.rename(
        columns={
            "Unique Institutional Identifier (UII)": "uii_code",
            "Name of HEI": "name",
            "Region": "region",
            "Province": "province",
            "City/Municipality2": "city_municipality",
            "Sector": "sector",
            "Longitude": "longitude",
            "Latitude": "latitude",
            "Program Level": "program_level",
            "Discipline Group": "discipline_group",
            "PSCED/Program Name": "program_name",
        }
    )

    str_cols = [
        "name", "region", "province", "city_municipality", "sector",
        "discipline_group", "program_name",
    ]
    for col in str_cols:
        raw[col] = raw[col].astype(str).str.strip().replace("nan", None)

    raw["uii_code"] = raw["uii_code"].astype(str).str.strip().replace("nan", None)
    return raw


# ---------------------------------------------------------------------------
# Step 2: Normalize localities
# ---------------------------------------------------------------------------
def normalize_localities(raw):
    """Capture original CHED locality values, then harmonize to DepEd naming.

    Adds old_region, old_province, old_city_municipality columns containing
    the pre-harmonization CHED strings. The canonical columns (region,
    province, city_municipality) are updated to match DepEd conventions so
    downstream joins across basic and higher education work without an
    additional harmonization layer.

    Changes applied:
    - region: numeric format (Region 01) → Roman numeral (Region I); MIMAROPA
      for Region 04-B. BARMM, CAR, CARAGA, NCR unchanged.
    - province: four name fixes (MT. PROVINCE, COTABATO, QUEZON PROVINCE,
      CAGAYAN VALLEY). "CAGAYAN VALLEY" is a region name misplaced as a
      province in some CHED records — nulled out; PSGC spatial lookup provides
      the correct province for those campuses.
    - city_municipality: strip trailing " MUNICIPALITY" suffix (DepEd omits it).
    """
    raw["old_region"] = raw["region"]
    raw["old_province"] = raw["province"]
    raw["old_city_municipality"] = raw["city_municipality"]

    raw["region"] = raw["region"].replace(REGION_MAP)

    # Case-insensitive province map (source has mixed title/upper case)
    _prov_map_upper = {k.upper(): v for k, v in PROVINCE_MAP.items()}
    raw["province"] = raw["province"].apply(
        lambda x: _prov_map_upper.get(str(x).upper(), x) if pd.notna(x) else x
    )
    cagayan_valley_mask = raw["province"].str.upper().eq("CAGAYAN VALLEY")
    n_cagayan_valley = int(cagayan_valley_mask.sum())
    if n_cagayan_valley > 0:
        raw.loc[cagayan_valley_mask, "province"] = None
        print(f"  'CAGAYAN VALLEY' province nulled (region name misplaced): {n_cagayan_valley:,} rows")

    raw["city_municipality"] = raw["city_municipality"].str.replace(
        r"\s+Municipality$", "", regex=True, flags=re.IGNORECASE
    )

    changed_region = (raw["old_region"] != raw["region"]).sum()
    changed_province = (raw["old_province"].fillna("") != raw["province"].fillna("")).sum()
    changed_city = (raw["old_city_municipality"] != raw["city_municipality"]).sum()
    print(f"\nLocality harmonization:")
    print(f"  Region values changed:           {changed_region:,}")
    print(f"  Province values changed:          {changed_province:,}")
    print(f"  City/municipality values changed: {changed_city:,}")

    return raw


# ---------------------------------------------------------------------------
# Step 3: Build silver — normalized HEI × program table
# ---------------------------------------------------------------------------
def build_silver(raw):
    silver = raw[
        [
            "uii_code", "name",
            "region", "old_region",
            "province", "old_province",
            "city_municipality", "old_city_municipality",
            "sector", "latitude", "longitude",
            "program_level", "discipline_group", "program_name",
        ]
    ].copy()

    silver["uii_missing"] = silver["uii_code"].isna()

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SILVER_DIR / "hei_programs.parquet"
    silver.to_parquet(out_path, index=False)
    print(f"\nSilver written: {out_path} ({len(silver):,} rows)")
    print(f"  Rows with null UII: {silver['uii_missing'].sum():,}")
    print(f"  Program level breakdown:")
    for level, count in silver["program_level"].value_counts(dropna=False).items():
        print(f"    {level}: {count:,}")

    return silver


# ---------------------------------------------------------------------------
# Step 4: Build gold — one row per HEI campus
# ---------------------------------------------------------------------------
def build_gold(silver):
    gold = (
        silver[
            [
                "uii_code", "name",
                "region", "old_region",
                "province", "old_province",
                "city_municipality", "old_city_municipality",
                "sector", "latitude", "longitude",
            ]
        ]
        .drop_duplicates(subset=["name", "latitude", "longitude"])
        .reset_index(drop=True)
    )

    gold["coord_status"] = "valid"
    oob_mask = (
        (gold["latitude"] < LAT_MIN) | (gold["latitude"] > LAT_MAX)
        | (gold["longitude"] < LON_MIN) | (gold["longitude"] > LON_MAX)
    )
    gold.loc[oob_mask, "coord_status"] = "out_of_bounds"

    uii_campus_counts = (
        gold[gold["uii_code"].notna()]
        .groupby("uii_code")["name"]
        .transform("count")
    )
    gold["is_multi_campus"] = False
    gold.loc[uii_campus_counts[uii_campus_counts > 1].index, "is_multi_campus"] = True

    gold = gold.sort_values(["region", "name"]).reset_index(drop=True)
    gold["source_vintage"] = "v2"

    print(f"\nGold: {len(gold):,} HEI campuses")
    print(f"  Valid coordinates:   {(gold['coord_status'] == 'valid').sum():,}")
    print(f"  Out-of-bounds:       {(gold['coord_status'] == 'out_of_bounds').sum():,}")
    print(f"  Null UII:            {gold['uii_code'].isna().sum():,}")
    print(f"  Multi-campus:        {gold['is_multi_campus'].sum():,}")

    return gold


# ---------------------------------------------------------------------------
# Step 4b: BARMM backfill from v1 source (absent in v2)
# ---------------------------------------------------------------------------
def build_barmm_backfill():
    """Load BARMM HEI campuses from the v1 source file.

    BARMM is entirely absent from the AY 2024-2025 (v2) source. This function
    extracts BARMM records from the older file, applies the v1-specific mojibake
    fix, maps v1 sector labels to v2 equivalents, and returns a campus-level
    DataFrame in the same schema as build_gold() — tagged source_vintage='v1_barmm_backfill'.

    Silver is NOT updated (no program-level data for v1 BARMM rows is carried forward).
    """
    if not V1_SOURCE_FILE.exists():
        print("\nWARNING: v1 source file not found — BARMM backfill skipped.")
        return None

    print(f"\nLoading BARMM backfill from v1: {V1_SOURCE_FILE.name}")
    raw = pd.read_excel(V1_SOURCE_FILE, sheet_name="Merge1")

    raw = raw.rename(columns={
        "Sheet1 (2).Unique Institutional Identifier (UII) Code": "uii_code",
        "Name of HEI": "name",
        "Region": "region",
        "Province": "province",
        "City and Municipality": "city_municipality",
        "Sector": "sector",
        "Longitude": "longitude",
        "Latitude": "latitude",
    })

    str_cols = ["name", "region", "province", "city_municipality", "sector"]
    for col in str_cols:
        raw[col] = raw[col].astype(str).str.strip().replace("nan", None)
        raw[col] = raw[col].apply(_fix_mojibake)
    raw["uii_code"] = raw["uii_code"].astype(str).str.strip().replace("nan", None)

    barmm = raw[raw["region"] == "BARMM"].copy()
    print(f"  BARMM rows in v1 (program-level): {len(barmm):,}")

    if len(barmm) == 0:
        print("  No BARMM rows found — backfill skipped.")
        return None

    # BARMM region is already in DepEd format; old_* = same as canonical
    barmm["old_region"] = barmm["region"]
    barmm["old_province"] = barmm["province"]
    barmm["old_city_municipality"] = barmm["city_municipality"]

    # Translate v1 sector labels to v2 vocabulary
    barmm["sector"] = barmm["sector"].replace(V1_SECTOR_MAP)

    barmm_gold = (
        barmm[[
            "uii_code", "name",
            "region", "old_region",
            "province", "old_province",
            "city_municipality", "old_city_municipality",
            "sector", "latitude", "longitude",
        ]]
        .drop_duplicates(subset=["name", "latitude", "longitude"])
        .reset_index(drop=True)
    )

    barmm_gold["coord_status"] = "valid"
    oob_mask = (
        (barmm_gold["latitude"] < LAT_MIN) | (barmm_gold["latitude"] > LAT_MAX)
        | (barmm_gold["longitude"] < LON_MIN) | (barmm_gold["longitude"] > LON_MAX)
    )
    barmm_gold.loc[oob_mask, "coord_status"] = "out_of_bounds"

    barmm_gold["is_multi_campus"] = False
    uii_counts = (
        barmm_gold[barmm_gold["uii_code"].notna()]
        .groupby("uii_code")["name"]
        .transform("count")
    )
    multi_idx = uii_counts[uii_counts > 1].index
    if len(multi_idx) > 0:
        barmm_gold.loc[multi_idx, "is_multi_campus"] = True

    barmm_gold["source_vintage"] = "v1_barmm_backfill"

    print(f"  BARMM campuses (gold):  {len(barmm_gold):,}")
    print(f"  Valid coordinates:      {(barmm_gold['coord_status'] == 'valid').sum():,}")
    print(f"  Out-of-bounds:          {(barmm_gold['coord_status'] == 'out_of_bounds').sum():,}")
    print(f"  Null UII:               {barmm_gold['uii_code'].isna().sum():,}")
    print(f"  Multi-campus:           {barmm_gold['is_multi_campus'].sum():,}")

    return barmm_gold


# ---------------------------------------------------------------------------
# Step 5: Attach PSGC via point-in-polygon
# ---------------------------------------------------------------------------
def attach_psgc(gold):
    """Spatial lookup against PSA barangay shapefile for all 4 admin levels.

    HEIs have no administrative PSGC crosswalk (unlike DepEd schools), so all
    PSGC codes are observed — derived entirely from which polygon each campus
    coordinate falls in. No psgc_validation column is produced since there is
    no claimed code to compare against.

    Adds columns:
        psgc_observed_region, psgc_observed_province,
        psgc_observed_municity, psgc_observed_barangay
    All are None for campuses whose coordinates fall outside all polygons.
    """
    print("\nAttaching PSGC codes via point-in-polygon...")
    print("  Loading shapefile...")

    gdf = gpd.read_file(SHAPEFILE_PATH)
    for col in ["ADM1_PCODE", "ADM2_PCODE", "ADM3_PCODE", "ADM4_PCODE"]:
        gdf[col] = gdf[col].str.replace("PH", "", regex=False)

    has_coords = gold["latitude"].notna() & gold["longitude"].notna()
    coords_df = gold[has_coords].copy()
    print(f"  Performing point-in-polygon for {len(coords_df):,} campuses...")

    hei_gdf = gpd.GeoDataFrame(
        index=coords_df.index,
        geometry=[
            Point(lon, lat)
            for lon, lat in zip(coords_df["longitude"], coords_df["latitude"])
        ],
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(
        hei_gdf,
        gdf[["ADM1_PCODE", "ADM2_PCODE", "ADM3_PCODE", "ADM4_PCODE", "geometry"]],
        how="left",
        predicate="within",
    )
    # Boundary campuses may match multiple polygons — keep first hit
    joined = joined[~joined.index.duplicated(keep="first")]

    gold["psgc_observed_region"] = joined["ADM1_PCODE"]
    gold["psgc_observed_province"] = joined["ADM2_PCODE"]
    gold["psgc_observed_municity"] = joined["ADM3_PCODE"]
    gold["psgc_observed_barangay"] = joined["ADM4_PCODE"]

    matched = gold["psgc_observed_barangay"].notna().sum()
    outside = int(has_coords.sum()) - int(matched)
    print(f"  Matched to polygon:   {matched:,}")
    print(f"  Outside all polygons: {outside:,}")

    # Backfill province text for campuses nulled during harmonization (e.g.,
    # where CHED had a region name in the province field). Use the shapefile's
    # ADM2_EN name — authoritative and already loaded.
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
        print(f"  Province backfilled from PSGC shapefile: {int(null_province.sum()):,} campus(es)")

    return gold


# ---------------------------------------------------------------------------
# Step 6: Write gold outputs
# ---------------------------------------------------------------------------
def write_gold(gold):
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    parquet_path = OUTPUT_DATA_DIR / "hei_coordinates.parquet"
    csv_path = OUTPUT_DATA_DIR / "hei_coordinates.csv"
    xlsx_path = OUTPUT_DATA_DIR / "hei_coordinates.xlsx"

    gold.to_parquet(parquet_path, index=False)
    gold.to_csv(csv_path, index=False)

    total = len(gold)
    valid = int((gold["coord_status"] == "valid").sum())
    oob = int((gold["coord_status"] == "out_of_bounds").sum())
    null_uii = int(gold["uii_code"].isna().sum())
    multi = int(gold["is_multi_campus"].sum())
    psgc_matched = int(gold["psgc_observed_barangay"].notna().sum())

    metadata = pd.DataFrame([
        {"field": "Pipeline", "value": "HEI Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Source File", "value": SOURCE_FILE.name},
        {"field": "Total HEI Campuses", "value": f"{total:,}"},
        {"field": "With Valid Coordinates", "value": f"{valid:,}"},
        {"field": "Out-of-Bounds Coordinates", "value": f"{oob:,}"},
        {"field": "Null UII Code", "value": f"{null_uii:,}"},
        {"field": "Multi-Campus Institutions", "value": f"{multi:,} campuses across multi-campus HEIs"},
        {"field": "PSGC Matched (spatial)", "value": f"{psgc_matched:,} / {total:,}"},
        {"field": "", "value": ""},
        {"field": "COLUMN DICTIONARY", "value": ""},
        {"field": "uii_code", "value": "CHED Unique Institutional Identifier. Null for ~460 campuses with no UII in source data."},
        {"field": "name", "value": "Official HEI name (CHED)"},
        {"field": "region", "value": "Administrative region — harmonized to DepEd Roman numeral convention (e.g., Region I, MIMAROPA)"},
        {"field": "old_region", "value": "Original CHED region string before harmonization (e.g., Region 01, Region 04-B)"},
        {"field": "province", "value": "Province — harmonized to DepEd naming (e.g., MOUNTAIN PROVINCE, NORTH COTABATO)"},
        {"field": "old_province", "value": "Original CHED province string before harmonization. Null if CHED had a region name in the province field."},
        {"field": "city_municipality", "value": "City or municipality — trailing ' MUNICIPALITY' suffix stripped to match DepEd convention"},
        {"field": "old_city_municipality", "value": "Original CHED city/municipality string before harmonization"},
        {"field": "sector", "value": "Ownership sector: Private, Public SUC Main, Public SUC Satellite, Public LUC, OGS"},
        {"field": "latitude", "value": "Latitude (WGS84)"},
        {"field": "longitude", "value": "Longitude (WGS84)"},
        {"field": "coord_status", "value": "valid = within PH bounding box [4.5-21.5, 116-127]; out_of_bounds = outside bounds"},
        {"field": "is_multi_campus", "value": "True if this UII code appears at more than one distinct location"},
        {"field": "source_vintage", "value": "v2 = AY 2024-2025 CHED file (primary source); v1_barmm_backfill = BARMM campuses carried forward from the earlier CHED file (absent in v2)"},
        {"field": "psgc_observed_region", "value": "PSGC region code — from point-in-polygon against PSA shapefile"},
        {"field": "psgc_observed_province", "value": "PSGC province code — from point-in-polygon"},
        {"field": "psgc_observed_municity", "value": "PSGC municipality/city code (7-digit) — from point-in-polygon"},
        {"field": "psgc_observed_barangay", "value": "PSGC barangay code — from point-in-polygon. Null if campus falls outside all barangay polygons."},
        {"field": "", "value": ""},
        {"field": "PSGC NOTE", "value": "All PSGC codes are spatially observed — no administrative PSGC crosswalk exists for HEIs. No psgc_validation column is produced (nothing to compare against)."},
        {"field": "LOCALITY NOTE", "value": "old_* columns preserve the original CHED strings. region/province/city_municipality are harmonized to DepEd naming so joins across basic and higher education work without an extra layer."},
        {"field": "MULTI-CAMPUS NOTE", "value": "Some UII codes appear under two different codes in the CHED source (e.g., Stella Maris College: 10085 and 13191). This is a CHED data issue and is preserved as-is."},
        {"field": "RELATED FILE", "value": "data/silver/hei_programs.parquet — full HEI x program mapping (25,058 rows, AY 2024-2025). Note: silver does not include BARMM backfill rows (no program-level data in v1 for BARMM)."},
        {"field": "BARMM NOTE", "value": "BARMM campuses are absent from the v2 source file. They are backfilled from the earlier CHED file (v1) and tagged source_vintage='v1_barmm_backfill'. Sector labels translated from v1 to v2 vocabulary: Private→Private Non-Sectarian, Public SUC Main→SUC Main, Public SUC Satellite→SUC Satellite, Public LUC→LUC, OGS→Special HEI."},
    ])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
        gold.to_excel(writer, sheet_name="HEI Coordinates", index=False)

    print(f"\nGold output written:")
    print(f"  {parquet_path} ({total:,} rows)")
    print(f"  {csv_path}")
    print(f"  {xlsx_path} (2 sheets)")


# ---------------------------------------------------------------------------
# Step 7: Build report + metrics
# ---------------------------------------------------------------------------
def write_report(silver, gold):
    total = len(gold)
    valid = int((gold["coord_status"] == "valid").sum())
    oob = int((gold["coord_status"] == "out_of_bounds").sum())
    null_uii = int(gold["uii_code"].isna().sum())
    psgc_matched = int(gold["psgc_observed_barangay"].notna().sum())

    v2_count = int((gold["source_vintage"] == "v2").sum()) if "source_vintage" in gold.columns else total
    barmm_count = int((gold["source_vintage"] == "v1_barmm_backfill").sum()) if "source_vintage" in gold.columns else 0

    lines = [
        "=" * 60,
        "HEI COORDINATES — BUILD REPORT",
        "=" * 60,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source (v2): {SOURCE_FILE.name}",
        f"Source (v1): {V1_SOURCE_FILE.name} (BARMM backfill only)",
        "",
        f"Silver (HEI × program): {len(silver):,} rows (v2 only)",
        f"Gold (HEI campuses):    {total:,}",
        f"  v2 (AY 2024-2025):      {v2_count:,}",
        f"  v1 BARMM backfill:      {barmm_count:,}",
        "",
        "Coordinate status:",
        f"  valid:          {valid:,}",
        f"  out_of_bounds:  {oob:,}",
        "",
        f"PSGC spatial match: {psgc_matched:,} / {total:,} campuses",
        f"Null UII code:      {null_uii:,} campuses",
        f"Multi-campus flag:  {gold['is_multi_campus'].sum():,} campuses",
        "",
        "Locality harmonization (old → new):",
        f"  Region values changed:           {(gold['old_region'] != gold['region']).sum():,}",
        f"  Province values changed:          {(gold['old_province'].fillna('') != gold['province'].fillna('')).sum():,}",
        f"  City/muni values changed:         {(gold['old_city_municipality'] != gold['city_municipality']).sum():,}",
        "",
        "Sector breakdown:",
    ]
    for sector, count in gold["sector"].value_counts(dropna=False).items():
        lines.append(f"  {sector}: {count:,}")

    lines += ["", "Regional distribution (harmonized):"]
    for region, count in gold["region"].value_counts(dropna=False).items():
        lines.append(f"  {region}: {count:,}")

    lines += ["", "Silver — program level breakdown:"]
    for level, count in silver["program_level"].value_counts(dropna=False).items():
        lines.append(f"  {level}: {count:,}")

    report = "\n".join(lines)
    print(f"\n{report}")

    OUTPUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_REPORT_DIR / "build_hei_report.txt"
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")


def write_metrics(silver, gold):
    def _vc(series):
        if series is None:
            return {}
        vc = series.fillna("__null__").value_counts().to_dict()
        return {str(k): int(v) for k, v in vc.items()}

    barmm_backfill_count = int((gold["source_vintage"] == "v1_barmm_backfill").sum()) if "source_vintage" in gold.columns else 0

    metrics = {
        "pipeline": "hei",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "silver_row_count": int(len(silver)),
        "gold_campus_count": int(len(gold)),
        "barmm_backfill_count": barmm_backfill_count,
        "source_vintage": _vc(gold.get("source_vintage")),
        "coord_status": _vc(gold["coord_status"]),
        "psgc_matched": int(gold["psgc_observed_barangay"].notna().sum()),
        "psgc_outside_polygons": int(gold["psgc_observed_barangay"].isna().sum()),
        "null_uii_count": int(gold["uii_code"].isna().sum()),
        "multi_campus_count": int(gold["is_multi_campus"].sum()),
        "locality_harmonization": {
            "region_changed": int((gold["old_region"] != gold["region"]).sum()),
            "province_changed": int(
                (gold["old_province"].fillna("") != gold["province"].fillna("")).sum()
            ),
            "city_municipality_changed": int(
                (gold["old_city_municipality"] != gold["city_municipality"]).sum()
            ),
        },
        "sector": _vc(gold["sector"]),
        "region": _vc(gold["region"]),
        "program_level": _vc(silver["program_level"]),
    }

    metrics_path = OUTPUT_DATA_DIR / "build_hei_metrics.json"
    with metrics_path.open("w") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
    print(f"  Metrics written: {metrics_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    raw = load_bronze()
    raw = normalize_localities(raw)
    silver = build_silver(raw)
    gold = build_gold(silver)

    barmm_gold = build_barmm_backfill()
    if barmm_gold is not None:
        gold = pd.concat([gold, barmm_gold], ignore_index=True)
        gold = gold.sort_values(["region", "name"]).reset_index(drop=True)
        print(f"\nCombined gold (v2 + BARMM backfill): {len(gold):,} campuses")

    gold = attach_psgc(gold)
    write_gold(gold)
    write_report(silver, gold)
    write_metrics(silver, gold)
    print("\nDone.")


if __name__ == "__main__":
    main()
