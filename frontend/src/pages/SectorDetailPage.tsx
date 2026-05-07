import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { useSectorDetail, type SectorStockRow } from "@/hooks/useSectorDetail";
import { getSectorIcon, getSectorIconColor } from "@/lib/sectorMeta";
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

function StockRow({ row }: { row: SectorStockRow }) {
  return (
    <tr className="hover:bg-muted/30 transition-colors">
      <td className="px-2 py-1.5">
        <Link
          to={`/stocks/${encodeURIComponent(row.ticker)}`}
          className="font-semibold hover:underline"
        >
          {row.ticker}
        </Link>
      </td>
      <td className="px-2 py-1.5 truncate max-w-[200px]" title={row.name ?? ""}>
        {row.name ?? "—"}
      </td>
      <td className="px-2 py-1.5 text-xs text-muted-foreground">
        {row.country ?? "—"}
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
    return <div className="p-8 text-muted-foreground">Caricamento…</div>;
  }
  if (q.error || !q.data) {
    return (
      <div className="p-8">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="h-4 w-4" /> Indietro
        </Link>
        <div className="mt-4 text-red-600">
          Settore non trovato: {decoded}
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
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Dashboard
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <KpiTile label="Score medio" value={fmtNum(d.kpis.avg_composite, 1)} />
        <KpiTile label="Score mediano" value={fmtNum(d.kpis.median_composite, 1)} />
        <KpiTile label="P/E mediano" value={fmtNum(d.kpis.median_pe, 1)} />
        <KpiTile label="P/B mediano" value={fmtNum(d.kpis.median_pb, 2)} />
        <KpiTile label="ROE mediano" value={fmtNum(d.kpis.median_roe, 1, "%")} />
        <KpiTile label="Cresc. ric. med." value={fmtNum(d.kpis.median_revenue_growth, 1, "%")} />
        <KpiTile label="Div. yield med." value={fmtNum(d.kpis.median_dividend_yield, 2, "%")} />
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold mb-3">Distribuzione score composito</div>
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
        />
        <DistributionCard
          title="Risk tier"
          buckets={d.kpis.risk_distribution}
          total={d.kpis.stock_count}
          palette="risk"
        />
        <DistributionCard
          title="Capitalizzazione"
          buckets={d.kpis.market_cap_distribution}
          total={d.kpis.stock_count}
          palette="amber"
          preserveOrder
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

      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold mb-3">
            Tutte le aziende del settore ({d.stocks.length})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-xs text-muted-foreground border-b">
                  <th className="px-2 py-2 text-left">Ticker</th>
                  <th className="px-2 py-2 text-left">Nome</th>
                  <th className="px-2 py-2 text-left">Paese</th>
                  <th className="px-2 py-2 text-right">Score</th>
                  <th className="px-2 py-2 text-right">P/E</th>
                  <th className="px-2 py-2 text-right">P/B</th>
                  <th className="px-2 py-2 text-right">ROE</th>
                  <th className="px-2 py-2 text-right">Cresc. ric.</th>
                  <th className="px-2 py-2 text-right">Div. Y</th>
                  <th className="px-2 py-2 text-right">Mkt cap</th>
                </tr>
              </thead>
              <tbody>
                {d.stocks.map((row) => (
                  <StockRow key={row.ticker} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function KpiTile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="text-xs text-muted-foreground truncate" title={label}>{label}</div>
        <div className="text-lg font-semibold tabular-nums mt-1">{value}</div>
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
  const accentClass =
    accent === "green"
      ? "text-green-600 dark:text-green-400"
      : "text-red-600 dark:text-red-400";
  return (
    <Card>
      <CardContent className="p-4">
        <div className={cn("text-sm font-semibold mb-3", accentClass)}>{title}</div>
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">
            Dati insufficienti
          </div>
        ) : (
          <table className="w-full text-sm tabular-nums">
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="hover:bg-muted/30">
                  <td className="px-2 py-1.5">
                    <Link
                      to={`/stocks/${encodeURIComponent(r.ticker)}`}
                      className="font-semibold hover:underline"
                    >
                      {r.ticker}
                    </Link>
                  </td>
                  <td className="px-2 py-1.5 truncate max-w-[180px]" title={r.name ?? ""}>
                    {r.name ?? "—"}
                  </td>
                  <td className={cn("px-2 py-1.5 text-right", scoreColor(r.composite))}>
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

const PILLAR_LABELS: Array<[keyof PillarAverages, string]> = [
  ["profitability", "Profittabilità"],
  ["sustainability", "Sostenibilità"],
  ["growth", "Crescita"],
  ["value", "Valore"],
  ["momentum", "Momentum"],
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
        <div className="text-sm font-semibold mb-3">
          Punteggio medio per pilastro
        </div>
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
        <div className="text-sm font-semibold mb-3">
          Sotto-industrie ({buckets.length})
        </div>
        {buckets.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">Nessun dato</div>
        ) : (
          <div className="space-y-1.5">
            {buckets.map((b) => {
              const pct = (b.count / max) * 100;
              const sharePct = total > 0 ? (b.count / total) * 100 : 0;
              return (
                <div
                  key={b.label}
                  className="grid grid-cols-[1fr_60px_36px] items-center gap-2"
                >
                  <span className="text-xs truncate" title={b.label}>
                    {b.label}
                  </span>
                  <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500/70"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums text-right text-muted-foreground">
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
}: {
  title: string;
  buckets: CountBucket[];
  total: number;
  palette: "blue" | "amber" | "risk";
  preserveOrder?: boolean;
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

  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold mb-3">{title}</div>
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
                  className="grid grid-cols-[1fr_50px_36px] items-center gap-2"
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
                  <span className="text-xs tabular-nums text-right text-muted-foreground">
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
