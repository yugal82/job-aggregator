import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { JobDetailView } from "@/components/jobs/job-detail";

export default async function JobDetailPage(props: PageProps<"/jobs/[id]">) {
  const { id } = await props.params;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-10">
      <div>
        <Link
          href="/"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          ← Back to jobs
        </Link>
      </div>
      <JobDetailView id={id} />
    </main>
  );
}
