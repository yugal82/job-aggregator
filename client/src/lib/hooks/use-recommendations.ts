import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  listRecommendations,
  type RecommendationsParams,
} from "@/lib/api/jobs";

export function useRecommendations(
  params: RecommendationsParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ["recommendations", params],
    queryFn: ({ signal }) => listRecommendations(params, signal),
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
}
