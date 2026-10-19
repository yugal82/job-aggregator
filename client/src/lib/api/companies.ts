import { apiFetch } from "./client";
import {
  companyDetailSchema,
  companySchema,
  pageSchema,
} from "@/lib/types/job";

const companiesPageSchema = pageSchema(companySchema);

export type CompanySort = "name" | "jobs";

export function listCompanies(
  {
    limit = 200,
    offset = 0,
    sort = "name",
  }: { limit?: number; offset?: number; sort?: CompanySort } = {},
  signal?: AbortSignal,
) {
  const search = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    sort,
  });
  return apiFetch(`/api/companies?${search.toString()}`, {
    schema: companiesPageSchema,
    signal,
  });
}

export function getCompanyBySlug(slug: string, signal?: AbortSignal) {
  return apiFetch(`/api/companies/by-slug/${encodeURIComponent(slug)}`, {
    schema: companyDetailSchema,
    signal,
  });
}
