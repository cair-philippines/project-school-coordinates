# HEI Source Registry

Provenance record for CHED higher education institution coordinate datasets.
Each entry documents a source file vintage, its structural characteristics, the
pipeline adjustments it required, and the outputs it produced. Entries are in
chronological order. See `data/bronze/frozen/` for the files themselves.

---

## v1 — HEIs_with_Regions_latlong_Programs_Disciplines.xlsx

| Field | Value |
|---|---|
| **Filename** | `HEIs_with_Regions_latlong_Programs_Disciplines.xlsx` |
| **Academic year** | Not stated (received ~2026-05) |
| **Sheet** | `Merge1` |
| **Header row** | Row 1 (no skip needed) |
| **Data rows** | 22,473 |
| **Unique campuses (gold)** | 2,422 |

### Column schema

| Source column name | Internal name |
|---|---|
| `Name of HEI` | `name` |
| `Region` | `region` |
| `Province` | `province` |
| `City and Municipality` | `city_municipality` |
| `Sector` | `sector` |
| `Curriculum` | `curriculum` |
| `Longitude` | `longitude` |
| `Latitude` | `latitude` |
| `Sheet1 (2).Unique Institutional Identifier (UII) Code` | `uii_code` |
| `Sheet1 (2).Program level` | `program_level` |
| `Sheet1 (2).Discipline Group` | `discipline_group` |
| `Sheet1 (2).PSCEd/ Program Name` | `program_name` |

### Sector vocabulary

| Source value | Mapped to |
|---|---|
| `Private` | `ched_private` |
| `Public SUC Main` | `ched_public` |
| `Public SUC Satellite` | `ched_public` |
| `Public LUC` | `ched_public` |
| `OGS` | `ched_public` |

### Region format

`"Region 01"`, `"Region 04-A"`, `"Region 04-B"` — numeric style. Mapped to
DepEd Roman numeral convention via `REGION_MAP`. BARMM, CAR, CARAGA, NCR were
already in DepEd format and passed through unchanged.

### Known issues / pipeline adjustments

- **Mojibake**: ñ and other non-ASCII characters were stored as Latin-1 bytes
  inside the Excel file, read back as garbled UTF-8. Fixed by `.encode("latin-1").decode("utf-8")` on all string columns.
- **Null UIIs**: ~460 campuses had no UII code. Discipline group join in
  `data_loader.py` falls back to `(name.lower(), city.lower())` key for these.
- **Multi-campus UIIs**: 8 campuses shared UII codes that appeared at multiple
  distinct coordinates (CHED data issue, preserved as-is).
- **CAGAYAN VALLEY province**: some records had the region name in the province
  field — nulled and backfilled from PSGC shapefile.

### Gold output stats (generated 2026-05-18)

| Metric | Value |
|---|---|
| Gold campuses | 2,422 |
| Valid coordinates | 2,422 (100%) |
| Out-of-bounds | 0 |
| Null UII | 460 |
| Multi-campus flag | 8 |
| PSGC matched | 2,418 / 2,422 (99.8%) |
| Outside all polygons | 4 |
| BARMM campuses | 111 |
| NIR campuses | 0 (not present in source) |

### Program level vocabulary (Curriculum column)

`Baccalaureate`, `Master's`, `Pre-baccalaureate`, `Post-baccalaureate`, `Doctorate`

---

## v2 — Annex A - CHED Template of the Requested Data_Table.xlsx

| Field | Value |
|---|---|
| **Filename** | `Annex A - CHED Template of the Requested Data_Table.xlsx` |
| **Academic year** | AY 2024-2025 |
| **Sheet** | `Table` |
| **Header row** | Row 3 (row 1 blank, row 2 title: "AY 2024–2025 HEI Coordinates") |
| **Data rows** | 25,058 |
| **Unique campuses (gold)** | 2,321 |

### Column schema

Column A in the spreadsheet is unnamed and empty — skipped via `usecols=range(1, 12)`.

| Source column name | Internal name |
|---|---|
| `Unique Institutional Identifier (UII)` | `uii_code` |
| `Name of HEI` | `name` |
| `Region` | `region` |
| `Province` | `province` |
| `City/Municipality2` | `city_municipality` |
| `Sector` | `sector` |
| `Longitude` | `longitude` |
| `Latitude` | `latitude` |
| `Program Level` | `program_level` |
| `Discipline Group` | `discipline_group` |
| `PSCED/Program Name` | `program_name` |

