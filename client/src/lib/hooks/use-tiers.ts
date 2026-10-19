import { useQuery } from "@tanstack/react-query";
import { listTiers } from "@/lib/api/filters";

export function useTiers() {
  return useQuery({
    queryKey: ["filters", "tiers"],
    queryFn: ({ signal }) => listTiers(signal),
    staleTime: 10 * 60_000,
  });
}
