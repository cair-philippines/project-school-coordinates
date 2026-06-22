import {
  X,
  MapPin,
  School,
  Eye,
  Users,
  GraduationCap,
  Info,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  BookOpen,
  Wrench,
  Building2,
} from "lucide-react";

function Badge({ children, variant = "default" }) {
  const styles = {
    default: "bg-gray-100 text-gray-700",
    blue: "bg-blue-50 text-blue-700",
    pink: "bg-pink-50 text-pink-700",
    green: "bg-green-50 text-green-700",
    amber: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
    violet: "bg-violet-50 text-violet-700",
    orange: "bg-orange-50 text-orange-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${styles[variant] || styles.default}`}>
      {children}
    </span>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, muted }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex justify-between items-start text-sm">
      <span className="text-[var(--muted-foreground)] text-xs shrink-0">{label}</span>
      <span className={`text-right ml-2 text-xs ${muted ? "text-[var(--muted-foreground)]" : "font-medium"}`}>
        {value}
      </span>
    </div>
  );
}

const SOURCE_LABELS = {
  monitoring_validated: "Monitoring (university-validated)",
  osmapaaralan: "OSMapaaralan (OSM community-mapped)",
  nsbi_2324: "NSBI SY 2023-2024 (official inventory)",
  geolocation_deped: "Geolocation DepEd (internal office)",
  tosf_self_reported: "TOSF (self-reported via Google Forms)",
};

const SOURCE_TRUST = {
  monitoring_validated: { level: "Highest", variant: "green", desc: "Validated by university team against satellite imagery and social media" },
  osmapaaralan: { level: "High", variant: "green", desc: "Community-mapped and reviewed through OSM's rigorous mapping process" },
  nsbi_2324: { level: "Moderate", variant: "amber", desc: "Official DepEd system, but dated and not field-validated" },
  geolocation_deped: { level: "Low", variant: "amber", desc: "Internal office revision, lowest priority among public sources" },
  tosf_self_reported: { level: "Variable", variant: "amber", desc: "Self-reported by school — may be inaccurate, swapped, or approximate" },
};

const MONITORING_SUB_LABELS = {
  OSMapaaralan: "Validator chose OSMapaaralan coordinates as correct",
  NSBI: "Validator chose NSBI coordinates as correct",
  "New coordinates": "Validator found new coordinates from external sources",
};

function sectorLabel(sector) {
  const labels = {
    public: "DepEd Public",
    private: "DepEd Private",
    ched_public: "CHED Public",
    ched_private: "CHED Private",
    tesda: "TESDA",
  };
  return labels[sector] || sector;
}

function sectorBadgeVariant(sector) {
  if (sector === "public") return "green";
  if (sector === "private") return "blue";
  if (sector === "ched_public" || sector === "ched_private") return "violet";
  if (sector === "tesda") return "orange";
  return "default";
}

function TagList({ items }) {
  if (!items || items.length === 0) return (
    <div className="text-xs text-[var(--muted-foreground)]">None listed</div>
  );
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <Badge key={item} variant="default">{item}</Badge>
      ))}
    </div>
  );
}

