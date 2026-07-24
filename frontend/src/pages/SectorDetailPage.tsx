import { ArrowLeft, Building2, Globe2, Shield, SlidersHorizontal } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  PicksCard,
  SortableStocksTable,
} from "@/components/sectors/SectorDetailTables";
import {
  DistributionCard,
  IndustryBreakdownCard,
  PillarAveragesCard,
  ScoreDistributionCard,
} from "@/components/sectors/SectorDistributionCards";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { useSectorDetail } from "@/hooks/useSectorDetail";
import { fmtNum } from "@/lib/sectorFormat";
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

   The visual building blocks live in components/sectors/* — this file is
   the orchestrator that wires the KPI data into them.
*/

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
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 [&>*]:min-w-0">
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

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3 [&>*]:min-w-0">
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

      <ScoreDistributionCard distribution={d.kpis.score_distribution} />

      {/* V3.2 enrichments: 4 distribution panels in a 2x2 grid.
          - Pillar averages (radar-style horizontal bars)
          - Industry sub-breakdown (top sub-sectors)
          - Country distribution
          - Risk tier + Market cap distributions stacked vertically
          Densità informativa alta in poco spazio: ogni card è
          autocontenuta e legge un sottoinsieme di kpis. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
        <PillarAveragesCard pa={d.kpis.pillar_averages} />
        <IndustryBreakdownCard buckets={d.kpis.industry_breakdown} total={d.kpis.stock_count} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 [&>*]:min-w-0">
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 [&>*]:min-w-0">
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
