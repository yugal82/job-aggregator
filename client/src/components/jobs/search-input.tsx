"use client";

import { useEffect, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import { useFilters } from "@/lib/hooks/use-filters";

const DEBOUNCE_MS = 250;

export function SearchInput() {
  const { filters, setFilters } = useFilters();
  const [value, setValue] = useState(filters.q);
  const lastExternal = useRef(filters.q);

  useEffect(() => {
    if (filters.q !== lastExternal.current && filters.q !== value) {
      setValue(filters.q);
      lastExternal.current = filters.q;
    }
  }, [filters.q, value]);

  useEffect(() => {
    if (value === filters.q) return;
    const t = window.setTimeout(() => {
      lastExternal.current = value;
      setFilters((prev) => ({ ...prev, q: value }));
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [value, filters.q, setFilters]);

  return (
    <Input
      type="search"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder="Search title or description…"
      className="w-full sm:max-w-sm"
      aria-label="Search jobs"
    />
  );
}
