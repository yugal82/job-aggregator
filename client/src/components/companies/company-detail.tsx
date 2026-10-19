"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TierBadges } from "@/components/companies/tier-badges";
import { CompanyMark } from "@/components/jobs/company-mark";
import { JobCard } from "@/components/jobs/job-card";
import { JobCardSkeleton } from "@/components/jobs/job-card-skeleton";
import { SearchInput } from "@/components/jobs/search-input";
import { ApiError } from "@/lib/api/client";
import { EMPTY_FILTERS, filtersToApiParams } from "@/lib/filters/schema";
import { useCompany } from "@/lib/hooks/use-companies";
import { useFilters } from "@/lib/hooks/use-filters";
import { useJobs } from "@/lib/hooks/use-jobs";
import { formatRelative } from "@/lib/time";
import type { CompanyDetail as CompanyDetailType } from "@/lib/types/job";

const PAGE_SIZE = 20;

export function CompanyDetailView({ slug }: { slug: string }) {
  const query = useCompany(slug);

  useEffect(() => {
    if (!query.isError) return;
    const err = query.error;
    if (err instanceof ApiError && err.status === 404) return;
    const message =
      err instanceof ApiError
        ? `Failed to load company — ${err.message}`
        : err instanceof Error
          ? `Failed to load company — ${err.message}`
          : "Failed to load company";
    toast.error(message);
  }, [query.isError, query.error]);

  if (query.isPending) return <DetailSkeleton />;

  if (query.isError) {
    const notFound =
      query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
        {notFound ? "Company not found." : "Couldn't load this company."}
        <div className="flex gap-2 pt-3">
          {!notFound ? (
            <Button size="sm" variant="outline" onClick={() => query.refetch()}>
              Retry
            </Button>
          ) : null}
          <Link
            href="/companies"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Back to companies
          </Link>
        </div>
      </div>
    );
  }

  const company = query.data;

  return (
    <div className="flex flex-col gap-6">
      <CompanyHeader company={company} />
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Open roles</h2>
          <SearchInput />
        </div>
        <CompanyJobList slug={slug} company={company} />
      </section>
    </div>
  );
}

function CompanyHeader({ company }: { company: CompanyDetailType }) {
  const synced = company.last_synced_at
    ? `Synced ${formatRelative(company.last_synced_at)}`
    : "Never synced";

  return (
    <Card className="rounded-xl shadow-[0_1px_0_rgba(0,0,0,0.02)]">
      <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-start">
        <CompanyMark company={company} size="lg" />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {company.name}
            </h1>
            {!company.active ? (
              <Badge variant="secondary">inactive</Badge>
            ) : null}
          </div>
          {company.tiers && company.tiers.length > 0 ? (
            <TierBadges tiers={company.tiers} />
          ) : null}
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <Badge variant={company.active_job_count > 0 ? "default" : "secondary"}>
              {company.active_job_count}{" "}
              {company.active_job_count === 1 ? "open role" : "open roles"}
            </Badge>
            <span>·</span>
            <span>{synced}</span>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {company.careers_url ? (
              <a
                href={company.careers_url}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                Careers page ↗
              </a>
            ) : null}
            {company.website ? (
              <a
                href={company.website}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Website ↗
              </a>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CompanyJobList({
  slug,
  company,
}: {
  slug: string;
  company: CompanyDetailType;
}) {
  const { filters, setFilters } = useFilters();
  const [offset, setOffset] = useState(0);

  const resetKey = JSON.stringify({ slug, filters });
  const prevKey = useRef(resetKey);
  useEffect(() => {
    if (prevKey.current !== resetKey) {
      prevKey.current = resetKey;
      setOffset(0);
    }
  }, [resetKey]);

  const query = useJobs("all", {
    limit: PAGE_SIZE,
    offset,
    ...filtersToApiParams(filters),
    company: slug,
  });

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
        {Array.from({ length: 4 }).map((_, i) => (
          <JobCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
        Couldn&apos;t load this company&apos;s jobs.
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
    const hasSearch =
      JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
    const defaultHidingRoles =
      !hasSearch &&
      filters.seniority === "default" &&
      company.active_job_count > 0;
    return (
      <div className="rounded-md border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
        {defaultHidingRoles ? (
          <>
            No early-career roles here right now. {company.name} has{" "}
            {company.active_job_count}{" "}
            {company.active_job_count === 1 ? "role" : "roles"} at other levels.
            <div className="pt-3">
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setFilters((prev) => ({ ...prev, seniority: "any" }))
                }
              >
                Show all levels
              </Button>
            </div>
          </>
        ) : hasSearch ? (
          "No roles match your search here."
        ) : (
          "No open roles right now."
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
          <JobCard key={job.id} job={job} company={company} />
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

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardContent className="flex gap-4 p-5">
          <Skeleton className="size-14 rounded-md" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-8 w-40" />
          </div>
        </CardContent>
      </Card>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <JobCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
