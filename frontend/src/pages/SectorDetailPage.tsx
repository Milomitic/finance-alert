import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ArrowUpDown,
  BarChart3,
  Building2,
  Factory,
  Globe2,
  Layers,
  Shield,
  SlidersHorizontal,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useSectorDetail, type SectorStockRow } from "@/hooks/useSectorDetail";
import { getSectorIcon, getSectorIconColor } from "@/lib/sectorMeta";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

/* Sector recap page.
   Route /sectors/:name. Mirrors what indices do via /stocks?index=CODE,
   but with a backend endpoint that returns peer-aggregate KPIs for the
   header strip rather than a paginated list. Layout top-to-bottom:
     1. Header: sector icon + name + back link
     2. KPI strip: count, avg/median composite, P/E, P/B, ROE, etc.
     3. Score distribution histogram (5 buckets)
     4. Top 5 / Bottom 5 picks side-by-side
     5. Full stock table sortable client-side
*/

function fmtNum(v: number | null, digits = 1, suffix = ""): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function fmtMarketCap(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  if (score >= 70) return "text-green-600 dark:text-green-400 font-semibold";
  if (score >= 50) return "text-foreground";
  if (score >= 30) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function CountryFlag({ country, ticker }: { country: string | null; ticker: string }) {
  // Best-effort flag rendering — mirrors StockHeader's pattern. If the
  // helper can't resolve a code (e.g. exotic suffix), render a short
  // country-code chip instead of a missing image.
  const code = getStockFlagCode(country ?? null, ticker);
  if (!code) {
    return country ? (
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider tabular-nums">
        {country}
      </span>
    ) : (
      <span className="text-muted-foreground/60">—</span>
    );
  }
  return (
    <img
      src={`/flags/${code}.svg`}
      alt={country ?? ""}
      width={18}
      height={12}
      style={{ width: "18px", height: "12px", objectFit: "cover" }}
      className="rounded-sm shadow-sm shrink-0"
      title={country ?? code.toUpperCase()}
      aria-hidden
    />
  );
}

function StockRow({ row }: { row: SectorStockRow }) {
  return (
    <tr className="hover:bg-muted/30 transition-colors">
      {/* Identity = logo + ticker (link) + name muted underneath. Same
          treatment as the dashboard's TopStocksTable so a user moving
          between the two surfaces sees identical row chrome. */}
      <td className="px-2 py-1.5 min-w-0">
        <Link
          to={`/stocks/${encodeURIComponent(row.ticker)}`}
          className="flex items-center gap-2 hover:underline min-w-0"
        >
          <StockIdentity ticker={row.ticker} name={row.name} />
        </Link>
      </td>
      <td className="px-2 py-1.5 whitespace-nowrap">
        <CountryFlag country={row.country} ticker={row.ticker} />
      </td>
      <td className={cn("px-2 py-1.5 text-right tabular-nums", scoreColor(row.composite))}>
        {fmtNum(row.composite, 0)}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.pe, 1)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.pb, 2)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtNum(row.roe, 1, "%")}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtNum(row.revenue_growth, 1, "%")}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtNum(row.dividend_yield, 2, "%")}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {fmtMarketCap(row.market_cap)}
      </td>
    </tr>
  );
}

