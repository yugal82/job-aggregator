"use client";

import { useState } from "react";
import { faviconUrl } from "@/lib/favicon";
import type { Company } from "@/lib/types/job";

type Size = "sm" | "md" | "lg";

const SIZE_PX: Record<Size, number> = { sm: 32, md: 44, lg: 56 };
const SIZE_CLASS: Record<Size, string> = {
  sm: "size-8 text-[11px]",
  md: "size-11 text-sm",
  lg: "size-14 text-base",
};

export function CompanyMark({
  company,
  size = "md",
}: {
  company:
    | Pick<Company, "name" | "logo_url" | "website" | "careers_url">
    | null
    | undefined;
  size?: Size;
}) {
  const [imgError, setImgError] = useState(false);
  const url =
    !imgError && company
      ? (company.logo_url ?? faviconUrl(company, SIZE_PX[size] * 2))
      : null;

  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt=""
        onError={() => setImgError(true)}
        className={`${SIZE_CLASS[size]} shrink-0 rounded-lg border bg-white object-contain p-1.5`}
      />
    );
  }

  const initials = (company?.name ?? "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div
      aria-hidden
      className={`${SIZE_CLASS[size]} flex shrink-0 items-center justify-center rounded-lg border bg-muted font-semibold text-muted-foreground`}
    >
      {initials || "?"}
    </div>
  );
}
