"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import {
  EMPTY_FILTERS,
  parseFilters,
  serializeFilters,
  type JobFilters,
} from "@/lib/filters/schema";

export function useFilters() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters = useMemo(
    () => parseFilters(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );

  const push = useCallback(
    (next: JobFilters) => {
      const sp = serializeFilters(next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const setFilters = useCallback(
    (updater: JobFilters | ((prev: JobFilters) => JobFilters)) => {
      const next =
        typeof updater === "function"
          ? (updater as (p: JobFilters) => JobFilters)(filters)
          : updater;
      push(next);
    },
    [filters, push],
  );

  const clearFilters = useCallback(() => {
    push(EMPTY_FILTERS);
  }, [push]);

  return { filters, setFilters, clearFilters };
}