export default function SectorDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const decoded = decodeURIComponent(name);
  const q = useSectorDetail(decoded);

  const Icon = getSectorIcon(decoded);
  const iconColor = getSectorIconColor(decoded);

  if (q.isLoading) {
    // Sector page = header + KPI strip + stocks table. Structured
    // skeleton mirrors that shape (was bare "Caricamento…").
    return (
      <div className="space-y-3">
        <CardSkeleton rows={3} className="h-[120px]" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} rows={2} className="h-[100px]" />
          ))}
        </div>
        <CardSkeleton label="STOCKS DEL SETTORE" rows={12} strongHeader className="h-[500px]" />
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div className="p-8">
        <Link to="/sectors" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="h-4 w-4" /> Settori
        </Link>
        <div className="mt-4">
          {q.isError ? (
            // A genuine fetch failure is retryable — don't mislabel it "not found".
            <QueryError message={`del settore ${decoded}`} onRetry={q.refetch} isRetrying={q.isFetching} />
          ) : (
            <div className="text-red-600">Settore non trovato: {decoded}</div>
          )}
        </div>
      </div>
    );
  }

  const d = q.data;

  const buckets = [
    { label: "<20", color: "bg-red-500" },
    { label: "20-39", color: "bg-orange-500" },
    { label: "40-59", color: "bg-amber-500" },
    { label: "60-79", color: "bg-green-500" },
    { label: "≥80", color: "bg-emerald-600" },
  ];
  const maxBucket = Math.max(...d.kpis.score_distribution, 1);

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Icon className={cn("h-7 w-7", iconColor)} strokeWidth={1.75} />
          <div>
            <h1 className="text-2xl font-semibold">{decoded}</h1>
            <div className="text-sm text-muted-foreground">
              {d.kpis.stock_count} aziende nel catalogo
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Funnel verso lo screener: pre-filtra /stocks sul settore
              corrente (il param del browser stock è proprio `sector`). */}
          <Link
            to={`/stocks?sector=${encodeURIComponent(decoded)}`}
            className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent transition-colors"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden />
            Apri nello screener
          </Link>
          <Link
            to="/sectors"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> Settori
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <KpiTile label="Score medio" value={fmtNum(d.kpis.avg_composite, 1)} />
        <KpiTile label="Score mediano" value={fmtNum(d.kpis.median_composite, 1)} />
        <KpiTile
          label="Tecnico"
          value={fmtNum(d.kpis.avg_technical, 1)}
          hint={
            d.kpis.technical_count > 0
              ? `su ${d.kpis.technical_count} stock`
              : undefined
          }
        />
        <KpiTile label="P/E mediano" value={fmtNum(d.kpis.median_pe, 1)} />
        <KpiTile label="P/B mediano" value={fmtNum(d.kpis.median_pb, 2)} />
        <KpiTile label="ROE mediano" value={fmtNum(d.kpis.median_roe, 1, "%")} />
        <KpiTile label="Cresc. ric. med." value={fmtNum(d.kpis.median_revenue_growth, 1, "%")} />
        <KpiTile label="Div. yield med." value={fmtNum(d.kpis.median_dividend_yield, 2, "%")} />
      </div>

      <Card>
        <CardContent className="p-4">
          <SectionTitle
            icon={BarChart3}
            label="Distribuzione score composito"
            className="mb-3"
          />
          <div className="grid grid-cols-5 gap-2 items-end h-32">
            {d.kpis.score_distribution.map((count, i) => {
              const pct = (count / maxBucket) * 100;
              const b = buckets[i];
              return (
                <div key={b.label} className="flex flex-col items-center gap-1 h-full">
                  <div className="text-xs tabular-nums text-muted-foreground">
                    {count}
                  </div>
                  <div className="flex-1 w-full flex items-end">
                    <div
                      className={cn("w-full rounded-t", b.color)}
                      style={{ height: `${Math.max(pct, count > 0 ? 6 : 0)}%` }}
                    />
                  </div>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {b.label}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* V3.2 enrichments: 4 distribution panels in a 2x2 grid.
          - Pillar averages (radar-style horizontal bars)
          - Industry sub-breakdown (top sub-sectors)
          - Country distribution
          - Risk tier + Market cap distributions stacked vertically
          Densità informativa alta in poco spazio: ogni card è
          autocontenuta e legge un sottoinsieme di kpis. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PillarAveragesCard pa={d.kpis.pillar_averages} />
        <IndustryBreakdownCard buckets={d.kpis.industry_breakdown} total={d.kpis.stock_count} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <DistributionCard
          title="Distribuzione paesi"
          buckets={d.kpis.country_distribution}
          total={d.kpis.stock_count}
          palette="blue"
          icon={Globe2}
        />
        <DistributionCard
          title="Risk tier"
          buckets={d.kpis.risk_distribution}
          total={d.kpis.stock_count}
          palette="risk"
          icon={Shield}
        />
        <DistributionCard
          title="Capitalizzazione"
          buckets={d.kpis.market_cap_distribution}
          total={d.kpis.stock_count}
          palette="amber"
          preserveOrder
          icon={Building2}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PicksCard title="Top 5 per score composito" rows={d.top_picks} accent="green" />
        <PicksCard
          title="Bottom 5 per score composito"
          rows={d.bottom_picks}
          accent="red"
        />
      </div>

      <SortableStocksTable rows={d.stocks} />
    </div>
  );
}

function KpiTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-xs text-muted-foreground truncate" title={label}>{label}</div>
        <div className="text-lg font-semibold tabular-nums mt-1">{value}</div>
        {hint && (
          <div className="text-[11px] text-muted-foreground truncate" title={hint}>
            {hint}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PicksCard({
  title,
  rows,
  accent,
}: {
  title: string;
  rows: SectorStockRow[];
  accent: "green" | "red";
}) {
  const accentTone =
    accent === "green"
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-rose-700 dark:text-rose-300";
  const Icon = accent === "green" ? TrendingUp : TrendingDown;
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Icon}
          label={title}
          tone={accentTone}
          className="mb-3"
        />
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">
            Dati insufficienti
          </div>
        ) : (
          <table className="w-full text-sm tabular-nums">
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="hover:bg-muted/30">
                  {/* Same Identity treatment as the main table → logo +
                      ticker + name muted under it. Visual rhythm matches
                      the dashboard's TopMovers/TopPicks list rows. */}
                  <td className="px-2 py-1.5 min-w-0">
                    <Link
                      to={`/stocks/${encodeURIComponent(r.ticker)}`}
                      className="flex items-center gap-2 hover:underline min-w-0"
                    >
                      <StockIdentity ticker={r.ticker} name={r.name} />
                    </Link>
                  </td>
                  <td
                    className={cn(
                      "px-2 py-1.5 text-right tabular-nums font-semibold whitespace-nowrap",
                      scoreColor(r.composite),
                    )}
                  >
                    {fmtNum(r.composite, 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── V3.2 Sector enrichment cards ─────────────────────────────────────── */

import type { CountBucket, PillarAverages } from "@/hooks/useSectorDetail";

// NB: niente "momentum" qui — il pilastro è stato RIMOSSO dal composito
// Qualità (lens split 2026-05: la price-action vive nel lens Tecnico).
// StockScore.momentum è NULL by design per tutto l'universo, quindi la
// barra renderizzava sempre vuota ("—"). Non re-aggiungerla senza che
// il backend torni a popolare il campo.
const PILLAR_LABELS: Array<[keyof PillarAverages, string]> = [
  ["profitability", "Profittabilità"],
  ["sustainability", "Sostenibilità"],
  ["growth", "Crescita"],
  ["value", "Valore"],
  ["sentiment", "Sentiment"],
];

function pillarBarTone(score: number | null): string {
  if (score === null) return "bg-muted";
  if (score >= 70) return "bg-emerald-500";
  if (score >= 50) return "bg-sky-500";
  if (score >= 30) return "bg-amber-500";
  return "bg-rose-500";
}

function PillarAveragesCard({ pa }: { pa: PillarAverages }) {
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Layers}
          label="Punteggio medio per pilastro"
          className="mb-3"
        />

        <div className="space-y-2">
          {PILLAR_LABELS.map(([key, label]) => {
            const v = pa[key];
            const pct = v === null ? 0 : Math.max(0, Math.min(100, v));
            return (
              <div key={key} className="grid grid-cols-[110px_1fr_44px] items-center gap-2">
                <span className="text-xs text-muted-foreground truncate">{label}</span>
                <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", pillarBarTone(v))}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs tabular-nums font-semibold text-right">
                  {v === null ? "—" : v.toFixed(0)}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function IndustryBreakdownCard({
  buckets,
  total,
}: {
  buckets: CountBucket[];
  total: number;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Factory}
          label={`Sotto-industrie (${buckets.length})`}
          className="mb-3"
        />
        {buckets.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">Nessun dato</div>
        ) : (
          <div className="space-y-1.5">
            {buckets.map((b) => {
              const pct = (b.count / max) * 100;
              const sharePct = total > 0 ? (b.count / total) * 100 : 0;
              // Funnel verso lo screener: ogni industry apre /stocks
              // pre-filtrato (param `industry`). Il bucket "(no
              // industry)" è un'etichetta sintetica, non un filtro.
              const linkable = b.label !== "(no industry)";
              return (
                <div
                  key={b.label}
                  // V3.6: right column widened 36px → 72px and explicitly
                  // `whitespace-nowrap` because counts >9 paired with
                  // percentages ≥10% (e.g. "25 · 63%") used to wrap onto
                  // two lines inside the original 36px cell, doubling the
                  // row height and breaking the rhythm.
                  className="grid grid-cols-[1fr_60px_72px] items-center gap-2"
                >
                  {linkable ? (
                    <Link
                      to={`/stocks?industry=${encodeURIComponent(b.label)}`}
                      className="text-xs truncate hover:underline hover:text-foreground"
                      title={`Apri "${b.label}" nello screener`}
                    >
                      {b.label}
                    </Link>
                  ) : (
                    <span className="text-xs truncate" title={b.label}>
                      {b.label}
                    </span>
                  )}
                  <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500/70"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums text-right text-muted-foreground whitespace-nowrap">
                    {b.count} · {sharePct.toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const RISK_PALETTE: Record<string, string> = {
  conservative: "bg-emerald-500",
  moderate: "bg-sky-500",
  aggressive: "bg-rose-500",
};

function DistributionCard({
  title,
  buckets,
  total,
  palette,
  preserveOrder = false,
  icon,
}: {
  title: string;
  buckets: CountBucket[];
  total: number;
  palette: "blue" | "amber" | "risk";
  preserveOrder?: boolean;
  /** Icon shown in the SectionTitle. Defaults to BarChart3 when not
   *  supplied so callers that just need a generic histogram look don't
   *  have to import an icon. */
  icon?: typeof BarChart3;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const ordered = preserveOrder ? buckets : [...buckets].sort((a, b) => b.count - a.count);

  function barClass(label: string, idx: number): string {
    if (palette === "risk") return RISK_PALETTE[label] ?? "bg-muted";
    if (palette === "amber") {
      // Mega → emerald, descending → progressively warmer
      const tones = ["bg-emerald-500", "bg-sky-500", "bg-amber-500", "bg-orange-500", "bg-rose-500"];
      return tones[idx] ?? "bg-muted";
    }
    return "bg-blue-500/70";
  }

  const Icon = icon ?? BarChart3;
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={Icon} label={title} className="mb-3" />
        {ordered.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">Nessun dato</div>
        ) : (
          <div className="space-y-1.5">
            {ordered.map((b, i) => {
              const pct = (b.count / max) * 100;
              const sharePct = total > 0 ? (b.count / total) * 100 : 0;
              return (
                <div
                  key={b.label}
                  // V3.6: right column widened 36px → 72px + nowrap
                  // (see IndustryBreakdownCard for the rationale —
                  // same "25 · 63%" two-line bug).
                  className="grid grid-cols-[1fr_50px_72px] items-center gap-2"
                >
                  <span className="text-xs truncate capitalize" title={b.label}>
                    {b.label}
                  </span>
                  <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", barClass(b.label, i))}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums text-right text-muted-foreground whitespace-nowrap">
                    {b.count} · {sharePct.toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── SortableStocksTable ────────────────────────────────────────────────── */
/* Client-side sortable variant of the main "Tutte le aziende" table.
 * State lives here (not lifted) — sort is a pure view concern and the
 * page never needs to read it back. Sort columns map to the SectorStockRow
 * field; the comparator handles null-last consistently for both numeric
 * and string columns.
 *
 * UX:
 *   - Click header → set sort key (default desc for numeric, asc for
 *     ticker/country); same key → flip direction.
 *   - Active column shows an up/down chevron; inactive columns show a
 *     dim two-way arrow so the user knows they ARE clickable.
 *   - Default sort is composite DESC (mirrors top-picks ordering) so
 *     the table opens on the highest-score stocks first.
 */

type SortKey =
  | "ticker"
  | "country"
  | "composite"
  | "pe"
  | "pb"
  | "roe"
  | "revenue_growth"
  | "dividend_yield"
  | "market_cap";

type SortDir = "asc" | "desc";

interface ColumnSpec {
  key: SortKey;
  label: string;
  align: "left" | "right";
  /** Default sort direction the column flips to when first clicked.
   *  Numeric columns default desc (largest first), string columns asc. */
  defaultDir: SortDir;
}

const COLUMNS: ColumnSpec[] = [
  { key: "ticker", label: "Stock", align: "left", defaultDir: "asc" },
  { key: "country", label: "Paese", align: "left", defaultDir: "asc" },
  { key: "composite", label: "Score", align: "right", defaultDir: "desc" },
  { key: "pe", label: "P/E", align: "right", defaultDir: "asc" },
  { key: "pb", label: "P/B", align: "right", defaultDir: "asc" },
  { key: "roe", label: "ROE", align: "right", defaultDir: "desc" },
  { key: "revenue_growth", label: "Cresc. ric.", align: "right", defaultDir: "desc" },
  { key: "dividend_yield", label: "Div. Y", align: "right", defaultDir: "desc" },
  { key: "market_cap", label: "Mkt cap", align: "right", defaultDir: "desc" },
];

function compareRows(a: SectorStockRow, b: SectorStockRow, key: SortKey, dir: SortDir): number {
  const av = a[key];
  const bv = b[key];
  // Null-last regardless of direction: a row with no value (e.g. no P/E)
  // should never bubble to the top of either asc or desc sort.
  const aNull = av === null || av === undefined;
  const bNull = bv === null || bv === undefined;
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  let cmp: number;
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv;
  } else {
    cmp = String(av).localeCompare(String(bv));
  }
  return dir === "asc" ? cmp : -cmp;
}

function SortableStocksTable({ rows }: { rows: SectorStockRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("composite");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    // Slice() so we don't mutate the prop array (React rules + downstream
    // memoisation guarantees in the parent hook).
    return [...rows].sort((a, b) => compareRows(a, b, sortKey, sortDir));
  }, [rows, sortKey, sortDir]);

  function onHeaderClick(col: ColumnSpec) {
    if (col.key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Building2}
          label={`Tutte le aziende (${rows.length})`}
          className="mb-3"
        />
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-muted-foreground/80 border-b border-border/60">
                {COLUMNS.map((col) => {
                  const active = col.key === sortKey;
                  const Indicator = active
                    ? sortDir === "asc"
                      ? ArrowUp
                      : ArrowDown
                    : ArrowUpDown;
                  return (
                    <th
                      key={col.key}
                      // Clickable header: small hover affordance + cursor.
                      // The chevron flips between Up/Down for the active
                      // column and stays dim two-way for inactive ones —
                      // a discoverability hint per the "every clickable
                      // surface MUST look clickable" UX rule.
                      onClick={() => onHeaderClick(col)}
                      className={cn(
                        "px-2 py-2 font-mono select-none cursor-pointer",
                        "hover:text-foreground transition-colors",
                        col.align === "right" ? "text-right" : "text-left",
                        active && "text-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "inline-flex items-center gap-1",
                          col.align === "right" && "flex-row-reverse",
                        )}
                      >
                        <span>{col.label}</span>
                        <Indicator
                          className={cn(
                            "h-3 w-3 shrink-0",
                            active ? "opacity-100" : "opacity-40",
                          )}
                          aria-hidden
                        />
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <StockRow key={row.ticker} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
