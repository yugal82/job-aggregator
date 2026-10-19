"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CompanyMark } from "@/components/jobs/company-mark";
import { TierBadges } from "@/components/companies/tier-badges";
import { ApiError } from "@/lib/api/client";
import type { CompanySort } from "@/lib/api/companies";
import { useCompanies } from "@/lib/hooks/use-companies";
import { formatRelative } from "@/lib/time";
import type { Company } from "@/lib/types/job";

function parseSort(value: string | null): CompanySort {
  return value === "jobs" ? "jobs" : "name";
}

export function CompaniesIndex() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sort = parseSort(searchParams.get("sort"));
  const query = useCompanies({ sort });

  useEffect(() => {
    if (!query.isError) return;
    const err = query.error;
    const message =
      err instanceof ApiError
        ? `Failed to load companies — ${err.message}`
        : err instanceof Error
          ? `Failed to load companies — ${err.message}`
          : "Failed to load companies";
    toast.error(message);
  }, [query.isError, query.error]);

  const setSort = (next: CompanySort) => {
    const sp = new URLSearchParams(searchParams.toString());
    if (next === "name") sp.delete("sort");
    else sp.set("sort", next);
    const qs = sp.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <Tabs
          value={sort}
          onValueChange={(v) => setSort(v as CompanySort)}
        >
          <TabsList>
            <TabsTrigger value="name">A–Z</TabsTrigger>
            <TabsTrigger value="jobs">By open jobs</TabsTrigger>
          </TabsList>
        </Tabs>
        {query.data ? (
          <span className="text-xs text-muted-foreground">
            {query.data.total} companies
          </span>
        ) : null}
      </div>

      {query.isPending ? (
        <Grid>
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-md" />
          ))}
        </Grid>
      ) : query.isError ? (
        <ErrorBlock onRetry={() => query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <div className="rounded-md border bg-card px-4 py-10 text-center text-sm text-muted-foreground">
          No companies yet.
        </div>
      ) : (
        <Grid>
          {query.data.items.map((c) => (
            <CompanyCard key={c.slug} company={c} />
          ))}
        </Grid>
      )}
    </div>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {children}
    </div>
  );
}

function CompanyCard({ company }: { company: Company }) {
  const count = company.active_job_count ?? 0;
  return (
    <Link href={`/companies/${company.slug}`} className="group">
      <Card className="h-full rounded-xl shadow-[0_1px_0_rgba(0,0,0,0.02)] transition-all group-hover:border-foreground/30 group-hover:shadow-md">
        <CardContent className="flex items-start gap-3 p-5">
          <CompanyMark company={company} size="md" />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex items-start justify-between gap-2">
              <span className="truncate text-[0.95rem] font-semibold">
                {company.name}
              </span>
              <Badge variant={count > 0 ? "default" : "secondary"}>
                {count} {count === 1 ? "job" : "jobs"}
              </Badge>
            </div>
            {company.tiers && company.tiers.length > 0 ? (
              <TierBadges tiers={company.tiers} limit={2} />
            ) : null}
            <span className="truncate text-xs text-muted-foreground">
              {company.last_synced_at
                ? `Synced ${formatRelative(company.last_synced_at)}`
                : "Never synced"}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function ErrorBlock({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
      Couldn&apos;t load companies.
      <div className="pt-3">
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </div>
  );
}