export default function SchoolDetail({ school, onClose }) {
  if (!school) return null;

  const isDepEd = school.sector === "public" || school.sector === "private";
  const isPublic = school.sector === "public";
  const isCHED = school.sector === "ched_public" || school.sector === "ched_private";
  const isTESDA = school.sector === "tesda";
  const hasCoords = school.latitude != null && school.longitude != null;
  const trust = SOURCE_TRUST[school.coord_source] || null;

  return (
    <div className="h-full w-[350px] bg-[var(--card)] border border-[var(--border)] rounded-xl shadow-xl flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 p-4 border-b border-[var(--border)] bg-gradient-to-b from-[var(--accent)] to-[var(--card)]">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge variant={sectorBadgeVariant(school.sector)}>
                <School className="h-3 w-3" />
                {sectorLabel(school.sector)}
              </Badge>
              {isDepEd && (
                school.enrollment_status === "active" ? (
                  <Badge variant="green">
                    <CheckCircle2 className="h-3 w-3" />active
                  </Badge>
                ) : (
                  <Badge variant="amber">
                    <AlertCircle className="h-3 w-3" />no enrollment
                  </Badge>
                )
              )}
            </div>
            <h2 className="font-semibold text-base leading-tight">
              {school.school_name || "Unnamed"}
            </h2>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">
              ID: {school.school_id}
            </div>
            {isCHED && school.hei_ownership && (
              <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                {school.hei_ownership}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-1 rounded-lg hover:bg-[var(--secondary)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Location */}
        <Section title="Location" icon={MapPin}>
          <div className="space-y-1">
            {isTESDA && school.address && (
              <Row label="Address" value={school.address} />
            )}
            <Row label="Barangay" value={school.barangay} />
            <Row label="Municipality" value={school.municipality} />
            <Row label="Province" value={school.province} />
            <Row label="Region" value={school.region} />
            {hasCoords && (
              <Row
                label="Coordinates"
                value={`${school.latitude.toFixed(6)}, ${school.longitude.toFixed(6)}`}
              />
            )}
            {school.location_source && (
              <Row label="Location data from" value={school.location_source} muted />
            )}
          </div>
        </Section>

        {/* Coordinate Lineage — DepEd: full detail; CHED/TESDA: simplified */}
        <Section title="Coordinate Lineage" icon={Eye}>
          {hasCoords ? (
            isDepEd ? (
              <div className="space-y-2">
                <div className="rounded-lg border border-[var(--border)] p-3 space-y-2">
                  <div className="text-xs font-medium">
                    {SOURCE_LABELS[school.coord_source] || school.coord_source || "Unknown source"}
                  </div>
                  {trust && (
                    <div className="flex items-center gap-2">
                      <Badge variant={trust.variant}>Trust: {trust.level}</Badge>
                    </div>
                  )}
                  {trust && (
                    <div className="text-[11px] text-[var(--muted-foreground)]">
                      {trust.desc}
                    </div>
                  )}
                  {school.monitoring_chosen_source && (
                    <div className="mt-2 pt-2 border-t border-[var(--border)]">
                      <div className="text-[11px] text-[var(--muted-foreground)] flex items-center gap-1">
                        <ArrowRight className="h-3 w-3" />
                        {MONITORING_SUB_LABELS[school.monitoring_chosen_source] ||
                          `Validator chose: ${school.monitoring_chosen_source}`}
                      </div>
                    </div>
                  )}
                </div>
                {school.sources_available && (
                  <div>
                    <div className="text-[11px] text-[var(--muted-foreground)] mb-1">
                      Available in {school.sources_available.split(",").length} source(s):
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {school.sources_available.split(",").map((src) => (
                        <Badge
                          key={src}
                          variant={src === school.coord_source ? "green" : "default"}
                        >
                          {src === school.coord_source && <CheckCircle2 className="h-3 w-3" />}
                          {src.trim()}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-[var(--border)] p-3">
                <div className="text-xs font-medium">
                  {isCHED ? "CHED official data" : "TESDA official data"}
                </div>
                <div className="text-[11px] text-[var(--muted-foreground)] mt-1">
                  Coordinates from the {isCHED ? "CHED" : "TESDA"} source file.
                </div>
              </div>
            )
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1">
              <div className="text-xs font-medium text-amber-800">No coordinates available</div>
              <div className="text-[11px] text-amber-700">
                {isDepEd
                  ? (school.coord_rejection_reason === "no_submission"
                    ? "This school did not submit coordinates in the TOSF data collection."
                    : school.coord_rejection_reason === "not_in_lis"
                    ? "This school was found in enrollment data but is not in the LIS master list."
                    : school.coord_rejection_reason === "invalid"
                    ? "Submitted coordinates were invalid (non-numeric, out of range, or zero)."
                    : school.coord_rejection_reason === "out_of_bounds"
                    ? "Submitted coordinates fell outside the Philippines bounding box."
                    : "No coordinate source has data for this school.")
                  : `No valid coordinates in the ${isCHED ? "CHED" : "TESDA"} source file.`
                }
              </div>
            </div>
          )}

          {/* Coord status warnings (DepEd only — these suspect categories don't apply to CHED/TESDA) */}
          {isDepEd && school.coord_status === "suspect" && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 space-y-1">
              <div className="text-xs font-medium text-red-800">Suspect coordinates</div>
              <div className="text-[11px] text-red-700">
                {school.coord_rejection_reason === "placeholder_default"
                  ? "This coordinate matches a known TOSF system default value. The school almost certainly did not enter its actual location."
                  : school.coord_rejection_reason === "coordinate_cluster"
                  ? "This coordinate is shared by multiple schools across different municipalities — likely a placeholder or system default."
                  : school.coord_rejection_reason === "round_coordinates"
                  ? "Both latitude and longitude have very low precision (fewer than 3 decimal places). This appears to be a rough estimate, not a GPS reading."
                  : school.coord_rejection_reason === "outside_all_polygons"
                  ? "This coordinate falls outside all known land polygons — it may be over water or in an unmapped area. Likely a data entry error (transposed digits or wrong decimal)."
                  : school.coord_rejection_reason === "wrong_municipality"
                  ? "This coordinate falls in a different municipality than the school's declared location. The coordinate or the administrative assignment may be incorrect."
                  : `Flagged as suspect: ${school.coord_rejection_reason || "unknown reason"}`}
              </div>
            </div>
          )}
          {isDepEd && school.coord_status === "fixed_swap" && (
            <div className="text-[11px] text-[var(--muted-foreground)]">
              <b>Note:</b> Latitude and longitude were swapped in the original submission and auto-corrected.
            </div>
          )}
        </Section>

        {/* CHED — Academic Offerings */}
        {isCHED && (
          <Section title="Academic Offerings" icon={BookOpen}>
            <TagList items={school.discipline_groups} />
          </Section>
        )}

        {/* TESDA — Institution Details + Program Sectors */}
        {isTESDA && (
          <>
            <Section title="Institution Details" icon={Building2}>
              <div className="space-y-1">
                <Row label="Type" value={school.type_of_institution} />
                <Row label="Classification" value={school.classification} />
                <Row label="Role" value={school.institution_classification} />
              </div>
            </Section>
            <Section title="Program Sectors" icon={Wrench}>
              <TagList items={school.program_sectors} />
            </Section>
          </>
        )}

        {/* GASTPE (DepEd private only) */}
        {!isPublic && isDepEd && (
          <Section title="GASTPE Participation" icon={GraduationCap}>
            <div className="space-y-1">
              <Row label="ESC" value={school.esc_participating === 1 ? "Participating" : "No"} />
              <Row label="SHS VP" value={school.shsvp_participating === 1 ? "Participating" : "No"} />
              <Row label="JDVP" value={school.jdvp_participating === 1 ? "Participating" : "No"} />
            </div>
          </Section>
        )}

        {/* Enrollment (DepEd only) */}
        {isDepEd && (
          <Section title="Enrollment Status" icon={Users}>
            <div className="text-sm">
              {school.enrollment_status === "active" ? (
                <span className="text-green-700">Has reported enrollment in SY 2024-2025</span>
              ) : (
                <span className="text-amber-700">No reported enrollment in SY 2024-2025</span>
              )}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}
