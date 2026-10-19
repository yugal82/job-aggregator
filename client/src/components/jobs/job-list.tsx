"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { EMPTY_FILTERS, filtersToApiParams } from "@/lib/filters/schema";
import { useCompanyMap } from "@/lib/hooks/use-companies";
import { useFilters } from "@/lib/hooks/use-filters";
import { useJobs } from "@/lib/hooks/use-jobs";
import { useRecommendations } from "@/lib/hooks/use-recommendations";
import { useSort } from "@/lib/hooks/use-sort";
import { useTab } from "@/lib/hooks/use-tab";
import { JobCard } from "./job-card";
import { JobCardSkeleton } from "./job-card-skeleton";

const PAGE_SIZE = 20;

export function JobList() {
  const { tab } = useTab();
  const { filters, clearFilters } = useFilters();
  const { sort } = useSort();
  const [offset, setOffset] = useState(0);
  const companyMap = useCompanyMap();

  const isRecommended = tab === "recommended";
  const applyFilters = tab === "all";
  const effectiveSort = tab === "all" ? sort : "newest";
  const seniorityParam =
    filters.seniority === "default" ? undefined : filters.seniority;
  const effectiveFilters = applyFilters ? filters : EMPTY_FILTERS;
  const resetKey = JSON.stringify({
    tab,
    effectiveFilters,
    effectiveSort,
    seniorityParam,
  });
  const prevKey = useRef(resetKey);
  useEffect(() => {
    if (prevKey.current !== resetKey) {
      prevKey.current = resetKey;
      setOffset(0);
    }
  }, [resetKey]);

  const jobsQuery = useJobs(
    isRecommended ? "all" : tab,
    {
      limit: PAGE_SIZE,
      offset,
      ...(applyFilters ? filtersToApiParams(filters) : {}),
      ...(tab === "all" ? { sort } : {}),
    },
    { enabled: !isRecommended },
  );

  const recsQuery = useRecommendations(
    { limit: PAGE_SIZE, offset, seniority: seniorityParam },
    { enabled: isRecommended },
  );

  const query = isRecommended ? recsQuery : jobsQuery;

  useEffect(() => {
    if (!query.isError) return;
    const err = query.error;
    const message =
      err instanceof ApiError
        ? `Failed to load jobs — ${err.message}`
        : err instanceof Error
          ? `Failed to load jobs — ${err.message}`
          : "Failed to load jobs";
    toast.error(message);
  }, [query.isError, query.error]);

  if (query.isPending) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <JobCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
        Couldn&apos;t load jobs. Check that the backend is reachable at{" "}
        <code>{process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}</code>.
        <div className="pt-3">
          <Button size="sm" variant="outline" onClick={() => query.refetch()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const { items, total } = query.data;

  if (items.length === 0) {
    const hasFilters =
      applyFilters &&
      JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
    const emptyCopy = emptyCopyForTab(tab);
    return (
      <div className="rounded-md border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
        {hasFilters ? (
          <>
            No jobs match these filters.
            <div className="pt-3">
              <Button size="sm" variant="outline" onClick={clearFilters}>
                Clear filters
              </Button>
            </div>
          </>
        ) : (
          emptyCopy
        )}
      </div>
    );
  }

  const start = offset + 1;
  const end = offset + items.length;
  const hasPrev = offset > 0;
  const hasNext = offset + items.length < total;

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {items.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            company={companyMap.get(job.company_id)}
          />
        ))}
      </div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          {start}–{end} of {total}
        </span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!hasPrev || query.isFetching}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={!hasNext || query.isFetching}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

function emptyCopyForTab(tab: string): string {
  switch (tab) {
    case "recommended":
      return "No recommendations yet. Set up your profile to see tailored matches.";
    case "saved":
      return "No saved jobs yet. Click Save on any job to collect it here.";
    case "applied":
      return "No applied jobs yet. Mark a job as applied and it will land here.";
    case "dismissed":
      return "No dismissed jobs.";
    case "new":
      return "No new jobs in the last 24 hours.";
    default:
      return "No jobs yet. Run the backend seed or trigger a sync to see results here.";
  }
}
