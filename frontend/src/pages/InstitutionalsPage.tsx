import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Building2,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type {
  ActionAggregate,
  InstitutionalSummary,
  TickerAggregate,
} from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";

/* ─── TickerNameCell — local copy of dashboard's StockIdentity ────────── *
 *
 * "Logo + ticker on top, full company name muted underneath" stack —
 * the same pattern dashboard's TopPicksCard / TopMoversCard / 52w panel
 * use via `StockIdentity`. Inlined here (not imported) because table
 * cells need an `inline-flex` wrapper rather than the bare flex children
 * that StockIdentity emits — `<td>` content has different overflow
 * semantics than the row-level flex layout in dashboard cards.
 *
 * Sizes are explicit and intentional: `text-sm font-bold` on the ticker
 * (the user asked to keep ticker font size unchanged when bumping the
 * rest of the page), `text-[11px]` on the name (small enough not to
 * compete with the ticker, big enough to read at scan-distance).
 *
 * Wrapped in a Link only when the ticker matches a catalog row
 * (`stockId != null`); off-catalog tickers (CN ADRs, OTC, CUSIP-
 * placeholder rows from SEC 13F) render as plain text.
 */
function TickerNameCell({
  ticker,
  name,
}: {
  ticker: string;
  name: string | null | undefined;
}) {
  // CUSIP placeholders ("CUSIP:78462F103") aren't real tickers — they
  // come from SEC 13F rows where the issuer-name match against our
  // catalog didn't resolve. Linking these to /stocks/CUSIP:... would
  // 404 every time, so they stay non-clickable.
  // Real tickers are linked even when `stock_id` is null in our
  // catalog (e.g. ETFs we don't track, foreign listings) — the user
  // explicitly asked for click-through; if the StockDetailPage 404s
  // for that ticker the user gets a graceful error there, which is
  // better than dead text in the table.
  const isPlaceholder = ticker.startsWith("CUSIP:");
  const inner = (
    <span className="inline-flex items-center gap-2 min-w-0">
      <StockLogo ticker={ticker} size="xs" />
      <span className="min-w-0">
        <span className="block text-sm font-bold tabular-nums leading-tight">
          {ticker}
        </span>
        {name && (
          <span
            className="block text-[11px] text-muted-foreground truncate leading-tight max-w-[180px]"
            title={name}
          >
            {name}
          </span>
        )}
      </span>
    </span>
  );
  if (isPlaceholder) return inner;
  return (
    <Link
      to={`/stocks/${encodeURIComponent(ticker)}`}
      className="hover:underline"
    >
      {inner}
    </Link>
  );
}
import {
  useInstitutionalsAggregate,
  useInstitutionalsList,
} from "@/hooks/useInstitutionals";
import { QueryError } from "@/components/ui/query-error";
import { cn } from "@/lib/utils";

/* InstitutionalsPage — overview of all tracked institutional/superinvestor
 * portfolios.
 *
 * Layout top-to-bottom:
 *   1. Header (icon + title + count chip)
 *   2. Aggregate strip (3 cards): most-picked, recent buys, recent sells
 *   3. Sector tilt mini-bar
 *   4. Full institutionals table (links to /institutionals/:slug)
 *
 * The aggregate cards are computed only on each fund's LATEST filing
 * (no cross-quarter mixing) — see backend `get_aggregate_stats`.
 */

function fmtBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)}%`;
}

function shortDate(s: string | null): string {
  if (!s) return "—";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${d}/${m}/${y.slice(2)}`;
}

/** Un fondo è "stale" quando il suo ultimo period_end è più vecchio di
 *  2 trimestri (~183 giorni): con la finestra di deposito 13F di 45gg
 *  un fondo attivo dovrebbe sempre avere un filing entro quel raggio.
 *  Oltre → probabilmente non pubblica più / lo scraper l'ha perso. */
