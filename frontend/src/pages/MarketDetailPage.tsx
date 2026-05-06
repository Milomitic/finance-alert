import {
  AlertCircle,
  Bitcoin,
  CircleDot,
  Coins,
  Droplet,
  Flame,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { MarketChart } from "@/components/market/MarketChart";
import { MultiTimeframeKpisCard } from "@/components/MultiTimeframeKpisCard";
import { RangeSelector } from "@/components/stock/RangeSelector";
import { useMarketDetail } from "@/hooks/useMarketDetail";
import { cn } from "@/lib/utils";

/* ─── Per-symbol icon overrides ──────────────────────────────────────────
 *
 * Mirrors the LiveAssetsPanel mapping so the detail page header uses
 * the exact same brand glyph (Bitcoin orange, Gold amber Coins, Oil
 * slate Droplet, etc.) the user clicked from. Indices use their
 * country flag instead — no icon override needed.
 */
type IconRender = {
  Component: React.ComponentType<{ className?: string }>;
  color: string;
};

const SYMBOL_ICON: Record<string, IconRender> = {
  "GC=F": { Component: Coins, color: "text-amber-500" },
  "SI=F": { Component: Coins, color: "text-zinc-400 dark:text-zinc-300" },
  "CL=F": { Component: Droplet, color: "text-slate-700 dark:text-slate-200" },
  "NG=F": { Component: Flame, color: "text-orange-500" },
  "BTC-USD": { Component: Bitcoin, color: "text-orange-500" },
  "ETH-USD": { Component: EthereumIcon, color: "text-indigo-500 dark:text-indigo-400" },
};

const CATEGORY_FALLBACK_ICON: Record<string, LucideIcon> = {
  index: Globe,
  commodity: CircleDot,
  crypto: Bitcoin,
};

function EthereumIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 256 416" className={className} fill="currentColor" aria-hidden>
      <path d="M127.961 0L125.166 9.5v275.668l2.795 2.79 127.962-75.638z" opacity="0.8" />
      <path d="M127.962 0L0 212.32l127.962 75.639V154.158z" />
      <path d="M127.961 312.187l-1.575 1.92v98.199l1.575 4.6L256 236.587z" opacity="0.8" />
      <path d="M127.962 416.905v-104.72L0 236.587z" />
      <path d="M127.961 287.958l127.96-75.637-127.96-58.162z" opacity="0.5" />
      <path d="M0 212.32l127.96 75.638V154.159z" opacity="0.65" />
    </svg>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────
 *
 * `/markets/:symbol` route — drilldown for non-stock instruments
 * (indices, commodities, crypto) listed in the dashboard's
 * LiveAssetsPanel. Renders header (icon + name + live price + Δ%) +
 * range selector + candlestick chart + KPI strip (52w high/low, etc.).
 *
 * Doesn't show fundamentals / news / alerts / insiders — those don't
 * make sense for ETH or WTI crude. Just price + range.
 */
export default function MarketDetailPage() {
  const { symbol = "" } = useParams<{ symbol: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  // v2: default to "1d" timeframe (was "1y" range key — semantically
  // similar at the daily-resolution level, but the new vocabulary is
  // timeframe-based: 30m/1h/1d/1w/1m/all instead of 1m/3m/.../all
  // ranges. See `services/timeframe_service`.
  const range = searchParams.get("range") ?? "1d";
  const decoded = decodeURIComponent(symbol);
  const q = useMarketDetail(decoded, range);

  if (q.isError || (!q.isLoading && !q.data)) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center gap-3 text-sm">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>
            Errore nel caricamento di <strong>{decoded}</strong>. Verifica
            che il simbolo sia tra gli asset live tracciati.
          </span>
        </CardContent>
      </Card>
    );
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="space-y-3">
        <Card>
          <CardContent className="p-6 h-[120px] animate-pulse bg-muted/40" />
        </Card>
        <Card>
          <CardContent className="p-4 h-[460px] animate-pulse bg-muted/40" />
        </Card>
      </div>
    );
  }

  const d = q.data;
  // Quote takes precedence for "live" price; falls back to last_close
  // when the quote service couldn't produce one (rate limit, error).
  const livePrice = d.quote?.price ?? d.last_close;
  const changePct = d.quote?.change_pct ?? d.change_pct;
  const isLive =
    d.quote?.market_state === "OPEN" && d.quote?.error == null;
  const symbolIcon = SYMBOL_ICON[d.symbol];
  const FallbackIcon = CATEGORY_FALLBACK_ICON[d.category] ?? Globe;
  // Crypto/commodity have no meaningful volume from yfinance for
  // `=F` futures — show volume only when at least one bar reports it.
  const hasVolume = d.bars.some((b) => (b.volume ?? 0) > 0);

  return (
    <div className="space-y-3">
      {/* Header — identity + live price */}
      <Card>
        <CardContent className="p-4 flex items-center gap-4 flex-wrap">
          <span className="shrink-0 inline-flex items-center justify-center h-12 w-12 rounded-full bg-muted/50">
            {d.flag ? (
              <img
                src={`/flags/${d.flag}.svg`}
                alt={d.flag}
                width={40}
                height={28}
                style={{ width: "40px", height: "28px", objectFit: "cover" }}
                className="rounded-sm ring-1 ring-border/60"
                aria-hidden
              />
            ) : symbolIcon ? (
              <symbolIcon.Component
                className={cn("h-7 w-7", symbolIcon.color)}
              />
            ) : (
              <FallbackIcon className="h-7 w-7 text-muted-foreground" />
            )}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-semibold tracking-tight leading-tight truncate">
                {d.name}
              </h1>
              <span className="text-xs text-muted-foreground tabular-nums">
                {d.symbol}
              </span>
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {d.category}
              </span>
              {isLive && (
                <span
                  className="relative inline-flex h-2 w-2 ml-1"
                  title="Mercato aperto · prezzo live"
                >
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              {d.category === "index"
                ? "Indice di mercato"
                : d.category === "commodity"
                  ? "Materia prima"
                  : "Criptovaluta"}
            </p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold tabular-nums leading-none">
              {livePrice != null
                ? formatMarketPrice(livePrice, d.category)
                : "—"}
            </div>
            {changePct != null && (
              <div
                className={cn(
                  "text-sm font-semibold tabular-nums mt-1",
                  changePct > 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : changePct < 0
                      ? "text-rose-600 dark:text-rose-400"
                      : "text-muted-foreground",
                )}
              >
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(2)}%
              </div>
            )}
            {d.quote?.currency && (
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground/70 mt-0.5">
                {d.quote.currency}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* KPI strip — 52w high/low + range high/low.
          The 52w numbers stay constant across range changes, the
          range numbers reflect what's on the chart at the moment. */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCell
          label="52W high"
          value={d.high_52w != null ? formatMarketPrice(d.high_52w, d.category) : "—"}
        />
        <KpiCell
          label="52W low"
          value={d.low_52w != null ? formatMarketPrice(d.low_52w, d.category) : "—"}
        />
        <KpiCell
          label="Range high"
          value={d.high_window != null ? formatMarketPrice(d.high_window, d.category) : "—"}
        />
        <KpiCell
          label="Range low"
          value={d.low_window != null ? formatMarketPrice(d.low_window, d.category) : "—"}
        />
      </div>

      {/* Chart */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <RangeSelector
              value={range}
              onChange={(r) => setSearchParams({ range: r })}
            />
            <span className="text-xs text-muted-foreground">
              {d.bars.length} bar · range {d.range_key}
            </span>
          </div>
          {d.bars.length < 2 ? (
            <div className="h-[460px] flex items-center justify-center text-sm text-muted-foreground border border-border/50 rounded-md">
              Dati insufficienti per il chart
            </div>
          ) : (
            <div className="h-[460px]">
              {/* `key={range}` forces a clean remount on range switch
                  — same dance as the stock-detail PriceChart to avoid
                  stale fitContent races. */}
              <MarketChart
                key={range}
                bars={d.bars}
                showVolume={hasVolume}
                timeframe={range}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Multi-timeframe KPI comparison — same indicators (RSI 14,
          BB 20, SMA 20/50/200, MACD 12/26/9) computed across all 6
          timeframes side-by-side so the user can spot
          short-vs-long-term disagreements. */}
      <MultiTimeframeKpisCard ticker={d.symbol} kind="market" />
    </div>
  );
}

function KpiCell({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="text-lg font-bold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}

/** Format a market price by category. Indices and commodities at 2dp;
 *  crypto at variable precision (BTC at 0dp, low-cap cryptos at 4dp). */
function formatMarketPrice(v: number, category: string): string {
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (category === "crypto") {
    if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
    if (abs >= 1) return v.toFixed(2);
    return v.toFixed(4);
  }
  if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  return v.toFixed(2);
}
