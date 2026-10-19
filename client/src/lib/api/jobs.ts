import { z } from "zod";
import { apiFetch } from "./client";
import {
  jobDetailSchema,
  jobSummarySchema,
  pageSchema,
  recommendedJobSchema,
  userJobStateSchema,
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

export type JobsTab =
  | "all"
  | "recommended"
  | "new"
  | "saved"
  | "applied"
  | "dismissed";

function endpointForTab(tab: JobsTab): string {
  switch (tab) {
    case "new":
      return "/api/jobs/new";
    case "saved":
      return "/api/jobs/saved";
    case "applied":
      return "/api/jobs/applied";
    case "dismissed":
      return "/api/jobs/dismissed";
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

const jobUserStateResponseSchema = z.object({
  user_id: z.number().int(),
  job_id: z.string().uuid(),
  state: userJobStateSchema,
  created_at: z.string(),
  updated_at: z.string(),
});

export type JobUserStateResponse = z.infer<typeof jobUserStateResponseSchema>;

export function saveJob(id: string) {
  return apiFetch(`/api/jobs/${id}/save`, {
    schema: jobUserStateResponseSchema,
    method: "POST",
  });
}

export function applyJob(id: string) {
  return apiFetch(`/api/jobs/${id}/apply`, {
    schema: jobUserStateResponseSchema,
    method: "POST",
  });
}

export function dismissJob(id: string) {
  return apiFetch(`/api/jobs/${id}/dismiss`, {
    schema: jobUserStateResponseSchema,
    method: "POST",
  });
}
