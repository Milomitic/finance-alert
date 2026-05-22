import { Layers } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { EtfHolding } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useEtfHoldings } from "@/hooks/useEtfHoldings";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/* ─── EtfHoldingsCard ────────────────────────────────────────────────────────
 *
 * For an ETF, lists its top components with: weight (bar), a ~30-day
 * sparkline (trend), live price, and the day variation (colored). Renders
 * nothing for regular equities (`is_etf=false`) — the hook is cheap there
 * (backend caches the non-ETF result). A header chip shows the weighted-
 * average variation of the components as a proxy for the ETF's move.
 */
export function EtfHoldingsCard({ ticker }: Props) {
  const q = useEtfHoldings(ticker);
  const data = q.data;

  // Sort by weight desc and scale the bars to the heaviest holding so
  // small leveraged-ETF weights stay legible.
  const holdings = useMemo(
    () => [...(data?.holdings ?? [])].sort((a, b) => b.weight - a.weight),
    [data?.holdings],
  );
  const maxWeight = holdings[0]?.weight || 1;

  // Hide entirely for non-ETFs (or while we don't yet know). Showing a
  // skeleton for every equity would add a phantom card to most pages.
  if (q.isLoading || !data || !data.is_etf || holdings.length === 0) {
    return null;
  }

  const wChange = data.weighted_change_pct;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="px-4 py-3 border-b bg-muted/20 flex items-center justify-between gap-2">
          <SectionTitle
            icon={Layers}
            label="Componenti ETF"
            right={
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {holdings.length} posizioni
              </span>
            }
          />
          {wChange != null && (
            <span
              className={cn(
                "shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[12px] font-semibold tabular-nums",
                wChange >= 0
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800/60"
                  : "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800/60",
              )}
              title="Variazione media delle componenti, pesata per quota — proxy del movimento dell'ETF"
            >
              media pesata {wChange >= 0 ? "+" : ""}
              {wChange.toFixed(2)}%
            </span>
          )}
        </div>

        <ul className="divide-y divide-border/40 max-h-[460px] overflow-y-auto">
          {holdings.map((h) => (
            <HoldingRow key={h.symbol} h={h} maxWeight={maxWeight} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function HoldingRow({ h, maxWeight }: { h: EtfHolding; maxWeight: number }) {
  const up = h.change_pct != null ? h.change_pct >= 0 : sparkUp(h.sparkline);
  const changeColor =
    h.change_pct == null
      ? "text-muted-foreground"
      : h.change_pct >= 0
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-rose-600 dark:text-rose-400";
  const barPct = maxWeight > 0 ? Math.max(3, (h.weight / maxWeight) * 100) : 0;

  const inner = (
    <>
      {/* Identity */}
      <div className="flex items-center gap-2 min-w-0">
        <StockLogo ticker={h.symbol} size="xs" />
        <div className="min-w-0">
          <div className="text-sm font-bold tabular-nums leading-tight truncate">
            {h.symbol}
          </div>
          {h.name && (
            <div
              className="text-[11px] text-muted-foreground truncate leading-tight"
              title={h.name}
            >
              {h.name}
            </div>
          )}
        </div>
      </div>

      {/* Weight bar */}
      <div className="hidden sm:flex items-center gap-2 w-32">
        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full bg-sky-500 dark:bg-sky-400 rounded-full"
            style={{ width: `${barPct}%` }}
          />
        </div>
        <span className="w-11 text-right text-[11px] tabular-nums text-muted-foreground">
          {(h.weight * 100).toFixed(1)}%
        </span>
      </div>

      {/* Trend sparkline */}
      <div className="hidden md:block w-16 shrink-0">
        <MiniSpark closes={h.sparkline} up={up} />
      </div>

      {/* Price + day variation */}
      <div className="text-right tabular-nums shrink-0 w-[72px]">
        <div className="text-sm font-semibold leading-tight">
          {h.price != null ? `$${h.price.toFixed(2)}` : "—"}
        </div>
        <div className={cn("text-[12px] font-semibold leading-tight", changeColor)}>
          {h.change_pct != null
            ? `${h.change_pct >= 0 ? "+" : ""}${h.change_pct.toFixed(2)}%`
            : "—"}
        </div>
      </div>
    </>
  );

  const grid =
    "grid grid-cols-[minmax(0,1fr)_auto_auto] sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 px-4 py-2";

  // Catalog holdings deep-link to their stock page; off-catalog ones are
  // static rows (no detail page exists for them).
  return (
    <li>
      {h.in_catalog ? (
        <Link to={`/stocks/${encodeURIComponent(h.symbol)}`} className={cn(grid, "hover:bg-accent/30 transition-colors")}>
          {inner}
        </Link>
      ) : (
        <div className={grid}>{inner}</div>
      )}
    </li>
  );
}

function sparkUp(closes: number[]): boolean {
  if (closes.length < 2) return true;
  return closes[closes.length - 1] >= closes[0];
}

/** Minimal 30-day sparkline. Green up / red down per the row's signal. */
function MiniSpark({ closes, up }: { closes: number[]; up: boolean }) {
  if (!closes || closes.length < 2) {
    return <span className="block text-center text-muted-foreground/40 text-xs">—</span>;
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 64;
  const H = 22;
  const points = closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="overflow-visible" aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke={up ? "#16a34a" : "#dc2626"}
        strokeWidth={1.3}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
