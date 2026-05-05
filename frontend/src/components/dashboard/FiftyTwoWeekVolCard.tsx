import { LineChart } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { IndexBadge } from "@/components/dashboard/IndexBadge";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
}

type TabKey = "hilo" | "vol" | "vol-spark";

const TABS: { key: TabKey; label: string; title: string }[] = [
  {
    key: "hilo",
    label: "52w events",
    title: "Stock che oggi raggiungono nuovi massimi/minimi a 52 settimane",
  },
  {
    key: "vol",
    label: "Volume spikes",
    title: "Stock con volume oggi maggiore di 2× la media a 20 giorni",
  },
  {
    key: "vol-spark",
    label: "Spikes ⚡",
    title: "Stesso elenco con grafico in dissolvenza per riga",
  },
];

function ListRow({ m, kind }: { m: Mover; kind: "high" | "low" }) {
  const arrow = kind === "high" ? "📈" : "📉";
  const color = kind === "high" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";
  return (
    <tr className="border-b border-border/50 hover:bg-muted/40 transition-colors">
      <td className="px-2 py-1.5">{arrow}</td>
      <td className="px-3 py-1.5 font-semibold">
        <Link to={`/stocks/${encodeURIComponent(m.ticker)}`} className="inline-flex items-start gap-2 hover:underline">
          <StockLogo ticker={m.ticker} size="xs" />
          <div className="min-w-0">
            <div>{m.ticker}</div>
            <div className="text-[10px] text-muted-foreground font-normal truncate max-w-[120px]" title={m.name}>{m.name}</div>
          </div>
        </Link>
      </td>
      <td className="px-2 py-1.5"><IndexBadge code={m.index} size="xs" /></td>
      <td className={`px-3 py-1.5 text-right tabular-nums ${color}`}>${m.last_close.toFixed(2)}</td>
    </tr>
  );
}

function VolRow({ m }: { m: VolumeSpike }) {
  const change = m.change_pct ?? 0;
  const positive = change >= 0;
  return (
    <tr className="border-b border-border/50 hover:bg-muted/40 transition-colors">
      <td className="px-3 py-1.5 font-semibold">
        <Link to={`/stocks/${encodeURIComponent(m.ticker)}`} className="inline-flex items-start gap-2 hover:underline">
          <StockLogo ticker={m.ticker} size="xs" />
          <div className="min-w-0">
            <div>{m.ticker}</div>
            <div className="text-[10px] text-muted-foreground font-normal truncate max-w-[120px]" title={m.name}>{m.name}</div>
          </div>
        </Link>
      </td>
      <td className="px-2 py-1.5"><IndexBadge code={m.index} size="xs" /></td>
      <td className="px-3 py-1.5 text-right tabular-nums">{m.vol_ratio.toFixed(1)}×</td>
      <td className={`px-3 py-1.5 text-right tabular-nums ${positive ? "text-green-600" : "text-red-600"}`}>
        {change >= 0 ? "+" : ""}{change.toFixed(2)}%
      </td>
    </tr>
  );
}

/**
 * Compact sparkline-rich row for the 3rd tab. Each row shows the per-stock
 * 30-day price sparkline as a faded background, in the style of the (now
 * removed) SpotlightCards Volume Spikes column.
 */
function VolSparkRow({ m }: { m: VolumeSpike }) {
  const sl = m.sparkline ?? [];
  const min = sl.length ? Math.min(...sl) : 0;
  const max = sl.length ? Math.max(...sl) : 1;
  const range = max - min || 1;
  const W = 100, H = 30;
  const points = sl
    .map((v, i) => `${((i / Math.max(1, sl.length - 1)) * W).toFixed(2)},${(H - ((v - min) / range) * H).toFixed(2)}`)
    .join(" ");
  const change = m.change_pct ?? 0;
  const trend = change >= 0 ? "#16a34a" : "#dc2626";
  return (
    <li className="border-b border-border/50 last:border-b-0 relative">
      {sl.length > 1 && (
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={`sp-vol-${m.ticker}`} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={trend} stopOpacity={0} />
              <stop offset="100%" stopColor={trend} stopOpacity={0.45} />
            </linearGradient>
          </defs>
          <polyline points={points} fill="none" stroke={`url(#sp-vol-${m.ticker})`} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="relative z-10 flex items-center gap-2 px-3 py-2 hover:bg-accent/30 transition-colors"
      >
        <StockLogo ticker={m.ticker} size="xs" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-bold tabular-nums leading-tight">{m.ticker}</div>
          {m.name && (
            <div className="text-[10px] text-muted-foreground truncate leading-tight" title={m.name}>{m.name}</div>
          )}
        </div>
        <span className="text-sm font-semibold tabular-nums shrink-0 text-blue-600 dark:text-blue-400">
          {m.vol_ratio.toFixed(1)}× vol
        </span>
      </Link>
    </li>
  );
}

export function FiftyTwoWeekVolCard({ movers }: Props) {
  // Was: Radix Tabs with horizontal triggers — different visual language than
  // the rest of the dashboard, which uses a plain button strip with equal-
  // width tabs and the active state highlighted by a solid background.
  // Switched to the canonical pattern so this card matches TopMovers and
  // TopPicks side-by-side.
  const [tab, setTab] = useState<TabKey>("hilo");

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle icon={LineChart} label="52w & volume events" />
        </div>

        {/* Canonical button-strip tabs (matches TopMovers / TopPicks). */}
        <div className="flex shrink-0 border-b">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              title={t.title}
              className={cn(
                "flex-1 text-[11px] font-bold uppercase tracking-wider py-1.5 transition-colors border-r last:border-r-0",
                tab === t.key
                  ? "bg-background shadow-inner text-foreground"
                  : "text-muted-foreground hover:bg-muted/30",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body — single content slot per active tab */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {tab === "hilo" && (
            <>
              <div className="px-3 py-2 text-sm text-muted-foreground">
                📈 {movers.new_52w_high.length} highs · 📉 {movers.new_52w_low.length} lows
              </div>
              <table className="w-full text-sm">
                <tbody>
                  {movers.new_52w_high.map((m) => <ListRow key={`h-${m.ticker}`} m={m} kind="high" />)}
                  {movers.new_52w_low.map((m) => <ListRow key={`l-${m.ticker}`} m={m} kind="low" />)}
                  {movers.new_52w_high.length === 0 && movers.new_52w_low.length === 0 && (
                    <tr><td colSpan={4} className="text-sm text-muted-foreground text-center py-6">Nessun evento</td></tr>
                  )}
                </tbody>
              </table>
            </>
          )}
          {tab === "vol" && (
            <table className="w-full text-sm">
              <tbody>
                {movers.volume_spikes.map((m) => <VolRow key={m.ticker} m={m} />)}
                {movers.volume_spikes.length === 0 && (
                  <tr><td colSpan={4} className="text-sm text-muted-foreground text-center py-6">Nessuno spike</td></tr>
                )}
              </tbody>
            </table>
          )}
          {tab === "vol-spark" && (
            movers.volume_spikes.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-6">Nessuno spike</div>
            ) : (
              <ul>
                {movers.volume_spikes.slice(0, 8).map((m) => <VolSparkRow key={m.ticker} m={m} />)}
              </ul>
            )
          )}
        </div>
      </CardContent>
    </Card>
  );
}
