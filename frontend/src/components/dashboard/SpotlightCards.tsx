import { Bell, Sparkles, TrendingDown, TrendingUp, Zap } from "lucide-react";
import { Link } from "react-router-dom";

import type { Mover, VolumeSpike } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { useSpotlight } from "@/hooks/useSpotlight";
import { cn } from "@/lib/utils";

interface RowItem {
  ticker: string;
  name?: string;
  subtitle: string;
  subtitleColor?: string;
  sparkline?: number[];
  /** Direction hint for the sparkline color when sparkline data is present. */
  trend?: "up" | "down" | "neutral";
}

interface ListCardProps {
  label: string;
  icon: typeof Bell;
  accent: string;
  items: RowItem[];
  emptyText: string;
}

/**
 * Faded sparkline rendered as a background layer behind a row.
 * Uses a horizontal alpha gradient (transparent left → opaque right) so the
 * line "fades in" while not overpowering the foreground text.
 */
function RowSparkline({ values, trend }: { values: number[]; trend: "up" | "down" | "neutral" }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  // Fixed viewBox; SVG scales with preserveAspectRatio=none to fill the row.
  const W = 100;
  const H = 30;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const stroke = trend === "up" ? "#16a34a" : trend === "down" ? "#dc2626" : "#94a3b8";
  // gradId must be unique per render; we derive a short hash from the values
  // so two rows with the same series share the same gradient (cheap).
  const gradId = `spark-${trend}-${values.length}-${Math.round(values[0] * 1000)}`;
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity={0} />
          <stop offset="60%" stopColor={stroke} stopOpacity={0.18} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0.45} />
        </linearGradient>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth={1.4}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function ListCard({ label, icon: Icon, accent, items, emptyText }: ListCardProps) {
  return (
    <Card className="overflow-hidden h-full">
      <CardContent className="p-0 flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-2 px-3 py-2 border-b bg-muted/30 shrink-0">
          <Icon className={cn("h-3.5 w-3.5", accent)} />
          <span className={cn("text-[10px] uppercase tracking-wider font-bold", accent)}>
            {label}
          </span>
          <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
            {items.length > 0 ? `Top ${items.length}` : ""}
          </span>
        </div>

        {/* Rows — each with its own faded sparkline background */}
        {items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground text-center">
            {emptyText}
          </div>
        ) : (
          <ul className="flex-1 flex flex-col justify-center divide-y divide-border/50">
            {items.map((it) => (
              <li key={it.ticker} className="flex-1 max-h-[60px] flex relative">
                {it.sparkline && it.sparkline.length > 1 && (
                  <RowSparkline values={it.sparkline} trend={it.trend ?? "neutral"} />
                )}
                <Link
                  to={`/stocks/${encodeURIComponent(it.ticker)}`}
                  className="relative z-10 flex items-center gap-2 pl-3 pr-3 py-1 hover:bg-accent/30 transition-colors flex-1 min-w-0"
                >
                  <StockLogo ticker={it.ticker} size="xs" />
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <div className="text-sm font-bold tabular-nums truncate leading-tight">{it.ticker}</div>
                    {it.name && (
                      <div className="text-[10px] text-muted-foreground truncate leading-tight" title={it.name}>{it.name}</div>
                    )}
                  </div>
                  <span
                    className={cn(
                      "text-sm font-semibold tabular-nums shrink-0 ml-auto text-right",
                      it.subtitleColor ?? "text-muted-foreground",
                    )}
                  >
                    {it.subtitle}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function fmtChange(c: number | null | undefined): { text: string; color: string } {
  if (c == null) return { text: "—", color: "text-muted-foreground" };
  const sign = c >= 0 ? "+" : "";
  return {
    text: `${sign}${c.toFixed(2)}%`,
    color: c > 0 ? "text-green-600 dark:text-green-400" : c < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground",
  };
}

function trendOf(change: number | null | undefined): "up" | "down" | "neutral" {
  if (change == null) return "neutral";
  return change > 0 ? "up" : change < 0 ? "down" : "neutral";
}

export function SpotlightCards() {
  const market = useMarketSummary();
  const spotlight = useSpotlight();

  if (market.isLoading || spotlight.isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent className="p-4 min-h-[260px] animate-pulse bg-muted/40" />
          </Card>
        ))}
      </div>
    );
  }

  const movers = market.data?.movers;
  const gainers: Mover[] = (movers?.gainers ?? []).slice(0, 5);
  const losers: Mover[] = (movers?.losers ?? []).slice(0, 5);
  const volSpikes: VolumeSpike[] = (movers?.volume_spikes ?? []).slice(0, 5);
  const spotCards = spotlight.data?.cards ?? [];
  const mostAlertedCard = spotCards.find((c) => c.type === "most_alerted_7d");

  const noData =
    gainers.length === 0 && losers.length === 0 && volSpikes.length === 0 && !mostAlertedCard;

  if (noData) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-6 flex flex-col items-center justify-center text-center min-h-[120px]">
          <Sparkles className="h-5 w-5 text-muted-foreground mb-2" />
          <div className="text-sm text-muted-foreground">
            Nessun stock in spotlight (esegui uno scan o attendi alert).
          </div>
        </CardContent>
      </Card>
    );
  }

  const gainersItems: RowItem[] = gainers.map((m) => {
    const f = fmtChange(m.change_pct);
    return {
      ticker: m.ticker, name: m.name,
      subtitle: f.text, subtitleColor: f.color,
      sparkline: m.sparkline, trend: trendOf(m.change_pct),
    };
  });
  const losersItems: RowItem[] = losers.map((m) => {
    const f = fmtChange(m.change_pct);
    return {
      ticker: m.ticker, name: m.name,
      subtitle: f.text, subtitleColor: f.color,
      sparkline: m.sparkline, trend: trendOf(m.change_pct),
    };
  });
  const volItems: RowItem[] = volSpikes.map((v) => ({
    ticker: v.ticker, name: v.name,
    subtitle: `${v.vol_ratio.toFixed(1)}× vol`,
    subtitleColor: "text-blue-600 dark:text-blue-400",
    sparkline: v.sparkline, trend: trendOf(v.change_pct),
  }));
  const mostAlertedItems: RowItem[] = mostAlertedCard
    ? [{
        ticker: mostAlertedCard.ticker,
        name: undefined,
        subtitle: `${mostAlertedCard.alerts_count ?? 0} alert ult. 7gg`,
        subtitleColor: "text-amber-600 dark:text-amber-400",
        sparkline: mostAlertedCard.sparkline,
        trend: "neutral",
      }]
    : [];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
      <ListCard label="Top gainers" icon={TrendingUp}
        accent="text-green-600 dark:text-green-400"
        items={gainersItems} emptyText="Nessun gainer oggi" />
      <ListCard label="Top losers" icon={TrendingDown}
        accent="text-red-600 dark:text-red-400"
        items={losersItems} emptyText="Nessun loser oggi" />
      <ListCard label="Volume spikes" icon={Zap}
        accent="text-blue-600 dark:text-blue-400"
        items={volItems} emptyText="Nessun volume spike" />
      <ListCard label="Most alerted 7d" icon={Bell}
        accent="text-amber-600 dark:text-amber-400"
        items={mostAlertedItems} emptyText="Nessun alert negli ultimi 7gg" />
    </div>
  );
}
