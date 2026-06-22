"""Institution Locator API — FastAPI backend.

Loads DepEd, CHED, and TESDA coordinate datasets into memory at startup
and serves search, filter, and detail endpoints.
"""

from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional
import data_loader

app = FastAPI(title="School Locator API", version="1.0.0")


def _match(value, query):
    """Case-insensitive exact match for location filters."""
    if not value or not query:
        return False
    return value.strip().lower() == query.strip().lower()

# ---------------------------------------------------------------------------
# Startup: load data
# ---------------------------------------------------------------------------
schools = None
filter_options = None


@app.on_event("startup")
def startup():
    global schools, filter_options
    # Support both local dev (locator/backend/) and Docker (/app/backend/)
    local_data = Path(__file__).resolve().parent.parent.parent / "data" / "gold"
    docker_data = Path(__file__).resolve().parent.parent / "data" / "gold"
    data_dir = local_data if local_data.exists() else docker_data
    schools = data_loader.load_all(data_dir)
    filter_options = data_loader.build_filter_options(schools)
    print(f"Loaded {len(schools):,} institutions")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.get("/api/schools")
def search_schools(
    q: Optional[str] = Query(None, description="Search term (school name)"),
    sector: Optional[str] = Query(None, description="public or private"),
    region: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    barangay: Optional[str] = Query(None),
    enrollment_status: Optional[str] = Query(None),
    has_coords: Optional[bool] = Query(None, description="Filter to schools with/without coordinates"),
    limit: Optional[int] = Query(None, ge=1, description="Max results; omit for all"),
    offset: int = Query(0, ge=0),
):
    """Search and filter schools. Returns a paginated list."""
    results = schools

    if sector:
        results = [s for s in results if s["sector"] == sector.lower()]

    if region:
        results = [s for s in results if _match(s.get("region"), region)]

    if province:
        results = [s for s in results if _match(s.get("province"), province)]

    if municipality:
        results = [s for s in results if _match(s.get("municipality"), municipality)]

    if barangay:
        results = [s for s in results if _match(s.get("barangay"), barangay)]

    if enrollment_status:
        results = [s for s in results if s.get("enrollment_status") == enrollment_status]

    if has_coords is not None:
        if has_coords:
            results = [s for s in results if s.get("latitude") is not None]
        else:
            results = [s for s in results if s.get("latitude") is None]

    if q:
        q_lower = q.lower()
        # Score by match quality: starts-with > contains > word match
        scored = []
        for s in results:
            name = (s.get("school_name") or "").lower()
            sid = s.get("school_id", "")
            if sid == q:
                scored.append((0, s))  # exact ID match
            elif name.startswith(q_lower):
                scored.append((1, s))
            elif q_lower in name:
                scored.append((2, s))
            elif any(word.startswith(q_lower) for word in name.split()):
                scored.append((3, s))
        scored.sort(key=lambda x: x[0])
        results = [s for _, s in scored]

    total = len(results)
    if limit is not None:
        page = results[offset : offset + limit]
    else:
        page = results[offset:]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": page,
    }


@app.get("/api/schools/{school_id}")
def get_school(school_id: str):
    """Get a single school by ID."""
    for s in schools:
        if s["school_id"] == school_id:
            return s
    return {"error": "School not found"}, 404


@app.get("/api/filters")
def get_filters(
    sector: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
):
    """Get distinct filter values, cascading based on selections."""
    results = schools

    if sector:
        results = [s for s in results if s["sector"] == sector.lower()]

    regions = sorted(set(s["region"] for s in results if s.get("region")))

    provinces = []
    if region:
        filtered = [s for s in results if _match(s.get("region"), region)]
        provinces = sorted(set(s["province"] for s in filtered if s.get("province")))

    municipalities = []
    if province:
        filtered = [s for s in results if _match(s.get("region"), region) and _match(s.get("province"), province)] if region else [s for s in results if _match(s.get("province"), province)]
        municipalities = sorted(set(s["municipality"] for s in filtered if s.get("municipality")))

    barangays = []
    if municipality:
        filtered = [s for s in results if _match(s.get("municipality"), municipality)]
        if province:
            filtered = [s for s in filtered if _match(s.get("province"), province)]
        barangays = sorted(set(s["barangay"] for s in filtered if s.get("barangay")))

    return {
        "regions": regions,
        "provinces": provinces,
        "municipalities": municipalities,
        "barangays": barangays,
    }


@app.get("/api/stats")
def get_stats():
    """Summary statistics across all sectors."""
    public = [s for s in schools if s["sector"] == "public"]
    private = [s for s in schools if s["sector"] == "private"]
    ched = [s for s in schools if s["sector"] in ("ched_public", "ched_private")]
    tesda = [s for s in schools if s["sector"] == "tesda"]
    return {
        "total_schools": len(schools),
        "public_schools": len(public),
        "private_schools": len(private),
        "ched_institutions": len(ched),
        "tesda_institutions": len(tesda),
        "with_coordinates": sum(1 for s in schools if s.get("latitude") is not None),
        "active_enrollment": sum(1 for s in schools if s.get("enrollment_status") == "active"),
    }


@app.get("/api/summary")
def get_summary(
    sector: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
):
    """Summary statistics for a given administrative area."""
    results = schools

    if sector:
        results = [s for s in results if s["sector"] == sector.lower()]
    if region:
        results = [s for s in results if _match(s.get("region"), region)]
    if province:
        results = [s for s in results if _match(s.get("province"), province)]
    if municipality:
        results = [s for s in results if _match(s.get("municipality"), municipality)]

    total = len(results)
    if total == 0:
        return {"total": 0}

    public = [s for s in results if s["sector"] == "public"]
    private = [s for s in results if s["sector"] == "private"]
    ched = [s for s in results if s["sector"] in ("ched_public", "ched_private")]
    tesda = [s for s in results if s["sector"] == "tesda"]
    with_coords = sum(1 for s in results if s.get("latitude") is not None)
    active = sum(1 for s in results if s.get("enrollment_status") == "active")
    no_enrollment = sum(1 for s in results if s.get("enrollment_status") == "no_enrollment_reported")

    # Coordinate source breakdown (DepEd public schools)
    coord_sources = {}
    for s in public:
        src = s.get("coord_source") or "none"
        coord_sources[src] = coord_sources.get(src, 0) + 1

    # GASTPE (DepEd private schools)
    esc = sum(1 for s in private if s.get("esc_participating") == 1)
    shsvp = sum(1 for s in private if s.get("shsvp_participating") == 1)
    jdvp = sum(1 for s in private if s.get("jdvp_participating") == 1)

    # Coord status breakdown (all institutions)
    coord_status = {}
    for s in results:
        st = s.get("coord_status") or "unknown"
        coord_status[st] = coord_status.get(st, 0) + 1

    return {
        "total": total,
        "public": len(public),
        "private": len(private),
        "ched": len(ched),
        "tesda": len(tesda),
        "with_coordinates": with_coords,
        "without_coordinates": total - with_coords,
        "coverage_pct": round(100 * with_coords / total, 1) if total > 0 else 0,
        "active_enrollment": active,
        "no_enrollment_reported": no_enrollment,
        "coord_sources": coord_sources,
        "coord_status": coord_status,
        "gastpe": {"esc": esc, "shsvp": shsvp, "jdvp": jdvp},
    }


# ---------------------------------------------------------------------------
# Serve React frontend (production)
# ---------------------------------------------------------------------------
frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Serve React SPA for all non-API routes."""
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dir / "index.html")
