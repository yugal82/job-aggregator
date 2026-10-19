import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  getCompanyBySlug,
  listCompanies,
  type CompanySort,
} from "@/lib/api/companies";
import type { Company } from "@/lib/types/job";

export function useCompanies(opts: { sort?: CompanySort } = {}) {
  const sort = opts.sort ?? "name";
  return useQuery({
    queryKey: ["companies", sort],
    queryFn: ({ signal }) => listCompanies({ limit: 200, sort }, signal),
    staleTime: 5 * 60_000,
  });
}

export function useCompanyMap(): Map<number, Company> {
  const { data } = useCompanies();
  return useMemo(() => {
    const map = new Map<number, Company>();
    for (const c of data?.items ?? []) map.set(c.id, c);
    return map;
  }, [data]);
}

export function useCompany(slug: string) {
  return useQuery({
    queryKey: ["company", slug],
    queryFn: ({ signal }) => getCompanyBySlug(slug, signal),
    enabled: Boolean(slug),
    staleTime: 60_000,
  });
}
