"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTab } from "@/lib/hooks/use-tab";
import type { JobsTab } from "@/lib/api/jobs";

const LABELS: Record<JobsTab, string> = {
  all: "All",
  recommended: "Recommended",
  new: "New",
};

const ORDER: JobsTab[] = ["all", "recommended", "new"];

export function JobTabs() {
  const { tab, setTab } = useTab();

  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as JobsTab)}>
      <TabsList>
        {ORDER.map((t) => (
          <TabsTrigger key={t} value={t}>
            {LABELS[t]}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
