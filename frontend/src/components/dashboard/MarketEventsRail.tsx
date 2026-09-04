import { Radar } from "lucide-react";
import { Link } from "react-router-dom";

import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import type { PremarketMover } from "@/api/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { usePremarketMovers } from "@/hooks/usePremarketMovers";
import { cn } from "@/lib/utils";

/* ─── MarketEventsRail — the deliberately thin one ──────────────────────── *
 *
 * Three event feeds (52-week highs/lows, volume spikes, US pre-market) in one
 * narrow column, each row reduced to ticker + one number.
 *
 * WHY IT DROPS THE COMPANY NAME. The dashboard's activity row used to be four
 * equal cards, each carrying ticker + name + price + Δ% + volume + ×avg. At a
 * 1280px viewport that gave every card ~230px against list rows whose fixed
 * numeric columns alone wanted 241px, so the name column resolved to 0px and
 * rendered as nothing. The information was not reduced — it was silently lost,
 * and only on some screens.
 *
 * So this rail reduces on purpose instead. Top movers and Volumi keep full
 * rows because they are the two lists actually read every day; these three are
 * "did anything unusual happen" feeds, and a ticker plus one number answers
 * that. The name and the full detail are one click away on the stock page.
 *
 * Everything here stays visible at every width — nothing hides behind a tab,
 * which is the property that made this preferable to folding the four cards
 * into a segmented control.
 */

interface Props {
  movers: MoversBlock;
}

function RailHeader({ label, count }: { label: string; count?: number }) {
  return (
    <div className="px-3 py-1 border-y bg-muted/40 shrink-0 flex items-baseline justify-between gap-2">
      <span className="text-[0.6765rem] uppercase tracking-[0.16em] font-bold text-muted-foreground truncate">
        {label}
      </span>
      {count != null && (
        <span className="text-[0.6765rem] tabular-nums text-muted-foreground/70 shrink-0">{count}</span>
      )}
    </div>
  );
}

/** One rail row: ticker on the left, a single value on the right.
 *  `min-w-0` on the ticker and `shrink-0` on the value is the whole layout
 *  contract — the ticker truncates, the number never does. */
function RailRow({
  ticker,
  value,
  tone,
  title,
}: {
  ticker: string;
  value: string;
  tone: "pos" | "neg" | "warn" | "mute";
  title: string;
}) {
  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(ticker)}`}
        title={title}
        className="flex items-baseline gap-2 px-3 py-1 hover:bg-accent/30 transition-colors"
      >
        <span className="text-[12.5px] font-semibold truncate min-w-0">{ticker}</span>
        <span
          className={cn(
            "ml-auto shrink-0 text-[0.7059rem] font-semibold tabular-nums",
            tone === "pos" && "text-emerald-600 dark:text-emerald-400",
            tone === "neg" && "text-red-600 dark:text-red-400",
            tone === "warn" && "text-amber-600 dark:text-amber-400",
            tone === "mute" && "text-muted-foreground",
          )}
        >
          {value}
        </span>
      </Link>
    </li>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="px-3 py-2 text-[0.7059rem] text-muted-foreground">{label}</div>;
}

export function MarketEventsRail({ movers }: Props) {
  // Same query the standalone pre-market card used, and the same strict gate:
  // `available` already aggregates "US market closed AND cache fresh AND
  // non-empty", so a false here means there is genuinely nothing to show and
  // the section is omitted rather than rendered empty.
  const premarketQ = usePremarketMovers();
  const pm = premarketQ.data;
  const pmAvailable = !!pm?.available;

  const highs = movers.new_52w_high.slice(0, 5);
  const lows = movers.new_52w_low.slice(0, 3);
  const spikes = movers.volume_spikes.slice(0, 5);
  const pmG: PremarketMover[] = pmAvailable ? (pm?.gainers ?? []).slice(0, 3) : [];
  const pmL: PremarketMover[] = pmAvailable ? (pm?.losers ?? []).slice(0, 3) : [];

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle icon={Radar} label="Sintesi eventi" />
        </div>

        {/* Two orientations, because this card occupies two different slots.
            At dense-3+ it is the narrow third column beside two taller cards,
            so the sections stack and it scrolls internally rather than setting
            the row height. Between md and dense-3 the row only fits two cards,
            so this one spans the full width underneath them — and there the
            same three sections read far better side by side than as one very
            long column. `dense-3:grid-cols-1` comes last so the wider
            breakpoint wins. */}
        <div className="flex-1 min-h-0 overflow-y-auto grid grid-cols-1 md:grid-cols-3 dense-3:grid-cols-1 md:divide-x dense-3:divide-x-0 divide-border/40 [&>*]:min-w-0">
          <section className="min-w-0">
            <RailHeader
              label="52 settimane"
              count={movers.new_52w_high.length + movers.new_52w_low.length}
            />
            {highs.length === 0 && lows.length === 0 ? (
              <Empty label="Nessun evento" />
            ) : (
              <ul>
                {highs.map((m: Mover) => (
                  <RailRow
                    key={`h-${m.ticker}`}
                    ticker={m.ticker}
                    value={`$${m.last_close.toFixed(2)}`}
                    tone="pos"
                    title={`${m.name} — nuovo massimo 52 settimane`}
                  />
                ))}
                {lows.map((m: Mover) => (
                  <RailRow
                    key={`l-${m.ticker}`}
                    ticker={m.ticker}
                    value={`$${m.last_close.toFixed(2)}`}
                    tone="neg"
                    title={`${m.name} — nuovo minimo 52 settimane`}
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="min-w-0">
            <RailHeader label="Volume spike" count={movers.volume_spikes.length} />
            {spikes.length === 0 ? (
              <Empty label="Nessuno spike" />
            ) : (
              <ul>
                {spikes.map((m: VolumeSpike) => (
                  <RailRow
                    key={m.ticker}
                    ticker={m.ticker}
                    value={`${m.vol_ratio.toFixed(1)}×`}
                    tone="warn"
                    title={`${m.name} — ${m.vol_ratio.toFixed(1)}× il volume medio a 20 giorni`}
                  />
                ))}
              </ul>
            )}
          </section>

          {/* Rendered even when empty so the three-column arrangement keeps
              its shape; the header explains the absence rather than leaving a
              hole where a section used to be. */}
          <section className="min-w-0">
            <RailHeader label="Pre-market USA" />
            {pmAvailable && (pmG.length > 0 || pmL.length > 0) ? (
              <ul>
                {pmG.map((m) => (
                  <RailRow
                    key={`pg-${m.ticker}`}
                    ticker={m.ticker}
                    value={`+${m.change_pct.toFixed(1)}%`}
                    tone="pos"
                    title={`${m.name} — $${m.price.toFixed(2)} in pre-market`}
                  />
                ))}
                {pmL.map((m) => (
                  <RailRow
                    key={`pl-${m.ticker}`}
                    ticker={m.ticker}
                    value={`${m.change_pct.toFixed(1)}%`}
                    tone="neg"
                    title={`${m.name} — $${m.price.toFixed(2)} in pre-market`}
                  />
                ))}
              </ul>
            ) : (
              <Empty label="Sessione USA aperta" />
            )}
          </section>
        </div>
      </CardContent>
    </Card>
  );
}
