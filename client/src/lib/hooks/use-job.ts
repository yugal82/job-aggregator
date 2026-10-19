import { useQuery } from "@tanstack/react-query";
import { getJob } from "@/lib/api/jobs";

export function useJob(id: string) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: ({ signal }) => getJob(id, signal),
    enabled: Boolean(id),
  });
}
