import {
  ArrowRight,
  BarChart3,
  Factory,
  Globe2,
  Grid3x3,
  Layers,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  useSectorsOverview,
  type IndustryRow,
  type SectorSummary,
} from "@/hooks/useSectorDetail";
import {
  getSectorIcon,
  getSectorIconColor,
  getSectorRing,
  getSectorTone,
} from "@/lib/sectorMeta";
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
 * (existing SectorDetailPage). The industries section is informational
 * — no click-through to a dedicated industry page (that doesn't exist
 * yet); a future enhancement could route to /stocks?industry=X via
 * the screener.
 */

function fmtNum(v: number | null | undefined, digits = 1, suffix = ""): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score >= 70) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 50) return "text-foreground";
  if (score >= 30) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

function scoreBgBar(score: number | null | undefined): string {
  // Saturated bar color paired with `scoreColor` text. Tailwind purger
  // requires literal class strings — keep this as a switch, not a
  // template, per CLAUDE.md.
  if (score === null || score === undefined) return "bg-zinc-300 dark:bg-zinc-700";
  if (score >= 70) return "bg-emerald-500";
  if (score >= 50) return "bg-sky-500";
  if (score >= 30) return "bg-amber-500";
  return "bg-rose-500";
}

/* ─── Top summary tile ─────────────────────────────────────────────────── */
function SummaryTile({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4 flex items-center gap-3">
        <div className="rounded-lg bg-muted/60 p-2.5">
          <Icon className="h-5 w-5 text-muted-foreground" />
        </div>
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-mono">
            {label}
          </div>
          <div className="text-2xl font-bold tabular-nums leading-tight">
            {value}
          </div>
          {hint && (
            <div className="text-xs text-muted-foreground mt-0.5">{hint}</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Sector tile card ────────────────────────────────────────────────── */
function SectorTile({ sector }: { sector: SectorSummary }) {
  const Icon = getSectorIcon(sector.name);
  const iconColor = getSectorIconColor(sector.name);
  const tone = getSectorTone(sector.name);
  const ring = getSectorRing(sector.name);

  return (
    <Link
      to={`/sectors/${encodeURIComponent(sector.name)}`}
      className={cn(
        "group block rounded-lg border bg-card overflow-hidden",
        "hover:shadow-md hover:ring-2 hover:ring-offset-1 transition-all",
        ring,
      )}
    >
      {/* Tinted header band */}
      <div className={cn("px-4 py-3 border-b", tone)}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Icon className={cn("h-5 w-5 shrink-0", iconColor)} aria-hidden />
            <span className="font-semibold truncate" title={sector.name}>
              {sector.name}
            </span>
          </div>
          <ArrowRight
            className="h-4 w-4 shrink-0 opacity-40 group-hover:opacity-100 transition-opacity"
            aria-hidden
          />
        </div>
      </div>

      {/* Body: stock count + avg score with progress bar */}
      <div className="p-4 space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-mono">
              Stocks
            </div>
            <div className="text-3xl font-bold tabular-nums leading-none">
              {sector.stock_count}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-mono">
              Score medio
            </div>
            <div
              className={cn(
                "text-3xl font-bold tabular-nums leading-none",
                scoreColor(sector.avg_score),
              )}
            >
              {fmtNum(sector.avg_score, 1)}
            </div>
          </div>
        </div>

        {/* Score progress bar — visual cue of how the sector sits on 0-100 */}
        {sector.avg_score !== null && (
          <div className="w-full h-1.5 rounded-full bg-muted/60 overflow-hidden">
            <div
              className={cn("h-full transition-all", scoreBgBar(sector.avg_score))}
              style={{ width: `${Math.max(0, Math.min(100, sector.avg_score))}%` }}
            />
          </div>
        )}

        {/* Fundamentals strip (small) */}
        <div className="grid grid-cols-3 gap-2 pt-1">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
              P/E
            </div>
            <div className="text-sm font-semibold tabular-nums">
              {fmtNum(sector.median_pe, 1)}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
              ROE
            </div>
            <div className="text-sm font-semibold tabular-nums">
              {fmtNum(sector.median_roe, 1, "%")}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
              Div Y
            </div>
            <div className="text-sm font-semibold tabular-nums">
              {fmtNum(sector.median_dividend_yield, 1, "%")}
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
}

/* ─── Industry row in the breakdown table ─────────────────────────────── */
function IndustryListItem({ industry }: { industry: IndustryRow }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="font-medium text-sm truncate" title={industry.name}>
          {industry.name}
        </div>
      </div>
      <div className="text-xs text-muted-foreground tabular-nums shrink-0">
        {industry.stock_count} stock
      </div>
      <div
        className={cn(
          "text-sm font-semibold tabular-nums shrink-0 w-12 text-right",
          scoreColor(industry.avg_score),
        )}
      >
        {fmtNum(industry.avg_score, 0)}
      </div>
    </div>
  );
}

/* ─── Page ────────────────────────────────────────────────────────────── */
export default function SectorsOverviewPage() {
  const { data, isLoading, isError } = useSectorsOverview();
  // Industries view-mode toggle: "by-sector" groups under each sector
  // header, "flat" lists all 29 in one ranked list. Default by-sector
  // because that's the most useful entry point on first land — the
  // user typically wants to see "what's IN technology?" rather than
  // a global industry leaderboard.
  const [industryView, setIndustryView] = useState<"by-sector" | "flat">(
    "by-sector",
  );

  // Group industries by parent sector for the "by-sector" view.
  const industriesBySector = useMemo(() => {
    if (!data) return new Map<string, IndustryRow[]>();
    const m = new Map<string, IndustryRow[]>();
    for (const ind of data.industries) {
      const key = ind.sector ?? "(altro)";
      const list = m.get(key) ?? [];
      list.push(ind);
      m.set(key, list);
    }
    return m;
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
    return (
      <div className="space-y-6">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">Settori</h2>
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Caricamento overview settori…
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">Settori</h2>
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Errore nel caricamento dei dati settoriali.
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
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {data.sectors.map((s) => (
            <SectorTile key={s.name} sector={s} />
          ))}
        </div>
      </div>

      {/* ─── Industries breakdown ──────────────────────────────────── */}
      <div>
        <SectionTitle
          icon={Factory}
          label={`Sotto-settori (${data.industries.length})`}
          className="mb-3"
          right={
            <div className="inline-flex rounded-md border bg-card overflow-hidden">
              <button
                type="button"
                onClick={() => setIndustryView("by-sector")}
                className={cn(
                  "px-3 py-1 text-xs font-mono uppercase tracking-wider transition-colors",
                  industryView === "by-sector"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent",
                )}
              >
                Per settore
              </button>
              <button
                type="button"
                onClick={() => setIndustryView("flat")}
                className={cn(
                  "px-3 py-1 text-xs font-mono uppercase tracking-wider transition-colors border-l",
                  industryView === "flat"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent",
                )}
              >
                Classifica
              </button>
            </div>
          }
        />

        {industryView === "by-sector" ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {Array.from(industriesBySector.entries()).map(([sector, rows]) => {
              const SectorIcon = getSectorIcon(sector);
              const iconColor = getSectorIconColor(sector);
              return (
                <Card key={sector} className="overflow-hidden">
                  <CardContent className="p-3">
                    <Link
                      to={`/sectors/${encodeURIComponent(sector)}`}
                      className="flex items-center gap-2 px-2 py-1.5 mb-2 rounded-md hover:bg-muted/60 transition-colors"
                    >
                      <SectorIcon
                        className={cn("h-4 w-4 shrink-0", iconColor)}
                        aria-hidden
                      />
                      <span className="font-semibold text-sm truncate">
                        {sector}
                      </span>
                      <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
                        {rows.length} industries
                      </span>
                    </Link>
                    <div className="space-y-0.5">
                      {rows.map((ind) => (
                        <IndustryListItem key={ind.name} industry={ind} />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          /* Flat ranking — sorted by avg score desc, then stock count desc */
          <Card>
            <CardContent className="p-3">
              <div className="space-y-0.5">
                {[...data.industries]
                  .sort((a, b) => {
                    const sa = a.avg_score ?? -Infinity;
                    const sb = b.avg_score ?? -Infinity;
                    if (sa !== sb) return sb - sa;
                    return b.stock_count - a.stock_count;
                  })
                  .map((ind) => (
                    <div
                      key={`${ind.sector}-${ind.name}`}
                      className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-sm truncate">
                          {ind.name}
                        </div>
                        {ind.sector && (
                          <div className="text-xs text-muted-foreground truncate">
                            {ind.sector}
                          </div>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground tabular-nums shrink-0">
                        {ind.stock_count} stock
                      </div>
                      <div
                        className={cn(
                          "text-sm font-semibold tabular-nums shrink-0 w-12 text-right",
                          scoreColor(ind.avg_score),
                        )}
                      >
                        {fmtNum(ind.avg_score, 0)}
                      </div>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

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
