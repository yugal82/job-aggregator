"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { JobSort } from "@/lib/api/jobs";
import { useSort } from "@/lib/hooks/use-sort";

const LABELS: Record<JobSort, string> = {
  newest: "Newest",
  match: "Best match",
  salary: "Salary",
};

const ORDER: JobSort[] = ["newest", "match", "salary"];

export function SortSelect() {
  const { sort, setSort } = useSort();
  return (
    <Select value={sort} onValueChange={(v) => setSort(v as JobSort)}>
      <SelectTrigger size="sm" aria-label="Sort jobs">
        <SelectValue>Sort: {LABELS[sort]}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {ORDER.map((v) => (
          <SelectItem key={v} value={v}>
            {LABELS[v]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
