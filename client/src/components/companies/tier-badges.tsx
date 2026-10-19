"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { useTiers } from "@/lib/hooks/use-tiers";

export function TierBadges({
  tiers,
  limit,
}: {
  tiers: string[] | undefined | null;
  limit?: number;
}) {
  const { data } = useTiers();
  const labelMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const t of data?.tiers ?? []) map.set(t.key, t.label);
    return map;
  }, [data]);

  if (!tiers || tiers.length === 0) return null;
  const visible = typeof limit === "number" ? tiers.slice(0, limit) : tiers;

  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((key) => (
        <Badge key={key} variant="secondary" className="font-medium">
          {labelMap.get(key) ?? key}
        </Badge>
      ))}
    </div>
  );
}
