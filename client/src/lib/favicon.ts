import type { Company } from "@/lib/types/job";

function hostOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

export function faviconUrl(
  company: Pick<Company, "website" | "careers_url"> | null | undefined,
  size: number = 64,
): string | null {
  if (!company) return null;
  const host = hostOf(company.website) ?? hostOf(company.careers_url);
  if (!host) return null;
  return `https://www.google.com/s2/favicons?domain=${host}&sz=${size}`;
}