function isStaleFund(periodEnd: string | null): boolean {
  if (!periodEnd) return false;
  const ts = Date.parse(periodEnd);
  if (Number.isNaN(ts)) return false;
  return Date.now() - ts > 183 * 86_400_000;
}

function MostPickedRow({ row }: { row: TickerAggregate }) {
  // Ticker cell now stacks logo+ticker+name (no separate Nome column).
  // Density tradeoff: each row is ~10px taller but the user gets the
  // company name without horizontal scroll, matching the dashboard's
  // TopPicksCard pattern.
  return (
    <tr className="hover:bg-muted/30">
      <td className="px-2 py-2">
        <TickerNameCell ticker={row.ticker} name={row.company_name} />
      </td>
      <td className="px-2 py-2 text-right tabular-nums font-semibold">
        {row.holder_count}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
        {fmtBig(row.total_value_usd)}
      </td>
      <td
        className="px-2 py-2 text-sm text-muted-foreground truncate max-w-[260px]"
        title={row.holders.join(", ")}
      >
        {row.holders.slice(0, 3).join(", ")}
        {row.holders.length > 3 ? "…" : ""}
      </td>
    </tr>
  );
}

function ActionRow({ row, kind }: { row: ActionAggregate; kind: "buy" | "sell" }) {
  const tone =
    kind === "buy"
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-red-700 dark:text-red-300";
  return (
    <tr className="hover:bg-muted/30">
      <td className="px-2 py-2">
        <TickerNameCell ticker={row.ticker} name={row.company_name} />
      </td>
      <td className={cn("px-2 py-2 text-sm", tone)}>{row.action}</td>
      <td className="px-2 py-2 text-right tabular-nums text-sm">
        {fmtPct(row.qoq_change_pct)}
      </td>
      {/* Valore column: absolute $ context for the % delta. A "+12% Q/Q"
          at a $1B fund (= ~$120M move) tells a different story than the
          same delta at a $50B fund. Sourced from
          ActionAggregate.value_usd (Phase 3D-add). */}
      <td className="px-2 py-2 text-right tabular-nums text-sm">
        {fmtBig(row.value_usd)}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-sm text-muted-foreground">
        {fmtPct(row.portfolio_pct)}
      </td>
      <td className="px-2 py-2 text-sm">
        <Link
          to={`/institutionals/${row.institutional_slug}`}
          className="hover:underline"
        >
          {row.institutional_name}
        </Link>
      </td>
      <td className="px-2 py-2 text-sm text-muted-foreground tabular-nums">
        {shortDate(row.period_end_date)}
      </td>
    </tr>
  );
}

