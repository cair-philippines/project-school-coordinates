import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, LayersControl } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import MapLegend from "./MapLegend";

// Fix default marker icons in bundled environments
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const SECTOR_COLORS = {
  public: "#22c55e",       // DepEd public — green
  private: "#3b82f6",      // DepEd private — blue
  ched_public: "#7c3aed",  // CHED public — violet
  ched_private: "#a78bfa", // CHED private — light violet
  tesda: "#f97316",        // TESDA — orange
};

function sectorColor(school) {
  return SECTOR_COLORS[school.sector] || "#9ca3b8";
}

const PH_CENTER = [12.5, 122.0];
const PH_ZOOM = 6;

/**
 * Coord-status-aware marker visuals:
 *
 * CONFIDENT (coord_status = valid or fixed_swap):
 *   Solid green dot — public
 *   Solid blue dot — private
 *
 * SUSPECT — wrong_municipality or round_coordinates:
 *   Green/blue dot + static orange ring
 *
 * SUSPECT — outside_all_polygons:
 *   Green/blue dot + pulsing red ring (most severe)
 *
 * SUSPECT — placeholder_default or coordinate_cluster:
 *   Green/blue dot + red X overlay (known fake)
 *
 * NO COORD_STATUS or psgc_no_validation only:
 *   Gray dot
 */
