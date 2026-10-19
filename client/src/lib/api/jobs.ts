import { apiFetch } from "./client";
import {
  jobDetailSchema,
  jobSummarySchema,
  pageSchema,
  recommendedJobSchema,
} from "@/lib/types/job";

const jobsPageSchema = pageSchema(jobSummarySchema);
const recommendedPageSchema = pageSchema(recommendedJobSchema);

export type JobSort = "newest" | "match" | "salary";

export type JobsListParams = {
  limit?: number;
  offset?: number;
  company?: string;
  location?: string;
  remote?: boolean;
  posted_after?: string;
  status?: string;
  q?: string;
  sort?: JobSort;
  company_tier?: string;
  source_type?: string;
  seniority?: string;
  level?: string;
};

function buildQuery(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    search.set(k, String(v));
  }
  const q = search.toString();
  return q ? `?${q}` : "";
}

export type JobsTab = "all" | "recommended" | "new";

function endpointForTab(tab: JobsTab): string {
  switch (tab) {
    case "new":
      return "/api/jobs/new";
    case "all":
    default:
      return "/api/jobs";
  }
}

export function listJobs(
  tab: JobsTab,
  params: JobsListParams = {},
  signal?: AbortSignal,
) {
  return apiFetch(`${endpointForTab(tab)}${buildQuery(params)}`, {
    schema: jobsPageSchema,
    signal,
  });
}

export function getJob(id: string, signal?: AbortSignal) {
  return apiFetch(`/api/jobs/${id}`, {
    schema: jobDetailSchema,
    signal,
  });
}

export type RecommendationsParams = {
  limit?: number;
  offset?: number;
  seniority?: string;
};

export function listRecommendations(
  params: RecommendationsParams = {},
  signal?: AbortSignal,
) {
  return apiFetch(`/api/recommendations${buildQuery(params)}`, {
    schema: recommendedPageSchema,
    signal,
  });
}
