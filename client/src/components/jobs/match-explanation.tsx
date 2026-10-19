import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  MatchBucket,
  MatchExplanation as MatchExplanationType,
  MatchFacet,
} from "@/lib/types/job";

const BUCKET_ORDER: MatchBucket[] = ["strong", "gap", "neutral"];

const BUCKET_LABEL: Record<MatchBucket, string> = {
  strong: "Strong matches",
  gap: "Potential gaps",
  neutral: "Neutral",
};

const BUCKET_ICON: Record<MatchBucket, string> = {
  strong: "✓",
  gap: "⚠",
  neutral: "·",
};

const BUCKET_COLOR: Record<MatchBucket, string> = {
  strong: "text-emerald-600 dark:text-emerald-400",
  gap: "text-amber-600 dark:text-amber-400",
  neutral: "text-muted-foreground",
};

export function MatchExplanation({ match }: { match: MatchExplanationType }) {
  const groups = new Map<MatchBucket, MatchFacet[]>();
  for (const facet of match.facets) {
    const list = groups.get(facet.bucket) ?? [];
    list.push(facet);
    groups.set(facet.bucket, list);
  }

  const sections = BUCKET_ORDER.filter(
    (b) => (groups.get(b) ?? []).length > 0,
  );

  if (sections.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Match</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {sections.map((bucket) => (
          <section key={bucket} className="flex flex-col gap-2">
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {BUCKET_LABEL[bucket]}
            </h3>
            <ul className="flex flex-col gap-1.5">
              {(groups.get(bucket) ?? []).map((facet) => (
                <li
                  key={facet.key}
                  className="flex items-start gap-2 text-sm"
                >
                  <span
                    aria-hidden
                    className={`mt-0.5 inline-block w-4 shrink-0 text-center font-semibold ${BUCKET_COLOR[bucket]}`}
                  >
                    {BUCKET_ICON[bucket]}
                  </span>
                  <span className="leading-relaxed">{facet.label}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}
