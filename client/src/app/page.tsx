import Link from "next/link";
import { Suspense } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DashboardShell } from "@/components/jobs/dashboard-shell";

export default function DashboardPage() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header className="flex items-end justify-between gap-4 border-b pb-6">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground">
            Discover and track roles from every source you care about.
          </p>
        </div>
        <Link
          href="/companies"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Companies
        </Link>
      </header>

      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <DashboardShell />
      </Suspense>
    </main>
  );
}
