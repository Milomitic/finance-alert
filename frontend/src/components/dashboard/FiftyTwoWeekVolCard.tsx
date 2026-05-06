import { LineChart } from "lucide-react";
import { Link } from "react-router-dom";

import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
}

/* ─── Sparkline-bg row primitive ────────────────────────────────────────── *
 *
 * A compact row that paints the stock's recent price sparkline as a
 * fading background. The user preferred this Spikes-style row over
 * the previous plain-table layout for both 52w events and volume
 * spikes — same visual language across the card.
 *
 * Row height: ~30px (px-3 py-1 + leading-tight). The "Spikes" tab
 * was the third (now-removed) view of this card; we adopted its row
 * shape here, hence the "spark" in the function name.
 */
function SparkRow({
  ticker,
  name,
  sparkline,
  rightLine1,
  rightLine2,
  rightTone,
  pillar,
}: {
  ticker: string;
  name?: string | null;
  sparkline: number[] | null | undefined;
  /** Big right-aligned value (e.g. "$387.08", "2.5×"). */
  rightLine1: string;
  /** Smaller line below (e.g. "+1.20%" or "vol"). null = no second line. */
  rightLine2?: string | null;
  rightTone: "pos" | "neg" | "neutral";
  /** Tiny leading icon — 📈 or 📉 for 52w highs/lows, ⚡ for spikes. */
  pillar: string;
}) {
  const sl = sparkline ?? [];
  const min = sl.length ? Math.min(...sl) : 0;
  const max = sl.length ? Math.max(...sl) : 1;
  const range = max - min || 1;
  const W = 100, H = 30;
  const points = sl
    .map(
      (v, i) =>
        `${((i / Math.max(1, sl.length - 1)) * W).toFixed(2)},${(H - ((v - min) / range) * H).toFixed(2)}`,
    )
    .join(" ");
  const trendStroke =
    rightTone === "pos" ? "#16a34a" : rightTone === "neg" ? "#dc2626" : "#737373";
  const toneCls =
    rightTone === "pos"
      ? "text-emerald-600 dark:text-emerald-400"
      : rightTone === "neg"
        ? "text-rose-600 dark:text-rose-400"
        : "text-muted-foreground";

  // Unique-enough id for the gradient stop.
  const gradId = `sp-${pillar}-${ticker}`.replace(/[^a-zA-Z0-9_-]/g, "_");

  return (
    <li className="border-b border-border/40 last:border-b-0 relative">
      {sl.length > 1 && (
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={trendStroke} stopOpacity={0} />
              <stop offset="100%" stopColor={trendStroke} stopOpacity={0.4} />
            </linearGradient>
          </defs>
          <polyline
            points={points}
            fill="none"
            stroke={`url(#${gradId})`}
            strokeWidth={1.2}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}
      <Link
        to={`/stocks/${encodeURIComponent(ticker)}`}
        className="relative z-10 flex items-center gap-2 px-3 py-1 hover:bg-accent/30 transition-colors leading-tight min-w-0"
      >
        <span className="shrink-0 w-4 text-center text-[12px]" aria-hidden>
          {pillar}
        </span>
        <StockIdentity ticker={ticker} name={name} />
        <div className="text-right shrink-0 leading-tight">
          <div className={cn("text-[12.5px] font-bold tabular-nums", toneCls)}>
            {rightLine1}
          </div>
          {rightLine2 && (
            <div className={cn("text-[10px] font-semibold tabular-nums", toneCls)}>
              {rightLine2}
            </div>
          )}
        </div>
      </Link>
    </li>
  );
}

/* ─── Empty-state helper ────────────────────────────────────────────────── */

function ColumnHeader({ label }: { label: string }) {
  return (
    <div className="shrink-0 px-2.5 py-1 text-[10.5px] uppercase tracking-[0.16em] font-bold text-muted-foreground border-b bg-muted/40">
      {label}
    </div>
  );
}

/* ─── Card ──────────────────────────────────────────────────────────────── *
 *
 * Was: 3-tab card (52w events / Volume spikes / Spikes ⚡). User
 * dropped the "Spikes ⚡" tab and asked for the remaining two views
 * to render as side-by-side columns with the same compact
 * sparkline-bg row styling that the Spikes tab used.
 *
 * 52w events column: shows a mix of new highs (📈) and lows (📉).
 * Volume spikes column: shows volume ratio + change %.
 */
export function FiftyTwoWeekVolCard({ movers }: Props) {
  const highs = movers.new_52w_high.slice(0, 6);
  const lows = movers.new_52w_low.slice(0, 4);
  const spikes = movers.volume_spikes.slice(0, 10);

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle icon={LineChart} label="52w & volume events" />
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {/* Column 1: 52w events */}
          <div className="flex flex-col min-h-0 min-w-0">
            <ColumnHeader
              label={`52w events · ${movers.new_52w_high.length} highs · ${movers.new_52w_low.length} lows`}
            />
            {highs.length === 0 && lows.length === 0 ? (
              <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
                Nessun evento
              </div>
            ) : (
              <ul className="flex-1 overflow-y-auto">
                {highs.map((m: Mover) => (
                  <SparkRow
                    key={`h-${m.ticker}`}
                    ticker={m.ticker}
                    name={m.name}
                    sparkline={m.sparkline}
                    rightLine1={`$${m.last_close.toFixed(2)}`}
                    rightTone="pos"
                    pillar="📈"
                  />
                ))}
                {lows.map((m: Mover) => (
                  <SparkRow
                    key={`l-${m.ticker}`}
                    ticker={m.ticker}
                    name={m.name}
                    sparkline={m.sparkline}
                    rightLine1={`$${m.last_close.toFixed(2)}`}
                    rightTone="neg"
                    pillar="📉"
                  />
                ))}
              </ul>
            )}
          </div>

          {/* Column 2: Volume spikes */}
          <div className="flex flex-col min-h-0 min-w-0">
            <ColumnHeader label={`Volume spikes · ${movers.volume_spikes.length}`} />
            {spikes.length === 0 ? (
              <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
                Nessuno spike
              </div>
            ) : (
              <ul className="flex-1 overflow-y-auto">
                {spikes.map((m: VolumeSpike) => {
                  const change = m.change_pct ?? 0;
                  const tone = change > 0 ? "pos" : change < 0 ? "neg" : "neutral";
                  return (
                    <SparkRow
                      key={m.ticker}
                      ticker={m.ticker}
                      name={m.name}
                      sparkline={m.sparkline}
                      rightLine1={`${m.vol_ratio.toFixed(1)}× vol`}
                      rightLine2={`${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                      rightTone={tone}
                      pillar="⚡"
                    />
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
