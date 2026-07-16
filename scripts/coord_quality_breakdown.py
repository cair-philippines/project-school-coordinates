"""Coordinate Quality Breakdown (stakeholder-facing).

Produces a simple, three-bucket quality summary of the MOST CURRENT gold
coordinates for each data owner: DepEd (public + private schools), CHED
(HEIs), and TESDA. Intended to populate a stakeholder slide.

The three buckets, defined so they mean the SAME THING across all agencies:

  clean               Coordinate plots on Philippine land AND agrees with the
                      institution's stated administrative location.
  needs_verification  Coordinate plots on PH land but DISAGREES with the stated
                      location (a soft flag: plottable, but not trustworthy).
  most_likely_error   No coordinate at all, outside the PH bounding box, or plots
                      outside every PH land polygon (sea / abroad); plus DepEd
                      placeholder / garbage submissions.

IMPORTANT ASYMMETRY (surfaced in the report and JSON so the slide can footnote it):
  - DepEd public/private coordinates were validated at the MUNICIPALITY / BARANGAY
    level (land-polygon + declared-municipality checks in their build pipelines).
  - CHED and TESDA coordinates were only bounding-box checked in their builds. Here
    we reconstruct the stronger checks from signals they DO carry:
      * a null `psgc_observed_*` means the point fell outside every PH land polygon
        (equivalent to DepEd's `outside_all_polygons`);
      * a REGION-level admin check, self-calibrated from the data (the modal claimed
        region per observed-region code), flags points that land in a different
        region than declared.
    So CHED/TESDA are checked at REGION level (coarser than DepEd's municipality
    level). Their "clean" is therefore a slightly weaker guarantee and their
    "needs_verification" is likely understated. This is disclosed, not hidden.

Outputs:
  output/coord_quality_breakdown.csv    tidy table (one row per agency)
  output/coord_quality_breakdown.json   counts + percentages + methodology notes

Run:
  python scripts/coord_quality_breakdown.py
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "data" / "gold"
OUT = ROOT / "output"

# DepEd rejection reasons that mean the coordinate is unusable / clearly wrong.
DEPED_ERROR_REASONS = {
    "out_of_bounds",        # outside the PH bounding box
    "outside_all_polygons", # inside the box but on no PH land polygon (sea/abroad)
    "placeholder_default",  # a default/placeholder value, not a real location
    "invalid",              # unparseable / garbage
}
# DepEd rejection reasons where a coordinate exists on land but disagrees with the
# stated location (or is too imprecise to trust) -> needs verification.
DEPED_SOFT_REASONS = {
    "wrong_municipality",
    "round_coordinates",
    "coordinate_cluster",
}

BUCKETS = ["clean", "needs_verification", "most_likely_error"]


def _classify_deped(df: pd.DataFrame) -> pd.Series:
    """Worst-wins bucket per row for a DepEd (public/private) gold table."""
    st = df["coord_status"]
    rr = df["coord_rejection_reason"]
    pv = df["psgc_validation"] if "psgc_validation" in df.columns else None
    latlon_null = df["latitude"].isna() | df["longitude"].isna()

    error = latlon_null | (st == "no_coords") | rr.isin(DEPED_ERROR_REASONS)
    soft = (st == "suspect") & rr.isin(DEPED_SOFT_REASONS)
    mismatch = (pv == "psgc_mismatch") if pv is not None else pd.Series(False, index=df.index)
    needs = (~error) & (soft | mismatch)

    out = pd.Series("clean", index=df.index)
    out[needs] = "needs_verification"
    out[error] = "most_likely_error"  # error wins over everything
    return out


def _classify_bbox(df: pd.DataFrame):
    """Worst-wins bucket per row for CHED/TESDA gold, plus the calibration map.

    Error   : no coordinate, out of PH bbox, or outside every land polygon
              (null psgc_observed_region while a coordinate is present).
    Needs   : on land but lands in a different REGION than declared, using a
              self-calibrated modal-region map (no external reference table).
    Clean   : on land and region agrees.
    """
    st = df["coord_status"]
    latlon_null = df["latitude"].isna() | df["longitude"].isna()
    obs_null = df["psgc_observed_region"].isna()

    error = (
        latlon_null
        | st.isin(["null_coords", "out_of_bounds"])
        | (obs_null & ~latlon_null)
    )

    # Self-calibrate: for each observed-region code, the declared region name that
    # MOST records agree on is treated as the correct name for that code.
    on_land = df[~error].copy()
    on_land["_obsreg"] = on_land["psgc_observed_region"].astype(str)
    modal = (
        on_land.groupby("_obsreg")["region"]
        .agg(lambda s: s.mode().iat[0] if len(s.mode()) else None)
    )
    expected = on_land["_obsreg"].map(modal)
    claimed = on_land["region"].astype(str).str.upper().str.strip()
    exp_norm = expected.astype(str).str.upper().str.strip()
    region_mismatch = claimed != exp_norm

    needs = pd.Series(False, index=df.index)
    needs.loc[on_land.index[region_mismatch]] = True

    out = pd.Series("clean", index=df.index)
    out[needs] = "needs_verification"
    out[error] = "most_likely_error"
    calib = {str(k): (None if v is None else str(v)) for k, v in modal.items()}
    return out, calib


def _summarize(label: str, source: str, buckets: pd.Series) -> dict:
    n = len(buckets)
    counts = {b: int((buckets == b).sum()) for b in BUCKETS}
    pct = {b: round(counts[b] / n * 100, 1) if n else 0.0 for b in BUCKETS}
    return {
        "agency": label,
        "source_dataset": source,
        "total": n,
        "counts": counts,
        "pct": pct,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)

    public = pd.read_parquet(GOLD / "public_school_coordinates.parquet")
    private = pd.read_parquet(GOLD / "private_school_coordinates.parquet")
    hei = pd.read_parquet(GOLD / "hei_coordinates.parquet")
    tesda = pd.read_parquet(GOLD / "tesda_coordinates.parquet")

    rows = []
    rows.append(_summarize("DepEd (public schools)",
                           "public_school_coordinates.parquet",
                           _classify_deped(public)))
    rows.append(_summarize("DepEd (private schools)",
                           "private_school_coordinates.parquet",
                           _classify_deped(private)))
    hei_b, hei_calib = _classify_bbox(hei)
    rows.append(_summarize("CHED (HEIs)", "hei_coordinates.parquet", hei_b))
    tesda_b, tesda_calib = _classify_bbox(tesda)
    rows.append(_summarize("TESDA", "tesda_coordinates.parquet", tesda_b))

    # ---- tidy CSV ----
    table = pd.DataFrame([
        {
            "agency": r["agency"],
            "clean": r["counts"]["clean"],
            "needs_verification": r["counts"]["needs_verification"],
            "most_likely_error": r["counts"]["most_likely_error"],
            "total": r["total"],
            "clean_pct": r["pct"]["clean"],
            "needs_verification_pct": r["pct"]["needs_verification"],
            "most_likely_error_pct": r["pct"]["most_likely_error"],
        }
        for r in rows
    ])
    table.to_csv(OUT / "coord_quality_breakdown.csv", index=False)

    # ---- JSON with methodology ----
    payload = {
        "buckets": {
            "clean": "Coordinate plots on PH land AND agrees with the stated admin location.",
            "needs_verification": "Plots on PH land but disagrees with the stated location "
                                  "(DepEd: wrong municipality / barangay mismatch / round "
                                  "coordinates / cluster; CHED & TESDA: different region than declared).",
            "most_likely_error": "No coordinate, outside the PH bounding box, or outside every "
                                 "PH land polygon (sea/abroad); plus DepEd placeholder/garbage.",
        },
        "asymmetry_caveat": (
            "DepEd is validated at municipality/barangay level; CHED and TESDA at region level "
            "(their psgc_observed codes are a different PSGC vintage than the DepEd municipality "
            "crosswalk). CHED/TESDA 'clean' is a slightly weaker guarantee and their "
            "'needs_verification' is likely understated."
        ),
        "region_calibration": {"CHED": hei_calib, "TESDA": tesda_calib},
        "agencies": rows,
    }
    with open(OUT / "coord_quality_breakdown.json", "w") as f:
        json.dump(payload, f, indent=2)

    # ---- console report ----
    print("=" * 78)
    print("COORDINATE QUALITY BREAKDOWN  (most current gold coordinates)")
    print("=" * 78)
    hdr = f"{'Agency':<26}{'Clean':>14}{'Needs verif.':>16}{'Likely error':>16}{'Total':>10}"
    print(hdr)
    print("-" * 82)
    for r in rows:
        c, nn, e = r["counts"]["clean"], r["counts"]["needs_verification"], r["counts"]["most_likely_error"]
        pc, pn, pe = r["pct"]["clean"], r["pct"]["needs_verification"], r["pct"]["most_likely_error"]
        print(f"{r['agency']:<26}"
              f"{c:>8,} ({pc:>4.1f}%)"
              f"{nn:>8,} ({pn:>4.1f}%)"
              f"{e:>8,} ({pe:>4.1f}%)"
              f"{r['total']:>10,}")
    print("-" * 82)
    print("\nNote: DepEd validated at municipality/barangay level; CHED & TESDA at region level.")
    print(f"Wrote {OUT / 'coord_quality_breakdown.csv'}")
    print(f"Wrote {OUT / 'coord_quality_breakdown.json'}")


if __name__ == "__main__":
    main()
