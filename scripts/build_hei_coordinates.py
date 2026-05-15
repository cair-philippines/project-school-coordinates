"""HEI Coordinates Pipeline.

Processes the CHED HEI dataset from bronze to silver (HEI × program table)
and gold (one row per HEI campus with coordinates).

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

import pandas as pd

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "frozen"
    / "HEIs_with_Regions_latlong_Programs_Disciplines.xlsx"
)
SILVER_DIR = PROJECT_ROOT / "data" / "silver"
OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "gold"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"

# Philippine bounding box
LAT_MIN, LAT_MAX = 4.5, 21.5
LON_MIN, LON_MAX = 116.0, 127.0


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
    str_cols = ["name", "region", "province", "city_municipality", "sector",
                "curriculum", "discipline_group", "program_name"]
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
# Step 2: Build silver — normalized HEI × program table
# ---------------------------------------------------------------------------
def build_silver(raw):
    silver = raw[
        ["uii_code", "name", "region", "province", "city_municipality",
         "sector", "curriculum", "latitude", "longitude",
         "program_level", "discipline_group", "program_name"]
    ].copy()

    silver["uii_missing"] = silver["uii_code"].isna()

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SILVER_DIR / "hei_programs.parquet"
    silver.to_parquet(out_path, index=False)
    print(f"\nSilver written: {out_path} ({len(silver):,} rows)")

    print(f"  Rows with null UII:  {silver['uii_missing'].sum():,}")
    print(f"  Program level breakdown:")
    for level, count in silver["program_level"].value_counts(dropna=False).items():
        print(f"    {level}: {count:,}")

    return silver


# ---------------------------------------------------------------------------
# Step 3: Build gold — one row per HEI campus
# ---------------------------------------------------------------------------
def build_gold(silver):
    # Deduplicate to one row per unique campus (name + location)
    gold = (
        silver[["uii_code", "name", "region", "province", "city_municipality",
                "sector", "latitude", "longitude"]]
        .drop_duplicates(subset=["name", "latitude", "longitude"])
        .reset_index(drop=True)
    )

    # Coordinate bounds check (flag, not reject — source is CHED official)
    gold["coord_status"] = "valid"
    oob_mask = (
        (gold["latitude"] < LAT_MIN) | (gold["latitude"] > LAT_MAX)
        | (gold["longitude"] < LON_MIN) | (gold["longitude"] > LON_MAX)
    )
    gold.loc[oob_mask, "coord_status"] = "out_of_bounds"

    # Flag institutions whose UII appears at more than one campus
    uii_campus_counts = (
        gold[gold["uii_code"].notna()]
        .groupby("uii_code")["name"]
        .transform("count")
    )
    gold["is_multi_campus"] = False
    gold.loc[uii_campus_counts[uii_campus_counts > 1].index, "is_multi_campus"] = True

    gold = gold.sort_values(["region", "name"]).reset_index(drop=True)

    print(f"\nGold: {len(gold):,} HEI campuses")
    print(f"  Valid coordinates:    {(gold['coord_status'] == 'valid').sum():,}")
    print(f"  Out-of-bounds:        {(gold['coord_status'] == 'out_of_bounds').sum():,}")
    print(f"  Null UII:             {gold['uii_code'].isna().sum():,}")
    print(f"  Multi-campus (flag):  {gold['is_multi_campus'].sum():,}")

    return gold


# ---------------------------------------------------------------------------
# Step 4: Write gold outputs
# ---------------------------------------------------------------------------
def write_gold(gold):
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    parquet_path = OUTPUT_DATA_DIR / "hei_coordinates.parquet"
    csv_path = OUTPUT_DATA_DIR / "hei_coordinates.csv"
    xlsx_path = OUTPUT_DATA_DIR / "hei_coordinates.xlsx"

    gold.to_parquet(parquet_path, index=False)
    gold.to_csv(csv_path, index=False)

    total = len(gold)
    valid = (gold["coord_status"] == "valid").sum()
    oob = (gold["coord_status"] == "out_of_bounds").sum()
    null_uii = gold["uii_code"].isna().sum()
    multi = gold["is_multi_campus"].sum()

    metadata = pd.DataFrame([
        {"field": "Pipeline", "value": "HEI Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Source File", "value": SOURCE_FILE.name},
        {"field": "Total HEI Campuses", "value": f"{total:,}"},
        {"field": "With Valid Coordinates", "value": f"{valid:,}"},
        {"field": "Out-of-Bounds Coordinates", "value": f"{oob:,}"},
        {"field": "Null UII Code", "value": f"{null_uii:,}"},
        {"field": "Multi-Campus Institutions", "value": f"{multi:,} campuses across multi-campus HEIs"},
        {"field": "", "value": ""},
        {"field": "COLUMN DICTIONARY", "value": ""},
        {"field": "uii_code", "value": "CHED Unique Institutional Identifier. Null for HEIs with no UII in source data."},
        {"field": "name", "value": "Official HEI name (CHED)"},
        {"field": "region", "value": "Administrative region"},
        {"field": "province", "value": "Province"},
        {"field": "city_municipality", "value": "City or municipality"},
        {"field": "sector", "value": "Ownership sector (Private, Public SUC Main, Public SUC Satellite, Public LUC, OGS)"},
        {"field": "latitude", "value": "Latitude (WGS84)"},
        {"field": "longitude", "value": "Longitude (WGS84)"},
        {"field": "coord_status", "value": "valid = within PH bounding box; out_of_bounds = outside [4.5-21.5, 116-127]"},
        {"field": "is_multi_campus", "value": "True if this UII code appears at more than one distinct location"},
        {"field": "", "value": ""},
        {"field": "NOTE ON MULTI-CAMPUS", "value": "Some UII codes appear twice in the source (e.g., Stella Maris College: 10085 and 13191). This is a CHED data issue and is preserved as-is."},
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
# Step 5: Build report + metrics
# ---------------------------------------------------------------------------
def write_report(silver, gold):
    total_campuses = len(gold)
    valid = (gold["coord_status"] == "valid").sum()
    oob = (gold["coord_status"] == "out_of_bounds").sum()
    null_uii = gold["uii_code"].isna().sum()

    lines = [
        "=" * 60,
        "HEI COORDINATES — BUILD REPORT",
        "=" * 60,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Source:    {SOURCE_FILE.name}",
        "",
        f"Silver (HEI × program): {len(silver):,} rows",
        f"Gold (HEI campuses):    {total_campuses:,}",
        "",
        "Coordinate status:",
        f"  valid:          {valid:,}",
        f"  out_of_bounds:  {oob:,}",
        "",
        f"Null UII Code: {null_uii:,} campuses",
        f"Multi-campus:  {gold['is_multi_campus'].sum():,} campuses flagged",
        "",
        "Sector breakdown:",
    ]
    for sector, count in gold["sector"].value_counts(dropna=False).items():
        lines.append(f"  {sector}: {count:,}")

    lines += ["", "Regional distribution:"]
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
        "null_uii_count": int(gold["uii_code"].isna().sum()),
        "multi_campus_count": int(gold["is_multi_campus"].sum()),
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
    silver = build_silver(raw)
    gold = build_gold(silver)
    write_gold(gold)
    write_report(silver, gold)
    write_metrics(silver, gold)
    print("\nDone.")


if __name__ == "__main__":
    main()
