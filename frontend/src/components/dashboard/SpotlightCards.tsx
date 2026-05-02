import { Bell, Sparkles, TrendingDown, TrendingUp, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import type { SpotlightCard } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { useSpotlight } from "@/hooks/useSpotlight";

const TYPE_META: Record<SpotlightCard["type"], { label: string; icon: typeof Bell; accent: string }> = {
  top_gainer: {
    label: "Top gainer",
    icon: TrendingUp,
    accent: "text-green-600 dark:text-green-400",
  },
  top_loser: {
    label: "Top loser",
    icon: TrendingDown,
    accent: "text-red-600 dark:text-red-400",
  },
  most_alerted_7d: {
    label: "Most alerted 7d",
    icon: Bell,
    accent: "text-amber-600 dark:text-amber-400",
  },
  vol_spike: {
    label: "Volume spike",
    icon: Zap,
    accent: "text-blue-600 dark:text-blue-400",
  },
};

function CardItem({ card }: { card: SpotlightCard }) {
  const meta = TYPE_META[card.type];
  const Icon = meta.icon;
  const sparkData = card.sparkline.map((v, i) => ({ idx: i, v }));
  const trendUp = sparkData.length >= 2 && sparkData[sparkData.length - 1].v >= sparkData[0].v;
  const subtitle =
    card.type === "top_gainer" || card.type === "top_loser"
      ? `${card.change_pct! >= 0 ? "+" : ""}${card.change_pct?.toFixed(2)}%`
      : card.type === "vol_spike"
        ? `${card.vol_ratio?.toFixed(1)}× volume`
        : `${card.alerts_count} alerts last 7d`;

  return (
    <Link to={`/stocks/${card.ticker}`} className="block">
      <Card className="hover:bg-accent/30 transition-colors cursor-pointer h-full">
        <CardContent className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <Icon className={`h-3.5 w-3.5 ${meta.accent}`} />
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-semibold">
              {meta.label}
            </span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <StockLogo ticker={card.ticker} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="font-bold text-sm">{card.ticker}</div>
              <div className={`text-xs ${meta.accent}`}>{subtitle}</div>
            </div>
            {card.last_close != null && (
              <div className="text-xs tabular-nums text-muted-foreground">
                ${card.last_close.toFixed(2)}
              </div>
            )}
          </div>
          {sparkData.length > 0 && (
            <div className="h-8 mt-1">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparkData}>
                  <Line
                    type="monotone"
                    dataKey="v"
                    stroke={trendUp ? "#16a34a" : "#dc2626"}
                    strokeWidth={1.5}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}

export function SpotlightCards() {
  const q = useSpotlight();
  const cards = q.data?.cards ?? [];

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4 min-h-[120px] animate-pulse bg-muted/40" />
      </Card>
    );
  }

  if (cards.length === 0) {
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

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
      {cards.map((c) => <CardItem key={c.type} card={c} />)}
    </div>
  );
}
