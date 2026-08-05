import { BarChart3, Grid3x3, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { LeaderboardStrip } from "@/components/sectors/LeaderboardStrip";
import { SectorIndustriesBreakdown } from "@/components/sectors/SectorIndustriesBreakdown";
import { SectorLensMatrix } from "@/components/sectors/SectorLensMatrix";
import { SectorLensTable } from "@/components/sectors/SectorLensTable";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useLeaderboards, useSectorsOverview } from "@/hooks/useSectorDetail";
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
 *
 * ─── Reordered, August 2026 ───────────────────────────────────────────────
 * The page used to open with four tiles carrying the universe totals, then
 * the sector lenses. Nothing above the fold answered "so what do I look at",
 * which is the question someone opens this page with.
 *
 * Now: header → top picks → lenses → industries. The totals moved into the
 * header line, where they still orient without spending a full row: they are
 * reference numbers that change once a day, and they were outranking the
 * three rankings underneath them purely by being higher up.
 */
export default function SectorsOverviewPage() {
  const { data, isLoading, isError, refetch, isFetching } = useSectorsOverview();
  // Separate query from the overview on purpose: the sector lenses render
  // straight from SQL while the analyst board waits on the fundamentals
  // cache, so the page paints without being held to the slower half.
  const { data: boards, isLoading: boardsLoading } = useLeaderboards();
  // Shared highlight between the matrix and the table — hovering a bubble
  // lights its row and vice versa, so the two are one surface.
  const [hoveredSector, setHoveredSector] = useState<string | null>(null);

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
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">Esplora</h2>
        {/* Mirrors the real layout: three ranking cards, then the two lenses. */}
        <div className="grid gap-3 lg:grid-cols-3 [&>*]:min-w-0">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} rows={6} />
          ))}
        </div>
        <div className="grid gap-3 items-start dense-3:grid-cols-[minmax(0,480px)_minmax(0,1fr)]">
          <CardSkeleton rows={6} className="h-[380px]" />
          <CardSkeleton label="SETTORI" rows={11} strongHeader />
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
      {/* ─── Header + universe totals on one line ──────────────────── */}
      <div>
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-3">
          <Grid3x3 className="h-7 w-7 text-muted-foreground" aria-hidden />
          Esplora
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Dove guardare oggi, e come si posizionano i settori del catalogo.
        </p>
        <dl className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            <dt className="inline">Stock</dt>{" "}
            <dd className="inline font-medium tabular-nums text-foreground">
              {data.total_stocks.toLocaleString("it-IT")}
            </dd>
          </span>
          <span>
            <dt className="inline">Settori</dt>{" "}
            <dd className="inline font-medium tabular-nums text-foreground">
              {data.total_sectors}
            </dd>
          </span>
          <span>
            <dt className="inline">Industries</dt>{" "}
            <dd className="inline font-medium tabular-nums text-foreground">
              {data.total_industries}
            </dd>
          </span>
          <span>
            <dt className="inline">Score medio universo</dt>{" "}
            <dd className="inline font-medium tabular-nums text-foreground">
              {fmtNum(universeAvgScore, 1)}
            </dd>
          </span>
        </dl>
      </div>

      {/* ─── Top picks ─────────────────────────────────────────────── */}
      <LeaderboardStrip
        analysts={boards?.analysts ?? []}
        combined={boards?.combined ?? []}
        signals={boards?.signals ?? []}
        signalWindowDays={boards?.signal_window_days ?? 30}
        isLoading={boardsLoading}
      />

      {/* ─── Sectors: matrix over table ────────────────────────────── *
       *
       * This replaced a grid of eleven identical cards. The cards showed every
       * sector the same way, alphabetically, with seven metrics each as plain
       * text — so "which sector has the strongest technical posture" meant
       * reading and comparing seventy-seven numbers by eye, and the page ran
       * 3.6 screens doing it.
       *
       * Two views, deliberately in this order. The matrix answers "where does
       * everything sit" — including the one reading no column can carry, which
       * is where the two lenses DISAGREE. The table answers every pointed
       * question underneath it, sortable, in half a screen.
       *
       * Hovering either one highlights the same sector in the other, so they
       * read as one surface rather than two charts of the same data. */}
      <div className="space-y-3">
        {unclassifiedCount > 0 && (
          <p className="text-xs text-muted-foreground">
            {unclassifiedCount} stock senza settore assegnato: contano nel totale ma non
            compaiono qui.
          </p>
        )}
        {/* Side by side from 1400px, where the table's 760px minimum still
            leaves the scatter its full width. Below that they stack, and the
            scatter's own max-width keeps it from stretching. */}
        <div className="grid gap-3 items-start dense-3:grid-cols-[minmax(0,480px)_minmax(0,1fr)]">
          <SectorLensMatrix
            sectors={data.sectors}
            activeSector={hoveredSector}
            onHover={setHoveredSector}
          />
          <SectorLensTable
            sectors={data.sectors}
            activeSector={hoveredSector}
            onHover={setHoveredSector}
          />
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
            pick, tabella completa con filtri — clicca sul nome del settore
            nella tabella o sulla sua bolla nel grafico.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
