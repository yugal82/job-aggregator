import { z } from "zod";
import { apiFetch } from "./client";

export const healthSchema = z.object({
  status: z.string(),
  database: z.string(),
  redis: z.string(),
});

export type Health = z.infer<typeof healthSchema>;

export function getHealth(signal?: AbortSignal) {
  return apiFetch("/health", { schema: healthSchema, signal });
}
