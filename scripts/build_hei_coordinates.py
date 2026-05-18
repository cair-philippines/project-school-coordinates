"""HEI Coordinates Pipeline.

Processes the CHED HEI dataset from bronze to silver (HEI × program table)
and gold (one row per HEI campus with coordinates).

Pipeline steps:
  1. Load bronze Excel
  2. Normalize localities: capture old_* values, harmonize to DepEd naming
  3. Build silver: normalized HEI × program table (22,473 rows)
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
    / "HEIs_with_Regions_latlong_Programs_Disciplines.xlsx"
)
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

# HEI numeric region format → DepEd Roman numeral convention
REGION_MAP = {
    "Region 01": "Region I",
    "Region 02": "Region II",
    "Region 03": "Region III",
    "Region 04-A": "Region IV-A",
    "Region 04-B": "MIMAROPA",
    "Region 05": "Region V",
    "Region 06": "Region VI",
    "Region 07": "Region VII",
    "Region 08": "Region VIII",
    "Region 09": "Region IX",
    "Region 10": "Region X",
    "Region 11": "Region XI",
    "Region 12": "Region XII",
}

# Province name fixes: CHED label → DepEd label
PROVINCE_MAP = {
    "MT. PROVINCE": "MOUNTAIN PROVINCE",
    "COTABATO": "NORTH COTABATO",
    "QUEZON PROVINCE": "QUEZON",
}


# ---------------------------------------------------------------------------
# Step 1: Load bronze
# ---------------------------------------------------------------------------
def load_bronze():
    print(f"Loading bronze: {SOURCE_FILE.name}")
    raw = pd.read_excel(SOURCE_FILE)
    print(f"  Raw rows: {len(raw):,}")

    raw = raw.rename(
        columns={
            "Name of HEI": "name",
            "Region": "region",
            "Province": "province",
            "City and Municipality": "city_municipality",
            "Sector": "sector",
            "Curriculum": "curriculum",
            "Longitude": "longitude",
            "Latitude": "latitude",
            "Sheet1 (2).Unique Institutional Identifier (UII) Code": "uii_code",
            "Sheet1 (2).Program level": "program_level",
            "Sheet1 (2).Discipline Group": "discipline_group",
            "Sheet1 (2).PSCEd/ Program Name": "program_name",
        }
    )

    # Fix Mojibake in string columns (ñ stored as Latin-1 read as UTF-8)
    str_cols = [
        "name", "region", "province", "city_municipality", "sector",
        "curriculum", "discipline_group", "program_name",
    ]
    for col in str_cols:
        raw[col] = (
            raw[col]
            .astype(str)
            .str.encode("latin-1", errors="replace")
            .str.decode("utf-8", errors="replace")
            .str.strip()
        )
        raw[col] = raw[col].replace("nan", None)

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
            "sector", "curriculum", "latitude", "longitude",
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

    print(f"\nGold: {len(gold):,} HEI campuses")
    print(f"  Valid coordinates:   {(gold['coord_status'] == 'valid').sum():,}")
    print(f"  Out-of-bounds:       {(gold['coord_status'] == 'out_of_bounds').sum():,}")
    print(f"  Null UII:            {gold['uii_code'].isna().sum():,}")
    print(f"  Multi-campus:        {gold['is_multi_campus'].sum():,}")

    return gold


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
        {"field": "psgc_observed_region", "value": "PSGC region code — from point-in-polygon against PSA shapefile"},
        {"field": "psgc_observed_province", "value": "PSGC province code — from point-in-polygon"},
        {"field": "psgc_observed_municity", "value": "PSGC municipality/city code (7-digit) — from point-in-polygon"},
        {"field": "psgc_observed_barangay", "value": "PSGC barangay code — from point-in-polygon. Null if campus falls outside all barangay polygons."},
        {"field": "", "value": ""},
        {"field": "PSGC NOTE", "value": "All PSGC codes are spatially observed — no administrative PSGC crosswalk exists for HEIs. No psgc_validation column is produced (nothing to compare against)."},
        {"field": "LOCALITY NOTE", "value": "old_* columns preserve the original CHED strings. region/province/city_municipality are harmonized to DepEd naming so joins across basic and higher education work without an extra layer."},
        {"field": "MULTI-CAMPUS NOTE", "value": "Some UII codes appear under two different codes in the CHED source (e.g., Stella Maris College: 10085 and 13191). This is a CHED data issue and is preserved as-is."},
        {"field": "RELATED FILE", "value": "data/silver/hei_programs.parquet — full HEI x program mapping (22,473 rows)"},
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

    lines = [
        "=" * 60,
        "HEI COORDINATES — BUILD REPORT",
        "=" * 60,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source:    {SOURCE_FILE.name}",
        "",
        f"Silver (HEI × program): {len(silver):,} rows",
        f"Gold (HEI campuses):    {total:,}",
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

    metrics = {
        "pipeline": "hei",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "silver_row_count": int(len(silver)),
        "gold_campus_count": int(len(gold)),
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
    gold = attach_psgc(gold)
    write_gold(gold)
    write_report(silver, gold)
    write_metrics(silver, gold)
    print("\nDone.")


if __name__ == "__main__":
    main()
