import { Badge } from "@/components/ui/badge";

type Props = {
  strong: number | null | undefined;
  gap: number | null | undefined;
};

export function MatchPreview({ strong, gap }: Props) {
  if (strong == null && gap == null) return null;
  const s = strong ?? 0;
  const g = gap ?? 0;
  if (s === 0 && g === 0) return null;
  return (
    <Badge
      variant="secondary"
      className="gap-1 bg-background"
      title={`${s} strong matches, ${g} potential gaps`}
    >
      {s > 0 ? (
        <span className="text-emerald-600 dark:text-emerald-400">✓ {s}</span>
      ) : null}
      {s > 0 && g > 0 ? <span className="text-muted-foreground">·</span> : null}
      {g > 0 ? (
        <span className="text-amber-600 dark:text-amber-400">⚠ {g}</span>
      ) : null}
    </Badge>
  );
}
