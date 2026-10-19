"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useCompanies } from "@/lib/hooks/use-companies";
import { useFilters } from "@/lib/hooks/use-filters";
import { useTiers } from "@/lib/hooks/use-tiers";
import {
  activeFilterCount,
  todayIsoDate,
  type JobFilters,
  type SourceType,
} from "@/lib/filters/schema";

export function FilterCount() {
  const { filters } = useFilters();
  const n = activeFilterCount(filters);
  if (n === 0) return null;
  return (
    <Badge variant="secondary" className="ml-1.5">
      {n}
    </Badge>
  );
}

export function FiltersSidebar({ className }: { className?: string }) {
  return (
    <aside className={className}>
      <div className="sticky top-6 rounded-xl border bg-card p-5 shadow-[0_1px_0_rgba(0,0,0,0.02)]">
        <FiltersBody />
      </div>
    </aside>
  );
}

export function FiltersSheetTrigger() {
  const { filters } = useFilters();
  const n = activeFilterCount(filters);

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button variant="outline" size="sm">
            Filters
            {n > 0 ? (
              <Badge variant="secondary" className="ml-1.5">
                {n}
              </Badge>
            ) : null}
          </Button>
        }
      />
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-sm">
        <SheetHeader>
          <SheetTitle>Filters</SheetTitle>
          <SheetDescription>Narrow down the list.</SheetDescription>
        </SheetHeader>
        <Separator />
        <div className="overflow-y-auto px-4 py-4">
          <FiltersBody />
        </div>
        <Separator />
        <SheetFooter>
          <SheetClose
            render={<Button variant="outline" size="sm">Close</Button>}
          />
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function FiltersBody() {
  const { filters, setFilters, clearFilters } = useFilters();
  const n = activeFilterCount(filters);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <h2 className="text-sm font-semibold">Filters</h2>
          {n > 0 ? (
            <span className="text-xs text-muted-foreground">· {n} active</span>
          ) : null}
        </div>
        <Button
          size="xs"
          variant="ghost"
          disabled={n === 0}
          onClick={clearFilters}
        >
          Clear all
        </Button>
      </div>

      <QuickChips filters={filters} setFilters={setFilters} />
      <Separator />
      <SeniorityFilter filters={filters} setFilters={setFilters} />
      <Separator />
      <TierFilter filters={filters} setFilters={setFilters} />
      <Separator />
      <SourceTypeFilter filters={filters} setFilters={setFilters} />
      <Separator />
      <CompanyFilter filters={filters} setFilters={setFilters} />
      <Separator />
      <LocationFilter filters={filters} setFilters={setFilters} />
      <Separator />
      <PostedAfterFilter filters={filters} setFilters={setFilters} />
    </div>
  );
}

type FilterSectionProps = {
  filters: JobFilters;
  setFilters: (
    updater: JobFilters | ((prev: JobFilters) => JobFilters),
  ) => void;
};

function QuickChips({ filters, setFilters }: FilterSectionProps) {
  const today = todayIsoDate();
  const isNewToday = filters.posted_after === today;

  return (
    <div className="flex flex-wrap gap-2">
      <ChipButton
        active={isNewToday}
        onClick={() =>
          setFilters((prev) => ({
            ...prev,
            posted_after: isNewToday ? null : today,
          }))
        }
      >
        New today
      </ChipButton>
      <ChipButton
        active={filters.remote}
        onClick={() =>
          setFilters((prev) => ({ ...prev, remote: !prev.remote }))
        }
      >
        Remote only
      </ChipButton>
    </div>
  );
}

function ChipButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      size="xs"
      variant={active ? "default" : "outline"}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function CompanyFilter({ filters, setFilters }: FilterSectionProps) {
  const { data, isPending } = useCompanies();
  const [search, setSearch] = useState("");

  const selected = new Set(filters.companies);

  const visible = useMemo(() => {
    const companies = data?.items ?? [];
    const q = search.trim().toLowerCase();
    const base = q
      ? companies.filter(
          (c) =>
            c.name.toLowerCase().includes(q) || c.slug.toLowerCase().includes(q),
        )
      : companies;
    return [...base].sort((a, b) => a.name.localeCompare(b.name));
  }, [data, search]);

  const toggle = (slug: string) => {
    setFilters((prev) => {
      const set = new Set(prev.companies);
      if (set.has(slug)) set.delete(slug);
      else set.add(slug);
      return { ...prev, companies: Array.from(set) };
    });
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Company
        </span>
        {selected.size > 0 ? (
          <Button
            size="xs"
            variant="ghost"
            onClick={() =>
              setFilters((prev) => ({ ...prev, companies: [] }))
            }
          >
            Clear
          </Button>
        ) : null}
      </div>
      <Input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search companies…"
      />
      <div className="max-h-56 overflow-y-auto rounded-lg border bg-background">
        {isPending ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">
            Loading…
          </div>
        ) : visible.length === 0 ? (
          <div className="px-3 py-2 text-xs text-muted-foreground">
            No matches.
          </div>
        ) : (
          <ul className="flex flex-col">
            {visible.map((c) => {
              const checked = selected.has(c.slug);
              return (
                <li key={c.slug}>
                  <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => toggle(c.slug)}
                    />
                    <span className="truncate">{c.name}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function LocationFilter({ filters, setFilters }: FilterSectionProps) {
  const [draft, setDraft] = useState("");

  const addLocation = (raw: string) => {
    const value = raw.trim();
    if (!value) return;
    setFilters((prev) => {
      if (prev.locations.includes(value)) return prev;
      return { ...prev, locations: [...prev.locations, value] };
    });
    setDraft("");
  };

  const removeLocation = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      locations: prev.locations.filter((l) => l !== value),
    }));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addLocation(draft);
    } else if (e.key === "Backspace" && !draft && filters.locations.length) {
      removeLocation(filters.locations[filters.locations.length - 1]);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Location
      </span>
      {filters.locations.length ? (
        <div className="flex flex-wrap gap-1.5">
          {filters.locations.map((loc) => (
            <Badge
              key={loc}
              variant="secondary"
              className="cursor-pointer gap-1"
              onClick={() => removeLocation(loc)}
            >
              {loc}
              <span aria-hidden>×</span>
            </Badge>
          ))}
        </div>
      ) : null}
      <Input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => addLocation(draft)}
        placeholder="Type and press Enter (e.g. San Francisco)"
      />
      <label className="flex items-center gap-2 pt-1 text-sm">
        <Checkbox
          checked={filters.remote}
          onCheckedChange={(checked) =>
            setFilters((prev) => ({ ...prev, remote: Boolean(checked) }))
          }
        />
        Remote only
      </label>
    </div>
  );
}

function PostedAfterFilter({ filters, setFilters }: FilterSectionProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Posted after
        </span>
        {filters.posted_after ? (
          <Button
            size="xs"
            variant="ghost"
            onClick={() =>
              setFilters((prev) => ({ ...prev, posted_after: null }))
            }
          >
            Clear
          </Button>
        ) : null}
      </div>
      <Input
        type="date"
        value={filters.posted_after ?? ""}
        onChange={(e) =>
          setFilters((prev) => ({
            ...prev,
            posted_after: e.target.value || null,
          }))
        }
      />
    </div>
  );
}

function SeniorityFilter({ filters, setFilters }: FilterSectionProps) {
  const { seniority } = filters;

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Seniority
      </span>
      <div className="flex flex-wrap gap-1.5">
        <Button
          size="xs"
          variant={seniority === "default" ? "default" : "outline"}
          onClick={() =>
            setFilters((prev) => ({ ...prev, seniority: "default" }))
          }
          title="New grad, junior, L1, Software Engineer I / II — full-time only"
        >
          Early career
        </Button>
        <Button
          size="xs"
          variant={seniority === "internship" ? "default" : "outline"}
          onClick={() =>
            setFilters((prev) => ({ ...prev, seniority: "internship" }))
          }
          title="Internships, co-ops, student programs"
        >
          Internship
        </Button>
        <Button
          size="xs"
          variant={seniority === "any" ? "default" : "outline"}
          onClick={() =>
            setFilters((prev) => ({ ...prev, seniority: "any" }))
          }
          title="Show roles at every level"
        >
          All levels
        </Button>
      </div>
      {seniority === "default" ? (
        <p className="text-xs text-muted-foreground">
          Showing early-career roles by default.
        </p>
      ) : seniority === "internship" ? (
        <p className="text-xs text-muted-foreground">
          Internships, co-ops, and student programs only.
        </p>
      ) : null}
    </div>
  );
}

function TierFilter({ filters, setFilters }: FilterSectionProps) {
  const { data, isPending } = useTiers();
  const tiers = data?.tiers ?? [];

  const toggle = (key: string) => {
    setFilters((prev) => ({
      ...prev,
      tier: prev.tier === key ? null : key,
    }));
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Company tier
        </span>
        {filters.tier ? (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setFilters((prev) => ({ ...prev, tier: null }))}
          >
            Clear
          </Button>
        ) : null}
      </div>
      {isPending ? (
        <span className="text-xs text-muted-foreground">Loading…</span>
      ) : tiers.length === 0 ? (
        <span className="text-xs text-muted-foreground">
          No tiers configured.
        </span>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {tiers.map((t) => (
            <Button
              key={t.key}
              size="xs"
              variant={filters.tier === t.key ? "default" : "outline"}
              onClick={() => toggle(t.key)}
              title={t.description}
            >
              {t.label}
              <span className="ml-1 text-xs opacity-70">· {t.company_count}</span>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

const OWN_PORTAL_TYPES: SourceType[] = ["official", "ats"];

function SourceTypeFilter({ filters, setFilters }: FilterSectionProps) {
  const current = new Set(filters.source_types);
  const ownPortalOnly =
    OWN_PORTAL_TYPES.every((t) => current.has(t)) && !current.has("board");

  const toggleOwnPortal = (checked: boolean) => {
    setFilters((prev) => ({
      ...prev,
      source_types: checked ? OWN_PORTAL_TYPES : [],
    }));
  };

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Source
      </span>
      <label className="flex items-start gap-2 text-sm">
        <Checkbox
          checked={ownPortalOnly}
          onCheckedChange={(c) => toggleOwnPortal(Boolean(c))}
          className="mt-0.5"
        />
        <span className="leading-snug">
          Own portal only
          <span className="block text-xs text-muted-foreground">
            Official careers pages and first-party ATS (no job boards).
          </span>
        </span>
      </label>
    </div>
  );
}
