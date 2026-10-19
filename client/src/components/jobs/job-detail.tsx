"use client";

import Link from "next/link";
import { useEffect } from "react";
import { toast } from "sonner";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useJob } from "@/lib/hooks/use-job";
import { sanitizeDescription } from "@/lib/sanitize";
import { formatRelative } from "@/lib/time";
import type {
  JobDetail as JobDetailType,
  JobLocation,
  JobSourceLink,
} from "@/lib/types/job";
import { CompanyMark } from "./company-mark";
import { JobActions } from "./job-actions";
import { MatchExplanation } from "./match-explanation";

function formatLocation(loc: JobLocation): string {
  const parts = [loc.city, loc.state, loc.country].filter(Boolean);
  if (parts.length) return parts.join(", ");
  if (loc.location_text) return loc.location_text;
  if (loc.remote_allowed) return "Remote";
  return "—";
}

function formatSalary(job: JobDetailType): string | null {
  if (!job.salary_min && !job.salary_max) return null;
  const currency = job.salary_currency ?? "USD";
  const fmt = (v: string | number | null) =>
    v == null ? null : new Intl.NumberFormat("en-US").format(Number(v));
  const min = fmt(job.salary_min);
  const max = fmt(job.salary_max);
  if (min && max) return `${currency} ${min}–${max}`;
  return `${currency} ${min ?? max}`;
}

function hostOf(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function JobDetailView({ id }: { id: string }) {
  const query = useJob(id);

  useEffect(() => {
    if (!query.isError) return;
    const err = query.error;
    const message =
      err instanceof ApiError
        ? err.status === 404
          ? "Job not found"
          : `Failed to load job — ${err.message}`
        : err instanceof Error
          ? `Failed to load job — ${err.message}`
          : "Failed to load job";
    toast.error(message);
  }, [query.isError, query.error]);

  if (query.isPending) return <DetailSkeleton />;

  if (query.isError) {
    const notFound =
      query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
        {notFound ? "Job not found." : "Couldn't load this job."}
        <div className="pt-3 flex gap-2">
          {!notFound ? (
            <Button size="sm" variant="outline" onClick={() => query.refetch()}>
              Retry
            </Button>
          ) : null}
          <Link
            href="/"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Back to jobs
          </Link>
        </div>
      </div>
    );
  }

  const job = query.data;
  const posted = job.posted_at ?? job.first_seen_at;
  const salary = formatSalary(job);

  return (
    <article className="flex flex-col gap-6">
      <JobHeader job={job} posted={posted} />

      {(job.employment_type ||
        job.workplace_type ||
        salary ||
        job.department ||
        job.team) ? (
        <section className="flex flex-wrap gap-2">
          {job.employment_type ? (
            <Badge variant="secondary">{job.employment_type}</Badge>
          ) : null}
          {job.workplace_type ? (
            <Badge variant="secondary">{job.workplace_type}</Badge>
          ) : null}
          {salary ? <Badge variant="secondary">{salary}</Badge> : null}
          {job.department ? (
            <Badge variant="secondary">{job.department}</Badge>
          ) : null}
          {job.team ? <Badge variant="secondary">{job.team}</Badge> : null}
        </section>
      ) : null}

      {job.match ? <MatchExplanation match={job.match} /> : null}

      <DescriptionCard description={job.description} />

      <SourcesCard sources={job.sources} />
    </article>
  );
}

function JobHeader({
  job,
  posted,
}: {
  job: JobDetailType;
  posted: string;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 gap-4">
        <CompanyMark company={job.company ?? null} size="lg" />
        <div className="flex min-w-0 flex-col gap-1">
          {job.company ? (
            <Link
              href={`/companies/${job.company.slug}`}
              className="text-sm font-medium text-muted-foreground hover:text-foreground hover:underline"
            >
              {job.company.name}
            </Link>
          ) : (
            <span className="text-sm font-medium text-muted-foreground">—</span>
          )}
          <h1 className="text-2xl font-semibold tracking-tight">
            {job.canonical_title}
          </h1>
          <p className="text-sm text-muted-foreground">
            {job.locations.length
              ? job.locations.map(formatLocation).join(" · ")
              : "No location listed"}
            {" · Posted "}
            {formatRelative(posted)}
          </p>
        </div>
      </div>
      <div className="flex flex-col items-end gap-2">
        {job.application_url ? (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants()}
          >
            Apply ↗
          </a>
        ) : null}
        <JobActions jobId={job.id} state={job.user_state} variant="detail" />
      </div>
    </header>
  );
}

function DescriptionCard({ description }: { description: string | null }) {
  if (!description) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Description</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          No description provided.
        </CardContent>
      </Card>
    );
  }

  const sanitized = sanitizeDescription(description);

  return (
    <Card>
      <CardContent className="p-2">
        <Accordion>
          <AccordionItem value="description" className="border-b-0">
            <AccordionTrigger className="px-3 text-base font-semibold">
              Description
            </AccordionTrigger>
            <AccordionContent className="px-3">
              {sanitized.kind === "html" ? (
                <div
                  className="text-sm leading-relaxed [&>*+*]:mt-3 [&_a]:text-primary [&_a]:underline [&_ul]:ml-5 [&_ul]:list-disc [&_ol]:ml-5 [&_ol]:list-decimal [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_strong]:font-semibold"
                  dangerouslySetInnerHTML={{ __html: sanitized.html }}
                />
              ) : (
                <div className="text-sm whitespace-pre-wrap leading-relaxed">
                  {sanitized.text}
                </div>
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}

function SourcesCard({ sources }: { sources: JobSourceLink[] }) {
  if (sources.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Also on</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {sources.map((link, i) => {
          const url = link.source_url ?? link.source_application_url;
          return (
            <div key={link.id} className="flex flex-col gap-2">
              {i > 0 ? <Separator /> : null}
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium">{link.source.name}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {hostOf(url)}
                  </span>
                </div>
                {url ? (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    Open ↗
                  </a>
                ) : (
                  <span className="text-xs text-muted-foreground">no link</span>
                )}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex gap-4">
        <Skeleton className="size-14 rounded-md" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-24" />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Description</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </CardContent>
      </Card>
    </div>
  );
}
