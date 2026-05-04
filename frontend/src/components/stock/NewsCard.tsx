import { ExternalLink, Newspaper } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { useStockNews } from "@/hooks/useStockNews";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/**
 * Format a timestamp as a short relative-time string with a tone hint.
 * The tone tier is what the UI uses to color the badge so the eye can scan
 * for "fresh" content without reading every timestamp:
 *   - hot:    < 6h  (emerald)
 *   - warm:   < 24h (sky)
 *   - cool:   < 7d  (slate)
 *   - cold:   ≥ 7d  (muted)
 */
function relativeTime(iso: string | null): { text: string; tier: "hot" | "warm" | "cool" | "cold" } {
  if (!iso) return { text: "—", tier: "cold" };
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return { text: "—", tier: "cold" };
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 60) {
    const m = Math.max(1, Math.round(diffMin));
    return { text: `${m}m fa`, tier: "hot" };
  }
  const diffH = diffMin / 60;
  if (diffH < 24) {
    const h = Math.round(diffH);
    return { text: `${h}h fa`, tier: diffH < 6 ? "hot" : "warm" };
  }
  const diffD = diffH / 24;
  if (diffD < 30) {
    const d = Math.round(diffD);
    return { text: `${d}g fa`, tier: diffD < 7 ? "cool" : "cold" };
  }
  // Very old — show the actual date so the user can tell at a glance.
  return {
    text: new Date(iso).toLocaleDateString("it-IT", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    }),
    tier: "cold",
  };
}

const TIER_BADGE: Record<ReturnType<typeof relativeTime>["tier"], string> = {
  hot: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200",
  warm: "bg-sky-100 dark:bg-sky-900/40 text-sky-800 dark:text-sky-200",
  cool: "bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300",
  cold: "bg-muted text-muted-foreground",
};

/**
 * News list with relative-time tier coloring and a publisher chip.
 * The whole row is a clickable anchor so the click target is forgiving.
 * `line-clamp-3` instead of 2 so longer titles don't get aggressively
 * truncated on a wider card; the height is bounded by the parent scroller.
 */
export function NewsCard({ ticker }: Props) {
  // Bumped from 5 to 25 — the new scrollable layout (h-full + flex-1 +
  // overflow-y-auto) can absorb a long list. yfinance typically returns
  // 10–20 items, so 25 is a safe ceiling that still respects the cache.
  const q = useStockNews(ticker, 25);
  const items = q.data?.items ?? [];

  // Defensive client-side sort — backend already orders desc, but if a future
  // caching layer or mock sneaks unsorted data through, we still render
  // correctly. Cheap (≤25 items).
  const sorted = [...items].sort((a, b) => {
    const ta = a.published_at ? new Date(a.published_at).getTime() : 0;
    const tb = b.published_at ? new Date(b.published_at).getTime() : 0;
    return tb - ta;
  });

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-4 h-full flex flex-col min-h-0">
        <div className="flex items-center gap-2 mb-3 shrink-0">
          <Newspaper className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            News
          </span>
          {sorted.length > 0 && (
            <span
              className="text-xs text-muted-foreground tabular-nums"
              title={`${sorted.length} articoli totali`}
            >
              ({sorted.length})
            </span>
          )}
          <span className="ml-auto text-xs text-muted-foreground italic">
            yfinance · cache 1h
          </span>
        </div>

        {/* Scroller. flex-1 + min-h-0 lets the list shrink to fit the card
            height (set by the grid row), and overflow-y-auto contains the
            scroll inside the card so it never leaks into siblings.
            pr-1 prevents items from sitting under the scrollbar gutter. */}
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 -mr-1">
          {q.isLoading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="space-y-1.5">
                  <div className="h-3.5 bg-muted/40 animate-pulse rounded" />
                  <div className="h-3 bg-muted/40 animate-pulse rounded w-2/3" />
                </div>
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8 px-2">
              News non disponibili per questo ticker.
              <div className="text-xs mt-1 opacity-75">
                Yahoo Finance non espone news per questo simbolo, oppure è
                temporaneamente rate-limited.
              </div>
            </div>
          ) : (
            <ul className="space-y-2">
              {sorted.map((n) => {
                const rel = relativeTime(n.published_at);
                return (
                  <li key={n.link}>
                    <a
                      href={n.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cn(
                        "block rounded-md border border-transparent p-2 -mx-1",
                        // Subtle accent border-left in the relative-time tier
                        // color — gives the eye a vertical scan for freshness
                        // without being loud about it.
                        "hover:bg-accent/40 hover:border-border/40 transition-colors",
                        rel.tier === "hot" && "border-l-2 border-l-emerald-400 dark:border-l-emerald-500",
                        rel.tier === "warm" && "border-l-2 border-l-sky-400 dark:border-l-sky-500",
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        <span className="text-sm font-medium leading-snug line-clamp-3 flex-1 min-w-0">
                          {n.title}
                        </span>
                        <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground mt-0.5 opacity-60" />
                      </div>
                      <div className="flex items-center gap-2 mt-1.5 text-[11px]">
                        <span
                          className="font-semibold text-foreground/70 truncate"
                          title={n.publisher}
                        >
                          {n.publisher}
                        </span>
                        <span
                          className={cn(
                            "ml-auto px-1.5 py-0.5 rounded font-semibold tabular-nums shrink-0",
                            TIER_BADGE[rel.tier],
                          )}
                          title={
                            n.published_at
                              ? new Date(n.published_at).toLocaleString("it-IT")
                              : "Data sconosciuta"
                          }
                        >
                          {rel.text}
                        </span>
                      </div>
                    </a>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
