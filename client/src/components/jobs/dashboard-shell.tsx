"use client";

import {
  FiltersSheetTrigger,
  FiltersSidebar,
} from "@/components/jobs/job-filters";
import { JobList } from "@/components/jobs/job-list";
import { JobTabs } from "@/components/jobs/job-tabs";
import { SearchInput } from "@/components/jobs/search-input";
import { SortSelect } from "@/components/jobs/sort-select";
import { useTab } from "@/lib/hooks/use-tab";

export function DashboardShell() {
  const { tab } = useTab();
  const showFilters = tab === "all";
  const showSort = tab === "all";

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <JobTabs />
        <div className="flex items-center gap-2">
          {showFilters ? <SearchInput /> : null}
          {showSort ? <SortSelect /> : null}
          {showFilters ? (
            <div className="md:hidden">
              <FiltersSheetTrigger />
            </div>
          ) : null}
        </div>
      </div>

      <div
        className={
          showFilters
            ? "grid grid-cols-1 gap-6 md:grid-cols-[16rem_1fr]"
            : "grid grid-cols-1 gap-6"
        }
      >
        {showFilters ? <FiltersSidebar className="hidden md:block" /> : null}
        <JobList />
      </div>
    </>
  );
}
