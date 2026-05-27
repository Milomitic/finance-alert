import { Layers, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useConfluence } from "@/hooks/useAlerts";
import { TONE_BG } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* Inner list of the strongest active multi-signal clusters (>=2 detectors
 * agreeing on one ticker). Natural height (no internal scroll) so it can be
 * dropped into any scroll container — standalone in ConfluenceCard, or as a
 * column inside the Segnali panel. Read-only; clicking a row opens the
 * stock page. */
export function ConfluenceRows({ limit = 8 }: { limit?: number }) {
  const q = useConfluence(7, true);
  const items = (q.data ?? []).slice(0, limit);
  if (q.isLoading) {
    return (
      <div className="px-3 py-6 text-center text-xs text-muted-foreground">
        Caricamento…
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        Nessuna confluenza attiva.
      </div>
    );
  }
  return (
    <ul className="divide-y">
      {items.map((c) => {
        const DirIcon = c.direction === "bull" ? TrendingUp : TrendingDown;
        const tone = c.direction === "bull" ? TONE_BG.bullish : TONE_BG.bearish;
        const pct = Math.round(c.strength);
        const dirWord = c.direction === "bull" ? "Long" : "Short";
        return (
          <li key={c.ticker}>
            {/* Single row: identity (logo + ticker/name, "solito formato") on
                the left, then direction + concurring-signal count + strength —
                all on one line. The identity name truncates first when tight. */}
            <Link
              to={`/stocks/${encodeURIComponent(c.ticker)}`}
              className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
              title={`${c.name ?? c.ticker} — ${c.n_signals} segnali concordi · direzione ${dirWord.toLowerCase()} · forza ${pct}/100${c.multi_horizon ? " · multi-orizzonte" : ""}${c.contested ? " · conteso" : ""}`}
            >
              <StockIdentity ticker={c.ticker} name={c.name} />
              {/* Fixed-width meta cluster → the Long/Short pill, the flag
                  icons, the bar and the score all line up vertically across
                  rows regardless of word width ("Short" vs "Long") or whether
                  the flag icons are present. */}
              <div className="shrink-0 flex items-center gap-2">
                {/* Direction + concurring count — fixed-width, left-aligned
                    cell so every "Long/Short" starts at the same x. */}
                <span className="w-[72px] shrink-0">
                  <span
                    className={cn(
                      "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-semibold",
                      tone,
                    )}
                    title={`${c.n_signals} segnali concordi · direzione ${dirWord.toLowerCase()}`}
                  >
                    <DirIcon className="h-3 w-3" />
                    {dirWord} {c.n_signals}
                  </span>
                </span>
                {/* Flag icons — fixed-width slot so present/absent doesn't
                    shift the bar/score columns. */}
                <span className="w-8 shrink-0 flex items-center gap-0.5">
                  {c.multi_horizon && (
                    <Layers
                      className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-400"
                      aria-label="Multi-orizzonte"
                    />
                  )}
                  {c.contested && (
                    <Swords
                      className="h-3.5 w-3.5 text-amber-500"
                      aria-label="Conteso (segnali contrastanti sulla direzione opposta)"
                    />
                  )}
                </span>
                {/* Strength bar + score. */}
                <div className="flex items-center gap-1.5">
                  <div className="h-1.5 w-10 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        c.direction === "bull" ? "bg-emerald-500" : "bg-rose-500",
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span
                    className="text-sm font-bold tabular-nums w-7 text-right"
                    title="Forza della confluenza (0–100)"
                  >
                    {pct}
                  </span>
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/* Standalone dashboard card wrapping ConfluenceRows in a Card + header with
 * its own scroll. Kept for reuse; the dashboard now renders the rows as a
 * column inside the Segnali panel (AlertsCompactPanel) instead. */
export function ConfluenceCard({ limit = 8 }: { limit?: number }) {
  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Layers}
            label="Top confluenze"
            right={<span className="text-xs text-muted-foreground">2+ segnali concordi</span>}
          />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          <ConfluenceRows limit={limit} />
        </div>
      </CardContent>
    </Card>
  );
}