Note: `Curriculum` column is absent in this vintage. Program level now uses
ISCED numeric codes (e.g., `"6 - Bachelor level education or equivalent"`).

### Sector vocabulary

More granular than v1. `"Private"` splits into Sectarian/Non-Sectarian;
`"Public LUC"` splits into `LUC` and `LUC with Institutional Recognition`;
`"OGS"` is absent; `"Special HEI"` is new (4 campuses — government-chartered).

| Source value | Mapped to |
|---|---|
| `Private Non-Sectarian` | `ched_private` |
| `Private Sectarian` | `ched_private` |
| `SUC Main` | `ched_public` |
| `SUC Satellite` | `ched_public` |
| `LUC` | `ched_public` |
| `LUC with Institutional Recognition` | `ched_public` |
| `Special HEI` | `ched_public` |

### Region format

`"01 - Ilocos Region"`, `"13 - Nat. Capital Region"` etc. — numeric prefix +
name style. Fully remapped to DepEd Roman numeral convention via updated
`REGION_MAP`. NIR (`"18 - Negros Island Region"`) is new in this vintage →
mapped to `"NIR"`. BARMM is absent from this vintage entirely.

### Known issues / pipeline adjustments

- **Header offset**: `skiprows=2` and `usecols=range(1, 12)` required.
- **Encoding**: clean UTF-8 — mojibake fix from v1 removed.
- **BARMM absent**: 111 campuses present in v1 have no entry in this vintage.
  Whether they were folded into other regions, excluded from the CHED snapshot,
  or genuinely closed is unknown. Treated as a data gap, not a deletion.
- **Campus count decrease despite more program rows**: v2 has +2,585 silver rows
  but -101 gold campuses relative to v1. The new file likely consolidates
  campuses that were previously listed under separate coordinates, and drops
  BARMM entirely (−111).
- **Null UIIs**: reduced from 460 → 1 (single unidentified record).
- **Multi-campus**: 0 (down from 8 in v1 — CHED corrected the duplicate UIIs).
- **Outside all polygons**: 20 campuses (up from 4 in v1) — likely new campuses
  near coastlines or in areas with polygon gaps in the shapefile.

### Gold output stats (generated 2026-07-09)

| Metric | Value |
|---|---|
| Gold campuses | 2,321 |
| Valid coordinates | 2,321 (100%) |
| Out-of-bounds | 0 |
| Null UII | 1 |
| Multi-campus flag | 0 |
| PSGC matched | 2,300 / 2,321 (99.1%) |
| Outside all polygons | 20 |
| BARMM campuses | 0 (absent from source) |
| NIR campuses | 88 (new in this vintage) |

### Delta vs v1

| Metric | v1 | v2 | Change |
|---|---|---|---|
| Silver rows | 22,473 | 25,058 | +2,585 (+11.5%) |
| Gold campuses | 2,422 | 2,321 | −101 (−4.2%) |
| Null UIIs | 460 | 1 | −459 |
| BARMM campuses | 111 | 0 | −111 |
| NIR campuses | 0 | 88 | +88 |
| Outside polygons | 4 | 20 | +16 |

---

## BARMM Backfill (applied 2026-07-09)

BARMM is absent from the AY 2024-2025 source. To preserve coverage, the 111 BARMM campuses
from v1 are backfilled into the gold output. Silver is not updated (no program-level rows are
carried forward). Backfilled records are tagged `source_vintage='v1_barmm_backfill'` in the
gold table to make the provenance explicit.

### Sector translation applied (v1 → v2 vocabulary)

| v1 value | v2 value used in gold |
|---|---|
| `Private` | `Private Non-Sectarian` |
| `Public SUC Main` | `SUC Main` |
| `Public SUC Satellite` | `SUC Satellite` |
| `Public LUC` | `LUC` |
| `OGS` | `Special HEI` |

Note: v1 does not distinguish Private Sectarian from Non-Sectarian. All v1 private BARMM
campuses are mapped to `Private Non-Sectarian` as the closest equivalent.

### Gold output stats after backfill (generated 2026-07-09)

| Metric | v2 only | v2 + BARMM backfill | Change |
|---|---|---|---|
| Gold campuses | 2,321 | 2,432 | +111 |
| BARMM campuses | 0 | 111 | +111 |
| Null UIIs | 1 | 109 | +108 (BARMM had no UIIs in v1) |
| PSGC matched | 2,300 / 2,321 | 2,408 / 2,432 | +108 matched |
| Outside all polygons | 20 | 23 | +3 (3 BARMM campuses) |
