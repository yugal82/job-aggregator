import Link from "next/link";
import { Suspense } from "react";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CompanyDetailView } from "@/components/companies/company-detail";

export default async function CompanyPage(
  props: PageProps<"/companies/[slug]">,
) {
  const { slug } = await props.params;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-8">
      <div>
        <Link
          href="/companies"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          ← Companies
        </Link>
      </div>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <CompanyDetailView slug={slug} />
      </Suspense>
    </main>
  );
}
