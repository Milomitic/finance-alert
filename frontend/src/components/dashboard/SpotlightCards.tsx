import { Bell, Sparkles, TrendingDown, TrendingUp, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import type { Mover, VolumeSpike } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { useSpotlight } from "@/hooks/useSpotlight";
import { cn } from "@/lib/utils";

interface ListCardProps {
  label: string;
  icon: typeof Bell;
  accent: string;
  items: Array<{ ticker: string; name?: string; subtitle: string; subtitleColor?: string }>;
  emptyText: string;
  sparkline?: number[];
}

function ListCard({ label, icon: Icon, accent, items, emptyText, sparkline }: ListCardProps) {
  const sparkData = (sparkline ?? []).map((v, i) => ({ idx: i, v }));
  const trendUp = sparkData.length >= 2 && sparkData[sparkData.length - 1].v >= sparkData[0].v;

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

        {/* Rows — fill vertically and distribute evenly (with cap) */}
        {items.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground text-center">
            {emptyText}
          </div>
        ) : (
          <ul className="flex-1 flex flex-col justify-center divide-y divide-border/50">
            {items.map((it) => (
              <li key={it.ticker} className="flex-1 max-h-[60px] flex">
                <Link
                  to={`/stocks/${encodeURIComponent(it.ticker)}`}
                  className="flex items-center gap-2 px-3 py-1 hover:bg-accent/30 transition-colors flex-1"
                >
                  <StockLogo ticker={it.ticker} size="xs" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-bold tabular-nums truncate leading-tight">{it.ticker}</div>
                    {it.name && (
                      <div className="text-[10px] text-muted-foreground truncate leading-tight" title={it.name}>{it.name}</div>
                    )}
                  </div>
                  <span
                    className={cn(
                      "text-sm font-semibold tabular-nums shrink-0",
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

        {/* Sparkline footer — fade visual showing trend of the top item */}
        {sparkData.length > 1 && (
          <div className="h-10 px-1 pb-1 shrink-0 relative">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={`spark-grad-${label.replace(/\s/g, "")}`} x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor={trendUp ? "#16a34a" : "#dc2626"} stopOpacity={0} />
                    <stop offset="100%" stopColor={trendUp ? "#16a34a" : "#dc2626"} stopOpacity={1} />
                  </linearGradient>
                </defs>
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke={`url(#spark-grad-${label.replace(/\s/g, "")})`}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
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

export function SpotlightCards() {
  const market = useMarketSummary();
  const spotlight = useSpotlight();

  // Loading: show 4 skeleton cards
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
  const topGainerCard = spotCards.find((c) => c.type === "top_gainer");
  const topLoserCard = spotCards.find((c) => c.type === "top_loser");
  const volSpikeCard = spotCards.find((c) => c.type === "vol_spike");
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

  // Build the lists
  const gainersItems = gainers.map((m) => {
    const f = fmtChange(m.change_pct);
    return { ticker: m.ticker, name: m.name, subtitle: f.text, subtitleColor: f.color };
  });
  const losersItems = losers.map((m) => {
    const f = fmtChange(m.change_pct);
    return { ticker: m.ticker, name: m.name, subtitle: f.text, subtitleColor: f.color };
  });
  const volItems = volSpikes.map((v) => ({
    ticker: v.ticker,
    name: v.name,
    subtitle: `${v.vol_ratio.toFixed(1)}× vol`,
    subtitleColor: "text-blue-600 dark:text-blue-400",
  }));
  const mostAlertedItems = mostAlertedCard
    ? [{
        ticker: mostAlertedCard.ticker,
        name: undefined,
        subtitle: `${mostAlertedCard.alerts_count ?? 0} alert ult. 7gg`,
        subtitleColor: "text-amber-600 dark:text-amber-400",
      }]
    : [];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
      <ListCard
        label="Top gainers"
        icon={TrendingUp}
        accent="text-green-600 dark:text-green-400"
        items={gainersItems}
        emptyText="Nessun gainer oggi"
        sparkline={topGainerCard?.sparkline}
      />
      <ListCard
        label="Top losers"
        icon={TrendingDown}
        accent="text-red-600 dark:text-red-400"
        items={losersItems}
        emptyText="Nessun loser oggi"
        sparkline={topLoserCard?.sparkline}
      />
      <ListCard
        label="Volume spikes"
        icon={Zap}
        accent="text-blue-600 dark:text-blue-400"
        items={volItems}
        emptyText="Nessun volume spike"
        sparkline={volSpikeCard?.sparkline}
      />
      <ListCard
        label="Most alerted 7d"
        icon={Bell}
        accent="text-amber-600 dark:text-amber-400"
        items={mostAlertedItems}
        emptyText="Nessun alert negli ultimi 7gg"
        sparkline={mostAlertedCard?.sparkline}
      />
    </div>
  );
}
