import { apiFetch } from "./client";
import { tiersResponseSchema } from "@/lib/types/job";

export function listTiers(signal?: AbortSignal) {
  return apiFetch("/api/filters/tiers", {
    schema: tiersResponseSchema,
    signal,
  });
}
