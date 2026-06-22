"""Data loader — reads parquet files into memory as plain dicts."""

import math
from pathlib import Path
import pandas as pd

LOCATION_COLS = ["region", "province", "municipality", "barangay"]

PUBLIC_HEI_SECTORS = {"Public SUC Main", "Public SUC Satellite", "Public LUC", "OGS"}


def _title_case(val):
    """Normalize location strings to title case for display consistency."""
    import re
    if not val or not isinstance(val, str):
        return val
    val = val.strip()
    if not val:
        return None
    val = re.sub(r'\s+', ' ', val)
    val = re.sub(r'\s*,\s*', ', ', val)
    KEEP_UPPER = {"NCR", "CAR", "BARMM", "NIR", "CARAGA", "MIMAROPA"}
    if val.upper() in KEEP_UPPER:
        return val.upper()
    if val.upper().startswith("REGION "):
        return "Region " + val[7:].strip()
    return val.title()


def _clean_row(row: dict) -> dict:
    """Replace NaN/None with None for JSON serialization."""
    cleaned = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return cleaned


def _normalize_locations(df):
    """Normalize location column casing for consistency across datasets."""
    for col in LOCATION_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_title_case)
    return df


def _normalize_uii(uii):
    """Normalize UII code to a consistent string key (handles float/int/str)."""
    if uii is None:
        return None
    try:
        return str(int(float(uii)))
    except (ValueError, TypeError):
        return str(uii)


def _load_hei_discipline_map(silver_path: Path) -> tuple[dict, dict]:
    """Return (uii_discipline_map, name_city_discipline_map) from HEI silver."""
    uii_map = {}
    name_city_map = {}
    if not silver_path.exists():
        return uii_map, name_city_map
    silver = pd.read_parquet(
        silver_path,
        columns=["uii_code", "name", "city_municipality", "discipline_group"],
    )
    for uii, grp in silver[silver["uii_code"].notna()].groupby("uii_code"):
        groups = sorted(grp["discipline_group"].dropna().unique().tolist())
        if groups:
            uii_map[_normalize_uii(uii)] = groups
    no_uii = silver[silver["uii_code"].isna()]
    for (name, city), grp in no_uii.groupby(["name", "city_municipality"]):
        groups = sorted(grp["discipline_group"].dropna().unique().tolist())
        if groups:
            key = (
                name.lower() if isinstance(name, str) else "",
                city.lower() if isinstance(city, str) else "",
            )
            name_city_map[key] = groups
    return uii_map, name_city_map


def _load_tesda_program_sectors_map(silver_path: Path) -> dict:
    """Return tesda_inst_id → sorted list of program sectors from TESDA silver."""
    if not silver_path.exists():
        return {}
    silver = pd.read_parquet(silver_path, columns=["tesda_inst_id", "sector"])
    result = {}
    for inst_id, grp in silver.groupby("tesda_inst_id"):
        sectors = sorted(grp["sector"].dropna().unique().tolist())
        if sectors:
            result[inst_id] = sectors
    return result


def load_all(data_dir: Path) -> list[dict]:
    """Load all sectors; return combined list of dicts."""
    schools = []
    silver_dir = data_dir.parent / "silver"

    # --- DepEd Public ---
    public_path = data_dir / "public_school_coordinates.parquet"
    if public_path.exists():
        df = pd.read_parquet(public_path)
        df["sector"] = "public"
        df = _normalize_locations(df)
        for _, row in df.iterrows():
            schools.append(_clean_row(row.to_dict()))
        print(f"  DepEd Public: {len(df):,} schools")

    # --- DepEd Private ---
    private_path = data_dir / "private_school_coordinates.parquet"
    if private_path.exists():
        df = pd.read_parquet(private_path)
        df["sector"] = "private"
        df = _normalize_locations(df)
        df["coord_source"] = df["coord_status"].apply(
            lambda x: "tosf_self_reported" if x in ("valid", "fixed_swap") else None
        )
        for _, row in df.iterrows():
            schools.append(_clean_row(row.to_dict()))
        print(f"  DepEd Private: {len(df):,} schools")

    # --- CHED HEIs ---
    hei_path = data_dir / "hei_coordinates.parquet"
    if hei_path.exists():
        uii_map, name_city_map = _load_hei_discipline_map(silver_dir / "hei_programs.parquet")
        df = pd.read_parquet(hei_path)
        df["school_id"] = [f"HEI{i + 1:05d}" for i in range(len(df))]
        df["hei_ownership"] = df["sector"]
        df["sector"] = df["hei_ownership"].apply(
            lambda x: "ched_public" if x in PUBLIC_HEI_SECTORS else "ched_private"
        )
        oob_mask = df["coord_status"] == "out_of_bounds"
        df.loc[oob_mask, ["latitude", "longitude"]] = None
        df.loc[oob_mask, "coord_status"] = "no_coords"
        df = df.rename(columns={"name": "school_name", "city_municipality": "municipality"})
        df = _normalize_locations(df)
        for _, row in df.iterrows():
            d = _clean_row(row.to_dict())
            uii = _normalize_uii(d.get("uii_code"))
            if uii:
                d["discipline_groups"] = uii_map.get(uii, [])
            else:
                key = (
                    (d.get("school_name") or "").lower(),
                    (d.get("municipality") or "").lower(),
                )
                d["discipline_groups"] = name_city_map.get(key, [])
            schools.append(d)
        print(f"  CHED HEI: {len(df):,} campuses")

    # --- TESDA ---
    tesda_path = data_dir / "tesda_coordinates.parquet"
    if tesda_path.exists():
        ps_map = _load_tesda_program_sectors_map(silver_dir / "tesda_programs.parquet")
        df = pd.read_parquet(tesda_path)
        df = df.rename(columns={
            "tesda_inst_id": "school_id",
            "name": "school_name",
            "city_municipality": "municipality",
        })
        df["sector"] = "tesda"
        bad_mask = df["coord_status"].isin(["null_coords", "out_of_bounds"])
        df.loc[bad_mask, ["latitude", "longitude"]] = None
        df.loc[bad_mask, "coord_status"] = "no_coords"
        df = _normalize_locations(df)
        for _, row in df.iterrows():
            d = _clean_row(row.to_dict())
            d["program_sectors"] = ps_map.get(d.get("school_id", ""), [])
            schools.append(d)
        print(f"  TESDA: {len(df):,} institutions")

    return schools


def build_filter_options(schools: list[dict]) -> dict:
    """Pre-compute distinct filter values."""
    return {
        "sectors": sorted(set(s["sector"] for s in schools)),
        "regions": sorted(set(s["region"] for s in schools if s.get("region"))),
    }
