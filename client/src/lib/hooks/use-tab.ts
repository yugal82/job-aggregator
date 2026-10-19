"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { JobsTab } from "@/lib/api/jobs";

const TABS: readonly JobsTab[] = ["all", "recommended", "new"];

function parseTab(value: string | null): JobsTab {
  if (!value) return "all";
  return (TABS as readonly string[]).includes(value)
    ? (value as JobsTab)
    : "all";
}

export function useTab() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const tab = useMemo(() => parseTab(searchParams.get("tab")), [searchParams]);

  const setTab = useCallback(
    (next: JobsTab) => {
      const sp = new URLSearchParams(searchParams.toString());
      if (next === "all") sp.delete("tab");
      else sp.set("tab", next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return { tab, setTab };
}
