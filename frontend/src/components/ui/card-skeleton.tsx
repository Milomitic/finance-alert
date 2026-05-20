import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Reusable card-shaped loading placeholder.
 *
 * The goal is **layout stability across the loading→loaded transition**:
 * pages and rows that use real cards should mount the same outer
 * `<Card>` + header strip during fetch, with the body filled by
 * animated skeleton bars. When data arrives, the body is replaced in
 * place — no reflow, no content jump.
 *
 * Why a dedicated primitive instead of inline `animate-pulse` divs:
 * the codebase had ~12 different ad-hoc skeleton variants, each with
 * slightly different padding, header treatment, and row heights. That
 * inconsistency itself is a perception cost — every page "loads
 * differently". Funnelling skeletons through this primitive keeps the
 * vocabulary uniform.
 *
 * Pass `label` to render a fake card header (uppercase tracking
 * matching `SectionTitle`). Pass `rows` (default 5) to control how
 * many shimmer rows fill the body. Use `className` to size the outer
 * card to match the slot it's filling (height-restricted grid cells
 * need an explicit `h-full` or fixed height).
 */
export function CardSkeleton({
  label,
  rows = 5,
  className,
  bodyClassName,
  /** Optional: render a stronger header-strip block (matches the
   *  `border-b bg-muted/30` pattern used by SectionTitle headers). */
  strongHeader = false,
}: {
  label?: string;
  rows?: number;
  className?: string;
  bodyClassName?: string;
  strongHeader?: boolean;
}) {
  return (
    <Card className={cn("h-full overflow-hidden", className)}>
      <CardContent className="p-0 h-full flex flex-col">
        {label && (
          <div
            className={cn(
              "shrink-0",
              strongHeader
                ? "px-3 py-2 border-b bg-muted/30"
                : "px-3 py-2",
            )}
          >
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {label}
            </span>
          </div>
        )}
        <div className={cn("flex-1 min-h-0 p-3 space-y-2", bodyClassName)}>
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="h-3 rounded bg-muted/50 animate-pulse"
              style={{
                // Stagger widths slightly so the skeleton reads as
                // varied list rows rather than a uniform bar stack.
                width: `${80 - (i % 4) * 10}%`,
              }}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Row-style skeleton (logo + 2-line stack + right-side value),
 * intended for list cards (TopPicks, AnalystActions, PremarketMovers).
 * Keep the visual identical across cards so the eye gets one
 * "loading-row" idiom instead of N variations.
 */
export function ListRowSkeleton() {
  return (
    <li className="flex items-center gap-2 px-3 py-1.5 border-b border-border/40 last:border-b-0">
      <div className="h-7 w-7 rounded-full bg-muted/50 animate-pulse shrink-0" />
      <div className="flex-1 min-w-0 space-y-1">
        <div className="h-3 w-20 rounded bg-muted/50 animate-pulse" />
        <div className="h-2.5 w-28 rounded bg-muted/40 animate-pulse" />
      </div>
      <div className="h-3.5 w-12 rounded bg-muted/40 animate-pulse shrink-0" />
    </li>
  );
}
