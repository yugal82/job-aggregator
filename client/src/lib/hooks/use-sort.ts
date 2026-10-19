"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { JobSort } from "@/lib/api/jobs";

const VALUES: readonly JobSort[] = ["newest", "match", "salary"];

function parseSort(value: string | null): JobSort {
  return (VALUES as readonly string[]).includes(value ?? "")
    ? (value as JobSort)
    : "newest";
}

export function useSort() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sort = useMemo(() => parseSort(searchParams.get("sort")), [searchParams]);

  const setSort = useCallback(
    (next: JobSort) => {
      const sp = new URLSearchParams(searchParams.toString());
      if (next === "newest") sp.delete("sort");
      else sp.set("sort", next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return { sort, setSort };
}
