import { Building2, TrendingDown, TrendingUp, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type {
  ActionAggregate,
  InstitutionalSummary,
  TickerAggregate,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  useInstitutionalsAggregate,
  useInstitutionalsList,
} from "@/hooks/useInstitutionals";
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

function MostPickedRow({ row }: { row: TickerAggregate }) {
  // Catalog hit -> link to /stocks/:ticker; otherwise plain text.
  const TickerCell = row.stock_id ? (
    <Link
      to={`/stocks/${encodeURIComponent(row.ticker)}`}
      className="font-semibold hover:underline"
    >
      {row.ticker}
    </Link>
  ) : (
    <span className="font-semibold">{row.ticker}</span>
  );
  return (
    <tr className="hover:bg-muted/30">
      <td className="px-2 py-1.5">{TickerCell}</td>
      <td
        className="px-2 py-1.5 truncate max-w-[160px] text-xs text-muted-foreground"
        title={row.company_name ?? ""}
      >
        {row.company_name ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
        {row.holder_count}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
        {fmtBig(row.total_value_usd)}
      </td>
      <td
        className="px-2 py-1.5 text-xs text-muted-foreground truncate max-w-[200px]"
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
      <td className="px-2 py-1.5">
        <Link
          to={`/stocks/${encodeURIComponent(row.ticker)}`}
          className="font-semibold hover:underline"
        >
          {row.ticker}
        </Link>
      </td>
      <td className={cn("px-2 py-1.5 text-xs", tone)}>{row.action}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-xs">
        {fmtPct(row.qoq_change_pct)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-xs text-muted-foreground">
        {fmtPct(row.portfolio_pct)}
      </td>
      <td className="px-2 py-1.5 text-xs">
        <Link
          to={`/institutionals/${row.institutional_slug}`}
          className="hover:underline"
        >
          {row.institutional_name}
        </Link>
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground tabular-nums">
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
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {entries.slice(0, 12).map(([sector, value], idx) => (
            <span key={sector} className="flex items-center gap-1.5">
              <span
                className={cn("inline-block h-2 w-2 rounded-sm", palette[idx % palette.length])}
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
      <td className="px-2 py-1.5">
        <Link
          to={`/institutionals/${row.slug}`}
          className="font-semibold hover:underline"
        >
          {row.name}
        </Link>
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground truncate max-w-[180px]">
        {row.manager_name ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground">{row.type}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {row.total_positions ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">
        {fmtBig(row.total_value_usd)}
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground tabular-nums">
        {shortDate(row.latest_period_end)}
      </td>
    </tr>
  );
}

export default function InstitutionalsPage() {
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const list = useInstitutionalsList({ type: typeFilter, limit: 200 });
  const agg = useInstitutionalsAggregate({
    type: typeFilter,
    most_picked_limit: 25,
    recent_actions_limit: 15,
  });

  const counts = list.data?.length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Building2 className="h-6 w-6 text-foreground/80" />
          <div>
            <h1 className="text-xl font-semibold">Superinvestor &amp; istituzionali</h1>
            <p className="text-xs text-muted-foreground">
              Portafogli 13F-equivalenti tracciati. {counts} fondi disponibili.
            </p>
          </div>
        </div>
        <div className="flex gap-1 text-xs">
          <button
            type="button"
            className={cn(
              "rounded border px-2 py-1",
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
              "rounded border px-2 py-1",
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
              "rounded border px-2 py-1",
              typeFilter === "institutional"
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background hover:bg-muted",
            )}
            onClick={() => setTypeFilter("institutional")}
          >
            Istituzionali
          </button>
        </div>
      </header>

      {/* Aggregate strip: most-picked + recent buys + recent sells */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Card>
          <CardContent className="p-3">
            <SectionTitle
              icon={Users}
              label="Most-picked"
              className="mb-2"
              right={
                agg.data ? (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    top {agg.data.most_picked.length}
                  </span>
                ) : undefined
              }
            />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1 text-left">Ticker</th>
                    <th className="px-2 py-1 text-left">Nome</th>
                    <th className="px-2 py-1 text-right">N° fondi</th>
                    <th className="px-2 py-1 text-right">Tot $</th>
                    <th className="px-2 py-1 text-left">Holders</th>
                  </tr>
                </thead>
                <tbody>
                  {agg.data?.most_picked.slice(0, 12).map((row) => (
                    <MostPickedRow key={row.ticker} row={row} />
                  ))}
                  {!agg.isLoading && agg.data && agg.data.most_picked.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-2 py-3 text-center text-muted-foreground text-xs"
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
              label="Recent buys"
              tone="text-emerald-700 dark:text-emerald-300"
              className="mb-2"
            />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1 text-left">Ticker</th>
                    <th className="px-2 py-1 text-left">Action</th>
                    <th className="px-2 py-1 text-right">Q/Q</th>
                    <th className="px-2 py-1 text-right">% port</th>
                    <th className="px-2 py-1 text-left">Fondo</th>
                    <th className="px-2 py-1 text-left">Q-end</th>
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
              label="Recent sells"
              tone="text-red-700 dark:text-red-300"
              className="mb-2"
            />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1 text-left">Ticker</th>
                    <th className="px-2 py-1 text-left">Action</th>
                    <th className="px-2 py-1 text-right">Q/Q</th>
                    <th className="px-2 py-1 text-right">% port</th>
                    <th className="px-2 py-1 text-left">Fondo</th>
                    <th className="px-2 py-1 text-left">Q-end</th>
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
              <span className="text-xs text-muted-foreground tabular-nums">
                {counts}
              </span>
            }
          />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground border-b">
                <tr>
                  <th className="px-2 py-1 text-left">Portfolio</th>
                  <th className="px-2 py-1 text-left">Manager</th>
                  <th className="px-2 py-1 text-left">Tipo</th>
                  <th className="px-2 py-1 text-right">N° pos.</th>
                  <th className="px-2 py-1 text-right">Tot $</th>
                  <th className="px-2 py-1 text-left">Q-end</th>
                </tr>
              </thead>
              <tbody>
                {list.data?.map((row) => (
                  <InstitutionalRow key={row.id} row={row} />
                ))}
                {!list.isLoading && list.data && list.data.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-2 py-4 text-center text-muted-foreground text-xs"
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
