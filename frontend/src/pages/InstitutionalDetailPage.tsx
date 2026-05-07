import { ArrowLeft, Building2, ExternalLink } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import type { HoldingDetail } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useInstitutionalDetail } from "@/hooks/useInstitutionals";
import { cn } from "@/lib/utils";

/* InstitutionalDetailPage — single portfolio drilldown.
 *
 * Route: /institutionals/:slug
 * Optional ?period=YYYY-MM-DD lets the user inspect older filings via
 * the period selector at the top of the page.
 *
 * Layout:
 *   1. Back link + portfolio header (manager + AUM + total positions)
 *   2. Period selector (if multiple filings exist)
 *   3. Holdings table sorted by portfolio_pct DESC
 *
 * Holdings table cells:
 *   - Ticker → /stocks/:ticker if catalog hit, else plain text
 *     (Chinese / OTC tickers won't have a catalog entry — render as text)
 *   - Action chip with semantic color (new/add green, reduce/sold_out red)
 *   - Q/Q delta with sign coloring
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

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return `${v.toFixed(digits)}%`;
}

function fmtShares(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

function actionMeta(action: string | null): {
  label: string;
  tone: string;
  bg: string;
} {
  switch (action) {
    case "new":
      return {
        label: "Nuovo",
        tone: "text-emerald-700 dark:text-emerald-300",
        bg: "bg-emerald-50 dark:bg-emerald-950/40",
      };
    case "add":
      return {
        label: "Add",
        tone: "text-emerald-700 dark:text-emerald-300",
        bg: "bg-emerald-50 dark:bg-emerald-950/40",
      };
    case "reduce":
      return {
        label: "Reduce",
        tone: "text-amber-700 dark:text-amber-300",
        bg: "bg-amber-50 dark:bg-amber-950/40",
      };
    case "sold_out":
      return {
        label: "Sold out",
        tone: "text-red-700 dark:text-red-300",
        bg: "bg-red-50 dark:bg-red-950/40",
      };
    case "hold":
      return {
        label: "Hold",
        tone: "text-muted-foreground",
        bg: "bg-muted/40",
      };
    default:
      return { label: action ?? "—", tone: "text-muted-foreground", bg: "bg-muted/40" };
  }
}

function qoqColor(v: number | null | undefined): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-700 dark:text-emerald-300";
  if (v < 0) return "text-red-700 dark:text-red-300";
  return "text-muted-foreground";
}

function HoldingRow({ row }: { row: HoldingDetail }) {
  const a = actionMeta(row.action);
  const tickerCell = row.stock_id ? (
    <Link
      to={`/stocks/${encodeURIComponent(row.ticker)}`}
      className="font-semibold hover:underline"
    >
      {row.ticker}
    </Link>
  ) : (
    <span className="font-semibold" title="Ticker fuori dal catalogo">
      {row.ticker}
    </span>
  );

  return (
    <tr className="hover:bg-muted/30 border-t border-border/40">
      <td className="px-2 py-1.5">{tickerCell}</td>
      <td
        className="px-2 py-1.5 text-xs text-muted-foreground truncate max-w-[200px]"
        title={row.company_name ?? ""}
      >
        {row.company_name ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums font-semibold">
        {fmtPct(row.portfolio_pct)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtBig(row.value_usd)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-xs">
        {fmtShares(row.shares)}
      </td>
      <td className="px-2 py-1.5">
        <span
          className={cn(
            "inline-block rounded px-1.5 py-0.5 text-[11px] font-medium",
            a.tone,
            a.bg,
          )}
        >
          {a.label}
        </span>
      </td>
      <td className={cn("px-2 py-1.5 text-right tabular-nums text-xs", qoqColor(row.qoq_change_pct))}>
        {row.qoq_change_pct != null
          ? `${row.qoq_change_pct > 0 ? "+" : ""}${row.qoq_change_pct.toFixed(1)}%`
          : "—"}
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground">
        {row.stock_sector ?? "—"}
      </td>
    </tr>
  );
}

export default function InstitutionalDetailPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const periodParam = searchParams.get("period") ?? undefined;

  const q = useInstitutionalDetail(slug, periodParam);

  if (q.isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Caricamento…</div>;
  }
  if (q.isError || !q.data) {
    return (
      <div className="p-4">
        <Link
          to="/institutionals"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Torna alla lista
        </Link>
        <div className="mt-4 text-sm text-red-700">Portfolio non trovato.</div>
      </div>
    );
  }

  const { institutional, holdings, available_periods } = q.data;
  const totalValue = institutional.total_value_usd ?? 0;
  const top10Pct = holdings
    .slice(0, 10)
    .reduce((sum, h) => sum + (h.portfolio_pct ?? 0), 0);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <Link
            to="/institutionals"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
          >
            <ArrowLeft className="h-3 w-3" />
            Tutti i portafogli
          </Link>
          <div className="mt-2 flex items-center gap-3">
            <Building2 className="h-6 w-6 text-foreground/80" />
            <div>
              <h1 className="text-xl font-semibold leading-tight">
                {institutional.name}
              </h1>
              {institutional.manager_name && (
                <p className="text-xs text-muted-foreground">
                  {institutional.manager_name} · {institutional.type} ·{" "}
                  fonte: {institutional.source}
                </p>
              )}
            </div>
          </div>
          {institutional.description && (
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              {institutional.description}
            </p>
          )}
        </div>
        {institutional.source_url && (
          <a
            href={institutional.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            Apri fonte
          </a>
        )}
      </header>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <CardContent className="p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Posizioni
            </div>
            <div className="text-2xl font-semibold tabular-nums">
              {institutional.total_positions ?? "—"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Valore totale
            </div>
            <div className="text-2xl font-semibold tabular-nums">
              {fmtBig(totalValue)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Top-10 weight
            </div>
            <div className="text-2xl font-semibold tabular-nums">
              {fmtPct(top10Pct, 1)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Periodo (Q-end)
            </div>
            <div className="flex items-center gap-2">
              <select
                className="rounded border bg-background px-2 py-1 text-sm"
                value={periodParam ?? institutional.latest_period_end ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  const next = new URLSearchParams(searchParams);
                  // Latest = no param
                  if (v && v !== institutional.latest_period_end) {
                    next.set("period", v);
                  } else {
                    next.delete("period");
                  }
                  setSearchParams(next);
                }}
              >
                {available_periods.map((p) => (
                  <option key={p} value={p}>
                    {p}
                    {p === institutional.latest_period_end ? " (latest)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-3">
          <SectionTitle
            icon={Building2}
            label="Holdings"
            className="mb-2"
            right={
              <span className="text-xs text-muted-foreground tabular-nums">
                {holdings.length}
              </span>
            }
          />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground border-b">
                <tr>
                  <th className="px-2 py-1 text-left">Ticker</th>
                  <th className="px-2 py-1 text-left">Nome</th>
                  <th className="px-2 py-1 text-right">% port.</th>
                  <th className="px-2 py-1 text-right">Valore</th>
                  <th className="px-2 py-1 text-right">Shares</th>
                  <th className="px-2 py-1 text-left">Azione</th>
                  <th className="px-2 py-1 text-right">Q/Q</th>
                  <th className="px-2 py-1 text-left">Settore</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((row) => (
                  <HoldingRow key={`${row.ticker}-${row.shares}`} row={row} />
                ))}
                {holdings.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-2 py-4 text-center text-muted-foreground text-xs"
                    >
                      Nessuna posizione registrata per questo periodo.
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
