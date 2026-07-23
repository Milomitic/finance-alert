import {
  BarChart3,
  Factory,
  Globe2,
  Grid3x3,
  Layers,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useMemo } from "react";

import { SectorIndustriesBreakdown } from "@/components/sectors/SectorIndustriesBreakdown";
import { SectorTile, SummaryTile } from "@/components/sectors/SectorOverviewTiles";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { SectionTitle } from "@/components/ui/section-title";
import { useSectorsOverview } from "@/hooks/useSectorDetail";
import { fmtNum } from "@/lib/sectorFormat";
import { cn } from "@/lib/utils";

/* ─── Sectors Overview Hub ──────────────────────────────────────────────────
 *
 * Route `/sectors`. Replaced the Watchlists slot in May 2026 after the
 * watchlist feature was retired (curated user lists with custom rule
 * overrides was sunsetted — see CLAUDE.md). The slot is now an
 * omnicomprehensive hub for everything-sector:
 *
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  Header + 4 summary tiles (totals)                               │
 *   ├──────────────────────────────────────────────────────────────────┤
 *   │  12 sector cards in a grid                                       │
 *   │   ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
 *   │   │ Technology │ │  Financials│ │ Industrials│  ...              │
 *   │   │ 156 stocks │ │ 142 stocks │ │  87 stocks │                   │
 *   │   │ avg 64 ▲   │ │ avg 58     │ │ avg 51 ▼   │                   │
 *   │   │ P/E 28  ROE│ │ P/E 14 ROE │ │ P/E 22 ROE │                   │
 *   │   └────────────┘ └────────────┘ └────────────┘                   │
 *   ├──────────────────────────────────────────────────────────────────┤
 *   │  Industries breakdown (29 buckets, grouped by parent sector)     │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Each sector card links to `/sectors/{name}` for the detailed view
 * (existing SectorDetailPage). The tile / row building blocks live in
 * components/sectors/SectorOverviewTiles — this file orchestrates the
 * layout and the industries view-mode toggle.
 */
export default function SectorsOverviewPage() {
  const { data, isLoading, isError, refetch, isFetching } = useSectorsOverview();

  // Stocks with sector = NULL don't appear in any card, so the sum of
  // the card counts can undershoot the "Stock totali" tile (es. 938 vs
  // 890). Surface the gap explicitly as "N non classificati" instead
  // of letting the user hunt for the missing ~48 — the numbers ARE
  // coherent, some rows just have no sector data yet (backfillable via
  // app/scripts/backfill_null_sectors.py).
  const unclassifiedCount = useMemo(() => {
    if (!data) return 0;
    const classified = data.sectors.reduce((acc, s) => acc + s.stock_count, 0);
    return Math.max(0, data.total_stocks - classified);
  }, [data]);

  // Compute the universe-level avg score (weighted by sector stock count)
  // for the top-row "Score medio universo" tile. Simple average of the
  // sector avgs, weighted by stock count.
  const universeAvgScore = useMemo(() => {
    if (!data) return null;
    let num = 0;
    let den = 0;
    for (const s of data.sectors) {
      if (s.avg_score === null) continue;
      num += s.avg_score * s.stock_count;
      den += s.stock_count;
    }
    return den > 0 ? num / den : null;
  }, [data]);

  if (isLoading) {
    // Skeleton strutturato che rispecchia la pagina (4 tile riassuntive
    // + griglia di card settore) — stesso pattern di SectorDetailPage,
    // era un semplice "Caricamento…" testuale.
    return (
      <div className="space-y-6">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">Settori</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} rows={2} className="h-[84px]" />
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <CardSkeleton key={i} rows={5} className="h-[220px]" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">Settori</h2>
        <Card>
          <CardContent className="p-6 space-y-3">
            <p className="text-sm text-destructive">
              Errore nel caricamento dei dati settoriali.
            </p>
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm hover:bg-accent transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} aria-hidden />
              Riprova
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ─── Header ────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-3">
          <Grid3x3 className="h-7 w-7 text-muted-foreground" aria-hidden />
          Settori
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Panoramica completa di tutti i settori e sotto-settori del catalogo.
          Clicca su un settore per esplorare i suoi stock, le mediane, e i top
          mover.
        </p>
      </div>

      {/* ─── Top summary tiles ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryTile
          icon={Globe2}
          label="Stock totali"
          value={data.total_stocks.toLocaleString("it-IT")}
          hint="Universo dei country visibili"
        />
        <SummaryTile
          icon={Layers}
          label="Settori"
          value={data.total_sectors}
          hint="Classificazione GICS"
        />
        <SummaryTile
          icon={Factory}
          label="Industries"
          value={data.total_industries}
          hint="Sotto-settori GICS"
        />
        <SummaryTile
          icon={Sparkles}
          label="Score medio universo"
          value={fmtNum(universeAvgScore, 1)}
          hint="Composito 0–100, pesato per stock count"
        />
      </div>

      {/* ─── Sector grid ───────────────────────────────────────────── */}
      <div>
        <SectionTitle
          icon={Layers}
          label={`Settori (${data.sectors.length})`}
          className="mb-3"
          right={
            unclassifiedCount > 0 ? (
              <span
                className="text-xs text-muted-foreground"
                title="Stock senza settore assegnato: non compaiono in nessuna card ma contano nel totale"
              >
                ({unclassifiedCount} non classificati)
              </span>
            ) : undefined
          }
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {data.sectors.map((s) => (
            <SectorTile key={s.name} sector={s} />
          ))}
        </div>
      </div>

      {/* ─── Industries breakdown ──────────────────────────────────── */}
      <SectorIndustriesBreakdown industries={data.industries} />

      {/* ─── Help footer ───────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-4 flex items-start gap-3 text-sm">
          <BarChart3 className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
          <p className="text-muted-foreground leading-relaxed">
            Il <strong>score medio</strong> è la media dei punteggi composti
            (0–100) di tutti gli stock del settore. Mediane P/E, ROE e dividend
            yield calcolate sui fundamentals più recenti (yfinance, cache 24h).
            Per il dettaglio di ogni settore — distribuzione score, top/bottom
            pick, tabella completa con filtri — clicca su una tile.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
