import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { listJobs, type JobsListParams, type JobsTab } from "@/lib/api/jobs";

export function useJobs(
  tab: JobsTab,
  params: JobsListParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ["jobs", tab, params],
    queryFn: ({ signal }) => listJobs(tab, params, signal),
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
}
