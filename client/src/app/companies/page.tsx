import Link from "next/link";
import { Suspense } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CompaniesIndex } from "@/components/companies/companies-index";

export default function CompaniesPage() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header className="flex items-end justify-between gap-4 border-b pb-6">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Companies</h1>
          <p className="text-sm text-muted-foreground">
            Browse employers and jump into their open roles.
          </p>
        </div>
        <Link
          href="/"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          ← Jobs
        </Link>
      </header>

      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <CompaniesIndex />
      </Suspense>
    </main>
  );
}
