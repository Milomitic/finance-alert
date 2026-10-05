import { Layers } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { EtfHolding } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useEtfHoldings } from "@/hooks/useEtfHoldings";
import { formatMoney } from "@/lib/money";
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
 *
 * Una riga per componente, su una sola linea, e le righe in colonne che
 * crescono con lo schermo. Le soglie sono fatte sui conti, non a occhio: una
 * riga completa (logo, ticker, nome di almeno ~90px, peso, andamento, prezzo,
 * variazione) vuole ~510px; la barra laterale ne prende 255.
 *   - 1 colonna fino a `xl`;
 *   - 2 da `xl` (1280px: ~490px a colonna, quindi SENZA andamento fino a
 *     `dense-3`, 1400px, dove ogni colonna torna sopra i 550px);
 *   - 3 da 1900px (~525px a colonna).
 * ⚠️ Le classi restano letterali: il purger di Tailwind non vede le stringhe
 * composte a runtime.
 */
const GRIGLIA = "grid grid-cols-1 xl:grid-cols-2 min-[1900px]:grid-cols-3 gap-x-6";
const ANDAMENTO = "hidden lg:block xl:hidden dense-3:block w-12 shrink-0";

function fmtPct(pct: number): string {
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function tonoPct(pct: number | null | undefined): string {
  if (pct == null) return "text-muted-foreground";
  return pct >= 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}

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
  const underlying = data.underlying;
  const uChange = data.underlying_change_pct;
  const conteggio = `${holdings.length} ${holdings.length === 1 ? "componente principale" : "componenti principali"}`;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="px-4 py-3 border-b bg-muted/20 flex items-center justify-between gap-2">
          <SectionTitle
            icon={Layers}
            label="Componenti ETF"
            right={
              <span className="inline-flex flex-wrap items-baseline gap-x-1.5 text-[0.7059rem] text-muted-foreground tabular-nums">
                {underlying ? (
                  <>
                    {/* ETF a leva: il paniere e' quello dell'ETF fisico. */}
                    <span>paniere di</span>
                    {data.underlying_in_catalog ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(underlying)}`}
                        className="font-semibold text-foreground/80 underline decoration-dotted underline-offset-2 hover:text-foreground"
                      >
                        {underlying}
                      </Link>
                    ) : (
                      <span className="font-semibold text-foreground/80">{underlying}</span>
                    )}
                    {uChange != null && (
                      <span className={cn("font-semibold", tonoPct(uChange))}>{fmtPct(uChange)}</span>
                    )}
                    <span aria-hidden>·</span>
                    <span>{conteggio}</span>
                  </>
                ) : (
                  <span>{conteggio}</span>
                )}
              </span>
            }
          />
          {wChange != null && (
            <span
              className={cn(
                "shrink-0 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[0.7059rem] font-semibold tabular-nums",
                wChange >= 0
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800/60"
                  : "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800/60",
              )}
              title="Variazione media delle componenti mostrate, pesata per quota"
            >
              media componenti {fmtPct(wChange)}
            </span>
          )}
        </div>

        <ul className={cn(GRIGLIA, "px-1 max-h-[460px] overflow-y-auto")}>
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
  const barPct = maxWeight > 0 ? Math.max(3, (h.weight / maxWeight) * 100) : 0;
  const peso = `${(h.weight * 100).toFixed(1)}%`;
  const variazione = h.change_pct != null ? fmtPct(h.change_pct) : "—";

  const inner = (
    <>
      {/* Identita': il ticker non cede mai, il nome si tronca per primo. */}
      <div className="flex flex-1 items-center gap-2 min-w-0">
        <StockLogo ticker={h.symbol} size="xs" />
        <span className="shrink-0 text-sm font-bold tabular-nums">{h.symbol}</span>
        {h.name && (
          <span className="min-w-0 truncate text-[0.7059rem] text-muted-foreground" title={h.name}>
            {h.name}
          </span>
        )}
      </div>

      {/* Weight bar */}
      <div className="hidden sm:flex items-center gap-1.5 shrink-0">
        <div className="w-10 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full bg-sky-500 dark:bg-sky-400 rounded-full"
            style={{ width: `${barPct}%` }}
          />
        </div>
        <span className="w-9 text-right text-[0.7059rem] tabular-nums text-muted-foreground">
          {peso}
        </span>
      </div>

      {/* Trend sparkline */}
      <div className={ANDAMENTO}>
        <MiniSpark closes={h.sparkline} up={up} />
      </div>

      {/* Prezzo e variazione sulla stessa linea */}
      <div className="flex shrink-0 items-baseline justify-end gap-1.5 tabular-nums">
        <span className="text-sm font-semibold">{formatMoney(h.price, h.currency)}</span>
        <span className={cn("w-14 text-right text-[0.7059rem] font-semibold", tonoPct(h.change_pct))}>
          {variazione}
        </span>
      </div>
    </>
  );

  const riga = "flex items-center gap-3 px-3 py-1.5 border-b border-border/40";

  // Catalog holdings deep-link to their stock page; off-catalog ones are
  // static rows (no detail page exists for them).
  // ⚠️ Nome esplicito sul link: i pezzi della riga sono elementi in linea in
  // un flex, e il nome calcolato li incollerebbe senza spazi («FROGJFrog…»).
  return (
    <li className="min-w-0">
      {h.in_catalog ? (
        <Link
          to={`/stocks/${encodeURIComponent(h.symbol)}`}
          aria-label={`${h.symbol}${h.name ? `, ${h.name}` : ""}, peso ${peso}, ${formatMoney(h.price, h.currency)}, ${variazione}`}
          className={cn(riga, "hover:bg-accent/30 transition-colors")}
        >
          {inner}
        </Link>
      ) : (
        <div className={riga}>{inner}</div>
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
    return <span className="block text-center text-muted-foreground text-xs">—</span>;
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 48;
  const H = 18;
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
        stroke={up ? "#17b551" : "#dc2626"}
        strokeWidth={1.3}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
