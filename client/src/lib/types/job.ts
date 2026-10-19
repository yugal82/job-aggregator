import { z } from "zod";

export const jobStatusSchema = z.enum([
  "DISCOVERED",
  "ACTIVE",
  "UPDATED",
  "CLOSED",
]);

export type JobStatus = z.infer<typeof jobStatusSchema>;

export const companySchema = z.object({
  id: z.number().int(),
  name: z.string(),
  slug: z.string(),
  website: z.string().nullable(),
  careers_url: z.string().nullable(),
  logo_url: z.string().nullable(),
  active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
  active_job_count: z.number().int().optional(),
  last_synced_at: z.string().nullable().optional(),
  tiers: z.array(z.string()).optional(),
});

export const companyTierSchema = z.object({
  key: z.string(),
  label: z.string(),
  description: z.string().optional(),
  company_count: z.number().int(),
  companies: z.array(z.string()).optional(),
});

export type CompanyTier = z.infer<typeof companyTierSchema>;

export const tiersResponseSchema = z.object({
  tiers: z.array(companyTierSchema),
});

export type Company = z.infer<typeof companySchema>;

export const companyDetailSchema = companySchema.extend({
  active_job_count: z.number().int(),
  last_synced_at: z.string().nullable(),
});

export type CompanyDetail = z.infer<typeof companyDetailSchema>;

export const matchBucketSchema = z.enum(["strong", "gap", "neutral"]);

export type MatchBucket = z.infer<typeof matchBucketSchema>;

export const matchFacetSchema = z.object({
  key: z.string(),
  bucket: matchBucketSchema,
  label: z.string(),
  detail: z.unknown().nullable().optional(),
});

export type MatchFacet = z.infer<typeof matchFacetSchema>;

export const matchExplanationSchema = z.object({
  facets: z.array(matchFacetSchema),
});

export type MatchExplanation = z.infer<typeof matchExplanationSchema>;

export const jobSummarySchema = z.object({
  id: z.string().uuid(),
  company_id: z.number().int(),
  canonical_title: z.string(),
  employment_type: z.string().nullable(),
  workplace_type: z.string().nullable(),
  department: z.string().nullable(),
  team: z.string().nullable(),
  posted_at: z.string().nullable(),
  first_seen_at: z.string(),
  application_url: z.string().nullable(),
  canonical_url: z.string().nullable(),
  status: jobStatusSchema,
  level: z.string().nullable().optional(),
  match_strong_count: z.number().int().nullable().optional(),
  match_gap_count: z.number().int().nullable().optional(),
});

export type JobSummary = z.infer<typeof jobSummarySchema>;

export const jobLocationSchema = z.object({
  id: z.number().int(),
  city: z.string().nullable(),
  state: z.string().nullable(),
  country: z.string().nullable(),
  postal_code: z.string().nullable(),
  remote_allowed: z.boolean(),
  hybrid_allowed: z.boolean(),
  location_text: z.string().nullable(),
});

export type JobLocation = z.infer<typeof jobLocationSchema>;

export const sourceSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  type: z.enum(["official", "ats", "board"]),
  provider: z.string(),
  base_url: z.string().nullable(),
  active: z.boolean(),
});

export type Source = z.infer<typeof sourceSchema>;

export const jobSourceLinkSchema = z.object({
  id: z.number().int(),
  source_url: z.string().nullable(),
  source_application_url: z.string().nullable(),
  source_title: z.string().nullable(),
  source_location: z.string().nullable(),
  source_posted_at: z.string().nullable(),
  is_active: z.boolean(),
  source: sourceSchema,
});

export type JobSourceLink = z.infer<typeof jobSourceLinkSchema>;

export const jobDetailSchema = jobSummarySchema.extend({
  description: z.string().nullable(),
  salary_min: z.union([z.string(), z.number()]).nullable(),
  salary_max: z.union([z.string(), z.number()]).nullable(),
  salary_currency: z.string().nullable(),
  last_seen_at: z.string(),
  closed_at: z.string().nullable(),
  content_hash: z.string().nullable(),
  requisition_id: z.string().nullable(),
  company: companySchema.nullable().optional(),
  locations: z.array(jobLocationSchema).default([]),
  sources: z.array(jobSourceLinkSchema).default([]),
  match: matchExplanationSchema.nullable().optional(),
});

export type JobDetail = z.infer<typeof jobDetailSchema>;

export const recommendedJobSchema = jobSummarySchema.extend({
  match: matchExplanationSchema,
});

export type RecommendedJob = z.infer<typeof recommendedJobSchema>;

export function pageSchema<T extends z.ZodTypeAny>(itemSchema: T) {
  return z.object({
    items: z.array(itemSchema),
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
  });
}

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
