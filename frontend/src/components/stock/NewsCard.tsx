import { ExternalLink, Newspaper, TrendingDown, TrendingUp } from "lucide-react";

import type { StockNewsItem } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useStockNews } from "@/hooks/useStockNews";
import { cn } from "@/lib/utils";

/* ─── Sentiment chip rendering ──────────────────────────────────────────── *
 * The backend classifier (`news_sentiment.py`) tags every headline as
 * bullish / neutral / bearish via a finance-keyword scorer. The UI shows
 * a tiny colored dot + arrow for directional sentiment so the user can
 * scan a list of titles and spot bullish/bearish density at a glance.
 * Neutral items render no chip — the absence of decoration IS the signal. */

interface SentimentChipMeta {
  cls: string;
  Icon: typeof TrendingUp;
  label: string;
}

const SENTIMENT_META: Record<NonNullable<StockNewsItem["sentiment"]>, SentimentChipMeta | null> = {
  bullish: {
    cls: "border-emerald-300/70 dark:border-emerald-700/60 text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40",
    Icon: TrendingUp,
    label: "bullish",
  },
  bearish: {
    cls: "border-rose-300/70 dark:border-rose-700/60 text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40",
    Icon: TrendingDown,
    label: "bearish",
  },
  neutral: null, // no chip rendered
};

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
 * Each row caps at 2 title lines + meta — chosen for density (a 25-item
 * scrollable list reads better with shorter rows). Long titles get clipped
 * with the standard ellipsis; full text is preserved on hover via the
 * native title tooltip from the publisher chip + browser link preview.
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

  // Layout trick: NewsCard's natural content (25 items × ~80px = ~2000px)
  // would otherwise force the entire grid row to that height. We don't want
  // that — per user spec, only Fundamentals + Valuations should "command"
  // the row height. So we wrap the actual Card in a `relative` container
  // with the Card positioned `absolute inset-0`. Effects:
  //   1. The grid item (the wrapper div) has 0 intrinsic content height
  //      because its only child is out-of-flow (absolute) → contributes
  //      nothing to the grid row's max-content sizing.
  //   2. The Card fills the wrapper, which fills the row's actual height
  //      (set by Fundamentals or Valuations, whichever is taller).
  //   3. Internal flex-1 + overflow-y-auto on the list contains the long
  //      news list inside that bounded height.
  // This is a standard CSS pattern for "child should fill parent but not
  // contribute to its sizing" — same trick used for full-bleed images
  // inside fixed-aspect containers.
  return (
    <div className="relative h-full">
      <Card className="absolute inset-0 overflow-hidden flex flex-col">
        <CardContent className="p-4 h-full flex flex-col min-h-0">
        <SectionTitle
          icon={Newspaper}
          label="News"
          className="mb-3 shrink-0"
          right={
            <div className="flex items-center gap-2">
              {sorted.length > 0 && (
                <span
                  className="text-xs text-muted-foreground tabular-nums"
                  title={`${sorted.length} articoli totali`}
                >
                  ({sorted.length})
                </span>
              )}
              <span className="text-xs text-muted-foreground italic">
                yfinance · cache 1h
              </span>
            </div>
          }
        />

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
            <ul className="space-y-1">
              {sorted.map((n) => {
                const rel = relativeTime(n.published_at);
                return (
                  <li key={n.link}>
                    <a
                      href={n.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cn(
                        // Tighter padding (px-2 py-1.5 instead of p-2) trims
                        // ~10px per row → noticeable on a 25-item list.
                        "block rounded-md border border-transparent px-2 py-1.5 -mx-1",
                        // Subtle accent border-left in the relative-time tier
                        // color — gives the eye a vertical scan for freshness
                        // without being loud about it.
                        "hover:bg-accent/40 hover:border-border/40 transition-colors",
                        rel.tier === "hot" && "border-l-2 border-l-emerald-400 dark:border-l-emerald-500",
                        rel.tier === "warm" && "border-l-2 border-l-sky-400 dark:border-l-sky-500",
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        {/* line-clamp-2 (was 3) is the single biggest space
                            saver — caps each row at title-2-lines + meta. */}
                        <span className="text-sm font-medium leading-tight line-clamp-2 flex-1 min-w-0">
                          {n.title}
                        </span>
                        <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground mt-0.5 opacity-60" />
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px]">
                        <span
                          className="font-semibold text-foreground/70 truncate"
                          title={n.publisher}
                        >
                          {n.publisher}
                        </span>
                        {/* Sentiment chip — only rendered for directional
                            classifications (bullish / bearish). Neutral
                            articles show no chip; the absence is itself the
                            signal "no decisive sentiment". */}
                        {n.sentiment && SENTIMENT_META[n.sentiment] && (
                          (() => {
                            const meta = SENTIMENT_META[n.sentiment]!;
                            const SentimentIcon = meta.Icon;
                            return (
                              <span
                                className={cn(
                                  "inline-flex items-center gap-0.5 px-1 py-0.5 rounded-sm border text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap shrink-0",
                                  meta.cls,
                                )}
                                title={`Sentiment del titolo: ${meta.label} (classificato server-side dal motore parole-chiave finance)`}
                              >
                                <SentimentIcon className="h-2.5 w-2.5" />
                                {meta.label}
                              </span>
                            );
                          })()
                        )}
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
    </div>
  );
}
