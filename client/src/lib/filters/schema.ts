export type SourceType = "official" | "ats" | "board";

export type Seniority = "default" | "internship" | "any";

export type JobFilters = {
  q: string;
  companies: string[];
  locations: string[];
  remote: boolean;
  posted_after: string | null;
  tier: string | null;
  source_types: SourceType[];
  seniority: Seniority;
};

export const EMPTY_FILTERS: JobFilters = {
  q: "",
  companies: [],
  locations: [],
  remote: false,
  posted_after: null,
  tier: null,
  source_types: [],
  seniority: "default",
};

const VALID_SOURCE_TYPES: readonly SourceType[] = ["official", "ats", "board"];

function parseCsv(value: string | null): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseSeniority(value: string | null): Seniority {
  if (value === "any") return "any";
  if (value === "internship") return "internship";
  return "default";
}

function parseSourceTypes(value: string | null): SourceType[] {
  const parsed = parseCsv(value).map((s) => s.toLowerCase());
  return parsed.filter((v): v is SourceType =>
    (VALID_SOURCE_TYPES as readonly string[]).includes(v),
  );
}

export function parseFilters(sp: URLSearchParams): JobFilters {
  return {
    q: sp.get("q")?.trim() ?? "",
    companies: parseCsv(sp.get("company")),
    locations: parseCsv(sp.get("location")),
    remote: sp.get("remote") === "1",
    posted_after: sp.get("posted_after") ?? null,
    tier: sp.get("tier") || null,
    source_types: parseSourceTypes(sp.get("source_type")),
    seniority: parseSeniority(sp.get("seniority")),
  };
}

export function serializeFilters(f: JobFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set("q", f.q);
  if (f.companies.length) sp.set("company", f.companies.join(","));
  if (f.locations.length) sp.set("location", f.locations.join(","));
  if (f.remote) sp.set("remote", "1");
  if (f.posted_after) sp.set("posted_after", f.posted_after);
  if (f.tier) sp.set("tier", f.tier);
  if (f.source_types.length) sp.set("source_type", f.source_types.join(","));
  if (f.seniority !== "default") sp.set("seniority", f.seniority);
  return sp;
}

export function activeFilterCount(f: JobFilters): number {
  let n = 0;
  if (f.q) n += 1;
  if (f.companies.length) n += 1;
  if (f.locations.length) n += 1;
  if (f.remote) n += 1;
  if (f.posted_after) n += 1;
  if (f.tier) n += 1;
  if (f.source_types.length) n += 1;
  if (f.seniority !== "default") n += 1;
  return n;
}

export function todayIsoDate(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function filtersToApiParams(f: JobFilters) {
  const posted_after_iso = f.posted_after
    ? new Date(`${f.posted_after}T00:00:00`).toISOString()
    : undefined;
  return {
    q: f.q || undefined,
    company: f.companies.length ? f.companies.join(",") : undefined,
    location: f.locations.length ? f.locations.join(",") : undefined,
    remote: f.remote || undefined,
    posted_after: posted_after_iso,
    company_tier: f.tier || undefined,
    source_type: f.source_types.length ? f.source_types.join(",") : undefined,
    seniority: f.seniority === "default" ? undefined : f.seniority,
  };
}
