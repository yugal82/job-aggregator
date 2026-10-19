import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { formatRelative } from "@/lib/time";
import type { Company, JobSummary } from "@/lib/types/job";
import { CompanyMark } from "./company-mark";
import { MatchPreview } from "./match-preview";

type JobCardProps = {
  job: JobSummary;
  company: Company | undefined;
};

export function JobCard({ job, company }: JobCardProps) {
  const posted = job.posted_at ?? job.first_seen_at;
  const applyUrl = job.application_url ?? job.canonical_url;
  const hasInteractive =
    job.level ||
    job.employment_type ||
    job.workplace_type ||
    job.status !== "ACTIVE" ||
    (job.match_strong_count ?? 0) > 0 ||
    (job.match_gap_count ?? 0) > 0;

  return (
    <article className="group relative flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-[0_1px_0_rgba(0,0,0,0.02)] transition hover:border-foreground/30 hover:shadow-md focus-within:border-foreground/30 focus-within:shadow-md">
      <Link
        href={`/jobs/${job.id}`}
        aria-label={`${job.canonical_title}${company ? ` at ${company.name}` : ""}`}
        className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />

      <div className="relative z-10 flex items-start gap-3">
        <CompanyMark company={company} size="md" />
        <div className="min-w-0 flex-1">
          {company ? (
            <Link
              href={`/companies/${company.slug}`}
              className="relative z-10 inline-block text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
            >
              {company.name}
            </Link>
          ) : (
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              —
            </span>
          )}
          <h3
            className="mt-1 line-clamp-2 text-[0.95rem] font-semibold leading-snug tracking-tight text-foreground"
            title={job.canonical_title}
          >
            {job.canonical_title}
          </h3>
        </div>
      </div>

      {hasInteractive ? (
        <div className="relative z-0 flex flex-wrap gap-1.5">
          <MatchPreview
            strong={job.match_strong_count}
            gap={job.match_gap_count}
          />
          {job.level ? <Badge variant="outline">{job.level}</Badge> : null}
          {job.employment_type ? (
            <Badge variant="secondary">{job.employment_type}</Badge>
          ) : null}
          {job.workplace_type ? (
            <Badge variant="secondary">{job.workplace_type}</Badge>
          ) : null}
          {job.status === "CLOSED" ? (
            <Badge variant="destructive">closed</Badge>
          ) : null}
        </div>
      ) : null}

      <div className="relative z-10 mt-auto flex items-center justify-between gap-3 pt-1">
        <span className="text-xs text-muted-foreground">
          Posted {formatRelative(posted)}
        </span>
        {applyUrl ? (
          <a
            href={applyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            Apply ↗
          </a>
        ) : null}
      </div>
    </article>
  );
}