function SectorTiltBar({ tilt }: { tilt: Record<string, number> }) {
  const entries = Object.entries(tilt);
  if (entries.length === 0) return null;
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total === 0) return null;

  // Stable color rotation by sector name index.
  const palette = [
    "bg-emerald-500/70",
    "bg-sky-500/70",
    "bg-amber-500/70",
    "bg-violet-500/70",
    "bg-rose-500/70",
    "bg-teal-500/70",
    "bg-orange-500/70",
    "bg-indigo-500/70",
    "bg-pink-500/70",
    "bg-cyan-500/70",
    "bg-yellow-500/70",
    "bg-lime-500/70",
  ];

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle icon={Users} label="Tilt settoriale" className="mb-2" />
        <div className="flex h-3 w-full overflow-hidden rounded">
          {entries.map(([sector, value], idx) => {
            const pct = (value / total) * 100;
            return (
              <div
                key={sector}
                className={palette[idx % palette.length]}
                style={{ width: `${pct}%` }}
                title={`${sector}: ${fmtBig(value)} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
          {entries.slice(0, 12).map(([sector, value], idx) => (
            <span key={sector} className="flex items-center gap-1.5">
              <span
                className={cn("inline-block h-2.5 w-2.5 rounded-sm", palette[idx % palette.length])}
              />
              <span>{sector}</span>
              <span className="tabular-nums">
                {((value / total) * 100).toFixed(0)}%
              </span>
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function InstitutionalRow({ row }: { row: InstitutionalSummary }) {
  return (
    <tr className="hover:bg-muted/30">
      <td className="px-2 py-2">
        <Link
          to={`/institutionals/${row.slug}`}
          className="font-semibold hover:underline"
        >
          {row.name}
        </Link>
      </td>
      <td className="px-2 py-2 text-sm text-muted-foreground truncate max-w-[220px]">
        {row.manager_name ?? "—"}
      </td>
      <td className="px-2 py-2 text-sm text-muted-foreground">{row.type}</td>
      <td className="px-2 py-2 text-right tabular-nums">
        {row.total_positions ?? "—"}
      </td>
      <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">
        {fmtBig(row.total_value_usd)}
      </td>
      <td className="px-2 py-2 text-sm text-muted-foreground tabular-nums">
        <span className="inline-flex items-center gap-1.5">
          {shortDate(row.latest_period_end)}
          {isStaleFund(row.latest_period_end) && (
            <span
              className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
              title="Ultimo 13F più vecchio di 2 trimestri: il fondo potrebbe non pubblicare più o lo snapshot è incompleto."
            >
              stale
            </span>
          )}
        </span>
      </td>
    </tr>
  );
}

/** Colonne ordinabili client-side della tabella fondi. La lista è
 *  piccola (≤200 righe già in memoria) — nessun round-trip server. */
type FundSortKey = "total_positions" | "total_value_usd" | "latest_period_end";

function FundSortHeader({
  label,
  col,
  sort,
  onClick,
  align = "right",
}: {
  label: string;
  col: FundSortKey;
  sort: { key: FundSortKey; dir: "asc" | "desc" } | null;
  onClick: (col: FundSortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort?.key === col;
  return (
    <button
      type="button"
      onClick={() => onClick(col)}
      className={cn(
        "inline-flex items-center gap-1 uppercase tracking-wide hover:text-foreground transition-colors",
        active && "text-foreground",
        align === "right" && "ml-auto",
      )}
    >
      <span>{label}</span>
      {active && sort?.dir === "desc" && <ArrowDown className="h-3 w-3" />}
      {active && sort?.dir === "asc" && <ArrowUp className="h-3 w-3" />}
      {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
    </button>
  );
}

export default function InstitutionalsPage() {
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  // null = ordine API (alfabetico per nome). Il primo click su una
  // colonna parte DESC (i valori grandi/recenti sono i più interessanti),
  // il secondo inverte.
  const [fundSort, setFundSort] = useState<{
    key: FundSortKey;
    dir: "asc" | "desc";
  } | null>(null);
  const list = useInstitutionalsList({ type: typeFilter, limit: 200 });
  const agg = useInstitutionalsAggregate({
    type: typeFilter,
    most_picked_limit: 25,
    recent_actions_limit: 15,
  });

  function toggleFundSort(key: FundSortKey) {
    setFundSort((prev) =>
      prev?.key === key
        ? { key, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { key, dir: "desc" },
    );
  }

  const sortedFunds = useMemo(() => {
    const rows = list.data ?? [];
    if (!fundSort) return rows;
    const mult = fundSort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = a[fundSort.key];
      const bv = b[fundSort.key];
      // Nulls sempre in fondo, in entrambe le direzioni.
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string" && typeof bv === "string") {
        // latest_period_end è ISO (YYYY-MM-DD) → confronto lessicografico ok
        return av.localeCompare(bv) * mult;
      }
      return ((av as number) - (bv as number)) * mult;
    });
  }, [list.data, fundSort]);

  const counts = list.data?.length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Building2 className="h-7 w-7 text-foreground/80" />
          <div>
            <h1 className="text-2xl font-semibold">Superinvestor &amp; istituzionali</h1>
            <p className="text-sm text-muted-foreground">
              Portafogli 13F-equivalenti tracciati. {counts} fondi disponibili.
            </p>
            {/* Caption di onestà: il 13F non è un feed real-time — chi
                legge deve sapere che le posizioni possono avere fino a
                ~135 giorni (trimestre + finestra di deposito). */}
            <p className="text-xs text-muted-foreground/80">
              13F: dati trimestrali, depositati fino a 45gg dopo il fine trimestre.
            </p>
          </div>
        </div>
        <div className="flex gap-1 text-sm">
          <button
            type="button"
            className={cn(
              "rounded border px-3 py-1.5",
              typeFilter === undefined
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted",
            )}
            onClick={() => setTypeFilter(undefined)}
          >
            Tutti
          </button>
          <button
            type="button"
            className={cn(
              "rounded border px-3 py-1.5",
              typeFilter === "superinvestor"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted",
            )}
            onClick={() => setTypeFilter("superinvestor")}
          >
            Superinvestor
          </button>
          <button
            type="button"
            className={cn(
              "rounded border px-3 py-1.5",
              typeFilter === "institutional"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted",
            )}
            onClick={() => setTypeFilter("institutional")}
          >
            Istituzionali
          </button>
          <button
            type="button"
            className={cn(
              "rounded border px-3 py-1.5",
              typeFilter === "hedge_fund"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted",
            )}
            onClick={() => setTypeFilter("hedge_fund")}
          >
            Hedge fund
          </button>
        </div>
      </header>

      {/* One banner for the whole page's 13F data — both the aggregate strip and
          the funds table read from these two queries; on failure they'd
          otherwise render silently-empty tables (U1). */}
      {(agg.isError || list.isError) && (
        <QueryError
          message="dei portafogli 13F"
          onRetry={() => {
            agg.refetch();
            list.refetch();
          }}
          isRetrying={agg.isFetching || list.isFetching}
        />
      )}

      {/* Aggregate strip: most-picked + recent buys + recent sells */}
      <div className="grid gap-3 lg:grid-cols-3 [&>*]:min-w-0">
        <Card>
          <CardContent className="p-3">
            <SectionTitle
              icon={Users}
              label="Most-picked"
              className="mb-2"
              right={
                agg.data ? (
                  <span className="text-sm text-muted-foreground tabular-nums">
                    top {agg.data.most_picked.length}
                  </span>
                ) : undefined
              }
            />
            {/* max-h + overflow-y: TUTTE le righe del payload vengono
                renderizzate (prima uno slice(0,12) le troncava in
                silenzio) — il corpo scrolla invece di gonfiare la card
                oltre le sorelle buys/sells. */}
            <div className="overflow-x-auto overflow-y-auto max-h-[420px]">
              {/* Body bumped from text-sm → text-base per user request,
                  but the ticker cell explicitly resets to text-sm
                  inside TickerNameCell so the ticker font keeps its
                  current size. The "Nome" column is gone — name is
                  now stacked under the ticker à la TopPicksCard. */}
              <table className="w-full text-base">
                <thead className="text-[13px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Ticker</th>
                    <th className="px-2 py-1.5 text-right">N° fondi</th>
                    <th className="px-2 py-1.5 text-right">Tot $</th>
                    <th className="px-2 py-1.5 text-left">Holders</th>
                  </tr>
                </thead>
                <tbody>
                  {agg.data?.most_picked.map((row) => (
                    <MostPickedRow key={row.ticker} row={row} />
                  ))}
                  {!agg.isLoading && agg.data && agg.data.most_picked.length === 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        className="px-2 py-3 text-center text-muted-foreground text-sm"
                      >
                        Nessun dato — esegui un seed dei portafogli.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-3">
            <SectionTitle
              icon={TrendingUp}
              label="Acquisti recenti"
              tone="text-emerald-700 dark:text-emerald-300"
              className="mb-1"
            />
            {/* Sub-line clarifies the editorial model: 13F-HR is
                long-only — "buys" doesn't mean "long" vs "short", it
                means bullish actions on long positions (open OR grow). */}
            <p className="text-xs text-muted-foreground mb-2">
              Azioni rialziste: <span className="font-semibold">nuove posizioni</span> (new) + <span className="font-semibold">aumenti</span> (add)
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-base">
                <thead className="text-[13px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Ticker</th>
                    <th className="px-2 py-1.5 text-left">Action</th>
                    <th className="px-2 py-1.5 text-right">Q/Q</th>
                    <th className="px-2 py-1.5 text-right">Valore</th>
                    <th className="px-2 py-1.5 text-right">% port</th>
                    <th className="px-2 py-1.5 text-left">Fondo</th>
                    <th className="px-2 py-1.5 text-left">Q-end</th>
                  </tr>
                </thead>
                <tbody>
                  {agg.data?.recent_buys.slice(0, 12).map((row, idx) => (
                    <ActionRow
                      key={`${row.ticker}-${row.institutional_slug}-${idx}`}
                      row={row}
                      kind="buy"
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-3">
            <SectionTitle
              icon={TrendingDown}
              label="Vendite recenti"
              tone="text-red-700 dark:text-red-300"
              className="mb-1"
            />
            <p className="text-xs text-muted-foreground mb-2">
              Azioni ribassiste: <span className="font-semibold">riduzioni</span> (reduce) + <span className="font-semibold">uscite complete</span> (sold out)
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-base">
                <thead className="text-[13px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5 text-left">Ticker</th>
                    <th className="px-2 py-1.5 text-left">Action</th>
                    <th className="px-2 py-1.5 text-right">Q/Q</th>
                    <th className="px-2 py-1.5 text-right">Valore</th>
                    <th className="px-2 py-1.5 text-right">% port</th>
                    <th className="px-2 py-1.5 text-left">Fondo</th>
                    <th className="px-2 py-1.5 text-left">Q-end</th>
                  </tr>
                </thead>
                <tbody>
                  {agg.data?.recent_sells.slice(0, 12).map((row, idx) => (
                    <ActionRow
                      key={`${row.ticker}-${row.institutional_slug}-${idx}`}
                      row={row}
                      kind="sell"
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      {agg.data && Object.keys(agg.data.sector_tilt).length > 0 && (
        <SectorTiltBar tilt={agg.data.sector_tilt} />
      )}

      <Card>
        <CardContent className="p-3">
          <SectionTitle
            icon={Building2}
            label="Tutti i portafogli tracciati"
            className="mb-2"
            right={
              <span className="text-sm text-muted-foreground tabular-nums">
                {counts}
              </span>
            }
          />
          <div className="overflow-x-auto">
            <table className="w-full text-base">
              <thead className="text-[13px] uppercase tracking-wide text-muted-foreground border-b">
                <tr>
                  <th className="px-2 py-1.5 text-left">Portfolio</th>
                  <th className="px-2 py-1.5 text-left">Manager</th>
                  <th className="px-2 py-1.5 text-left">Tipo</th>
                  <th className="px-2 py-1.5 text-right">
                    <FundSortHeader
                      label="N° pos."
                      col="total_positions"
                      sort={fundSort}
                      onClick={toggleFundSort}
                    />
                  </th>
                  <th className="px-2 py-1.5 text-right">
                    <FundSortHeader
                      label="Tot $"
                      col="total_value_usd"
                      sort={fundSort}
                      onClick={toggleFundSort}
                    />
                  </th>
                  <th className="px-2 py-1.5 text-left">
                    <FundSortHeader
                      label="Q-end"
                      col="latest_period_end"
                      sort={fundSort}
                      onClick={toggleFundSort}
                      align="left"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedFunds.map((row) => (
                  <InstitutionalRow key={row.id} row={row} />
                ))}
                {!list.isLoading && list.data && list.data.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-2 py-4 text-center text-muted-foreground text-sm"
                    >
                      Nessun portafoglio. Avvia il seed dal terminale:&nbsp;
                      <code>python -m app.scripts.seed_institutionals</code>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