function createIcon(school) {
  const color = sectorColor(school);
  const status = school.coord_status;
  const reason = school.coord_rejection_reason;

  // Known fake coordinates — red X overlay
  if (status === "suspect" && (reason === "placeholder_default" || reason === "coordinate_cluster")) {
    return L.divIcon({
      className: "",
      html: `<div style="position:relative; width:16px; height:16px;">
        <div style="
          position:absolute; top:2px; left:2px;
          width:12px; height:12px;
          background:${color};
          border:2px solid white;
          border-radius:50%;
          box-shadow:0 2px 4px rgba(0,0,0,0.3);
          z-index:2;
        "></div>
        <div style="
          position:absolute; top:1px; left:1px;
          width:14px; height:14px;
          z-index:3;
          display:flex; align-items:center; justify-content:center;
          font-size:12px; font-weight:900; color:#ef4444;
          text-shadow:0 0 2px white, 0 0 2px white;
          line-height:1;
        ">&times;</div>
      </div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      popupAnchor: [0, -10],
    });
  }

  // Over water / outside all polygons — pulsing red ring (most severe)
  if (status === "suspect" && reason === "outside_all_polygons") {
    return L.divIcon({
      className: "",
      html: `<div style="position:relative; width:16px; height:16px;">
        <div style="
          position:absolute; top:2px; left:2px;
          width:12px; height:12px;
          background:${color};
          border:2px solid white;
          border-radius:50%;
          box-shadow:0 2px 4px rgba(0,0,0,0.3);
          z-index:2;
        "></div>
        <div style="
          position:absolute; top:0; left:0;
          width:16px; height:16px;
          border-radius:50%;
          background:rgba(239,68,68,0.4);
          animation:pulse-ring 2s ease-out infinite;
        "></div>
      </div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      popupAnchor: [0, -10],
    });
  }

  // Wrong municipality or round coordinates — static orange ring
  if (status === "suspect" && (reason === "wrong_municipality" || reason === "round_coordinates")) {
    return L.divIcon({
      className: "",
      html: `<div style="position:relative; width:16px; height:16px;">
        <div style="
          position:absolute; top:2px; left:2px;
          width:12px; height:12px;
          background:${color};
          border:2px solid white;
          border-radius:50%;
          box-shadow:0 2px 4px rgba(0,0,0,0.3);
          z-index:2;
        "></div>
        <div style="
          position:absolute; top:0; left:0;
          width:16px; height:16px;
          border-radius:50%;
          border:2px solid #f97316;
          opacity:0.7;
        "></div>
      </div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      popupAnchor: [0, -10],
    });
  }

  // Confident — solid dot
  if (status === "valid" || status === "fixed_swap") {
    return L.divIcon({
      className: "",
      html: `<div style="
        width:12px; height:12px;
        background:${color};
        border:2px solid white;
        border-radius:50%;
        box-shadow:0 2px 4px rgba(0,0,0,0.3);
      "></div>`,
      iconSize: [12, 12],
      iconAnchor: [6, 6],
      popupAnchor: [0, -8],
    });
  }

  // Fallback: gray dot (no coord_status, or unknown)
  return L.divIcon({
    className: "",
    html: `<div style="
      width:12px; height:12px;
      background:#9ca3b8;
      border:2px solid white;
      border-radius:50%;
      box-shadow:0 2px 4px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -8],
  });
}

/**
 * Compute robust bounding box, excluding spatial outliers.
 * Uses IQR (interquartile range) on lat and lon separately
 * to filter out stray points before computing bounds.
 */
function robustBounds(markers) {
  if (markers.length === 0) return null;
  if (markers.length <= 3) {
    return L.latLngBounds(markers.map((s) => [s.latitude, s.longitude]));
  }

  const lats = markers.map((s) => s.latitude).sort((a, b) => a - b);
  const lons = markers.map((s) => s.longitude).sort((a, b) => a - b);

  const q1Idx = Math.floor(lats.length * 0.25);
  const q3Idx = Math.floor(lats.length * 0.75);

  const latQ1 = lats[q1Idx], latQ3 = lats[q3Idx];
  const lonQ1 = lons[q1Idx], lonQ3 = lons[q3Idx];
  const latIQR = latQ3 - latQ1;
  const lonIQR = lonQ3 - lonQ1;

  // 2x IQR fence — generous enough to keep legitimate spread,
  // tight enough to exclude stray bad coordinates
  const latMin = latQ1 - 2 * latIQR;
  const latMax = latQ3 + 2 * latIQR;
  const lonMin = lonQ1 - 2 * lonIQR;
  const lonMax = lonQ3 + 2 * lonIQR;

  const inliers = markers.filter(
    (s) =>
      s.latitude >= latMin && s.latitude <= latMax &&
      s.longitude >= lonMin && s.longitude <= lonMax
  );

  // Fall back to all markers if IQR filtering removed too many
  const pts = inliers.length >= markers.length * 0.5 ? inliers : markers;
  return L.latLngBounds(pts.map((s) => [s.latitude, s.longitude]));
}

/**
 * Two independent effects:
 * 1. flyToTrigger — explicit "fly to this school" command, highest priority
 * 2. signature — markers changed from filter/search, fit bounds
 *
 * They don't interfere because flyToTrigger only fires on user click,
 * and signature only fires on filter/search result changes.
 */
function MapViewController({ selectedSchool, markers, mode, flyToTrigger }) {
  const map = useMap();
  const prevSignature = useRef("");
  const prevTrigger = useRef(0);

  const signature = useMemo(() => {
    if (markers.length === 0) return "empty";
    const first = markers[0]?.school_id || "";
    const last = markers[markers.length - 1]?.school_id || "";
    return `${markers.length}:${first}:${last}`;
  }, [markers]);

  // Effect 1: Explicit fly-to command (user clicked a school)
  useEffect(() => {
    if (flyToTrigger === prevTrigger.current) return;
    prevTrigger.current = flyToTrigger;
    if (!selectedSchool) return;

    // Stop any in-progress animation
    map.stop();

    if (selectedSchool.latitude && selectedSchool.longitude) {
      map.flyTo([selectedSchool.latitude, selectedSchool.longitude], 16, {
        duration: 1.2,
      });
    } else {
      // No coords — zoom to locality as best-effort
      const locality = selectedSchool.municipality || selectedSchool.province || selectedSchool.region;
      if (locality && markers.length > 0) {
        const field = selectedSchool.municipality ? "municipality"
          : selectedSchool.province ? "province" : "region";
        const nearby = markers.filter(
          (s) => s[field] && s[field].toLowerCase() === locality.toLowerCase()
        );
        if (nearby.length > 0) {
          const bounds = robustBounds(nearby);
          if (bounds && bounds.isValid()) {
            map.flyToBounds(bounds, { padding: [40, 40], maxZoom: 13, duration: 1.2 });
          }
        }
      }
    }
    // Update signature so Effect 2 doesn't re-zoom
    prevSignature.current = signature;
  }, [flyToTrigger, selectedSchool, markers, signature, map]);

  // Effect 2: Markers changed (filter/search results updated)
  useEffect(() => {
    if (signature === prevSignature.current) return;
    prevSignature.current = signature;

    if (signature === "empty") {
      map.flyTo(PH_CENTER, PH_ZOOM, { duration: 1.0 });
    } else if (mode !== "search") {
      const bounds = robustBounds(markers);
      if (bounds && bounds.isValid()) {
        map.flyToBounds(bounds, {
          padding: [40, 40],
          maxZoom: 15,
          duration: 1.2,
        });
      }
    }
  }, [signature, markers, mode, map]);

  return null;
}

const MAP_MARKER_CAP = 3000;

/**
 * Cap markers for rendering performance while preserving sector proportions.
 * If total exceeds the cap, sample each sector proportionally.
 */
function capMarkers(withCoords) {
  if (withCoords.length <= MAP_MARKER_CAP) return withCoords;

  const bySector = {};
  for (const s of withCoords) {
    const sec = s.sector || "unknown";
    (bySector[sec] = bySector[sec] || []).push(s);
  }

  const total = withCoords.length;
  const sample = (arr, n) => {
    if (arr.length <= n) return arr;
    const step = arr.length / n;
    return Array.from({ length: n }, (_, i) => arr[Math.floor(i * step)]);
  };

  const result = [];
  for (const arr of Object.values(bySector)) {
    const slots = Math.max(1, Math.round((arr.length / total) * MAP_MARKER_CAP));
    result.push(...sample(arr, slots));
  }
  return result;
}

/**
 * Create an enlarged marker with an "i" info badge for the selected school.
 * Visually distinct from regular markers — signals "click me for details."
 */
function createSelectedIcon(school) {
  const status = school.coord_status;
  const color =
    status === "valid" || status === "fixed_swap" || status === "suspect"
      ? sectorColor(school)
      : "#9ca3b8";

  return L.divIcon({
    className: "",
    html: `<div style="position:relative; width:28px; height:28px; cursor:pointer;" title="Click for details">
      <div style="
        position:absolute; top:4px; left:4px;
        width:20px; height:20px;
        background:${color};
        border:3px solid white;
        border-radius:50%;
        box-shadow:0 2px 8px rgba(0,0,0,0.4);
      "></div>
      <div style="
        position:absolute; top:0; left:0;
        width:28px; height:28px;
        border-radius:50%;
        border:2px solid ${color};
        opacity:0.4;
        animation:pulse-ring 2s ease-out infinite;
      "></div>
      <div style="
        position:absolute; top:-2px; right:-2px;
        width:14px; height:14px;
        background:white;
        border:1.5px solid ${color};
        border-radius:50%;
        display:flex; align-items:center; justify-content:center;
        font-size:9px; font-weight:700; color:${color};
        line-height:1; z-index:3;
      ">i</div>
    </div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -16],
  });
}

export default function SchoolMap({ schools, selectedSchool, onOpenDetail, mode = "idle", flyToTrigger = 0 }) {
  // All schools with coords — used for bounds calculation
  const allWithCoords = useMemo(() => {
    return schools.filter((s) => s.latitude && s.longitude);
  }, [schools]);

  // Capped subset for rendering markers
  const markers = useMemo(() => {
    return capMarkers(allWithCoords);
  }, [allWithCoords]);

  return (
    <div className="h-full w-full relative">
    <MapContainer
      center={PH_CENTER}
      zoom={PH_ZOOM}
      className="h-full w-full rounded-xl"
      zoomControl={true}
      scrollWheelZoom={true}
    >
      <LayersControl position="bottomright">
        <LayersControl.BaseLayer checked name="Light">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="OpenStreetMap">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite">
          <TileLayer
            attribution='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <MapViewController selectedSchool={selectedSchool} markers={allWithCoords} mode={mode} flyToTrigger={flyToTrigger} />
      {markers.map((school) => {
        const isSelected = selectedSchool?.school_id === school.school_id;
        return (
          <Marker
            key={school.school_id}
            position={[school.latitude, school.longitude]}
            icon={isSelected ? createSelectedIcon(school) : createIcon(school)}
            zIndexOffset={isSelected ? 1000 : 0}
            eventHandlers={isSelected ? {
              click: (e) => {
                e.originalEvent.stopPropagation();
                onOpenDetail(school);
              },
            } : undefined}
          >
            {!isSelected && (
              <Popup className="custom-popup">
                <div className="p-3">
                  <div className="font-semibold text-sm text-gray-900 leading-tight">
                    {school.school_name || "Unnamed"}
                  </div>
                  <div className="mt-1 text-xs text-gray-500">
                    {school.school_id} &middot;{" "}
                    <span style={{ color: sectorColor(school) }}>
                      {school.sector?.replace("_", " ")}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                    {school.barangay && <div><span className="text-gray-400">Barangay:</span> {school.barangay}</div>}
                    {school.municipality && <div><span className="text-gray-400">City/Muni:</span> {school.municipality}</div>}
                    {school.province && <div><span className="text-gray-400">Province:</span> {school.province}</div>}
                    {school.region && <div><span className="text-gray-400">Region:</span> {school.region}</div>}
                  </div>
                  <div className="mt-2 pt-2 border-t border-gray-100 text-xs text-gray-400 space-y-0.5">
                    <div>{school.latitude?.toFixed(6)}, {school.longitude?.toFixed(6)}</div>
                    {school.coord_source && <div>Source: {school.coord_source}</div>}
                  </div>
                  <button
                    onClick={() => onOpenDetail(school)}
                    className="mt-2 w-full text-center text-xs font-medium text-blue-600 hover:text-blue-800 py-1.5 border-t border-gray-100 transition-colors"
                  >
                    View Details →
                  </button>
                </div>
              </Popup>
            )}
          </Marker>
        );
      })}
    </MapContainer>
    <MapLegend />
    </div>
  );
}
