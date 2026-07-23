import { ArrowRight, BellRing } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import type {
  IndustryRow,
  SectorSummary,
  SectorTrendPoint,
} from "@/hooks/useSectorDetail";
import {
  getSectorIcon,
  getSectorIconColor,
  getSectorRing,
  getSectorTone,
} from "@/lib/sectorMeta";
import { fmtNum } from "@/lib/sectorFormat";
import { cn } from "@/lib/utils";

/* Tile / row components for the sectors overview hub. The score→color
 * helpers below are LOCAL and use the hub's softer emerald/rose palette —
 * deliberately distinct from the detail page's bolder green/red map (the
 * two pages never render together). Literal class strings per the
 * Tailwind-purger rule (CLAUDE.md). */
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

function changeTone(v: number | null): string {
  // Plain literal tone classes (Tailwind purger, per CLAUDE.md).
  if (v === null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

function fmtChange(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/* ─── Score-trend sparkline ────────────────────────────────────────────
 * Mini SVG polyline of the sector's Qualità composite over the last ~30
 * score_history captures. Stroke tone follows the net direction
 * (last vs first point). Under 2 points there's no line to draw. */
function ScoreSparkline({ points }: { points: SectorTrendPoint[] }) {
  if (points.length < 2) return null;
  const vals = points.map((p) => p.avg);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1; // flat series → centered horizontal line
  const w = 64;
  const h = 20;
  const pad = 2;
  const step = (w - pad * 2) / (vals.length - 1);
  const pts = vals
    .map((v, i) => {
      const x = pad + i * step;
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const rising = vals[vals.length - 1] >= vals[0];
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className={rising ? "text-emerald-500" : "text-rose-500"}
      role="img"
      aria-label="Trend score Qualità (ultime ~30 rilevazioni)"
    >
      <title>Trend score Qualità (ultime ~30 rilevazioni)</title>
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ─── Top summary tile ─────────────────────────────────────────────────── */
export function SummaryTile({
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
export function SectorTile({ sector }: { sector: SectorSummary }) {
  const Icon = getSectorIcon(sector.name);
  const iconColor = getSectorIconColor(sector.name);
  const tone = getSectorTone(sector.name);
  const ring = getSectorRing(sector.name);
  const navigate = useNavigate();

  // The whole tile is a <Link> to the sector detail; the inner chips
  // (segnali → /alerts, ETF proxy → /stocks/{ticker}) navigate elsewhere.
  // Nested <a> inside <a> is invalid HTML, so the chips are spans with
  // role="link" that stopPropagation + navigate imperatively.
  function goTo(e: React.MouseEvent | React.KeyboardEvent, url: string) {
    e.preventDefault();
    e.stopPropagation();
    navigate(url);
  }

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

        {/* Lente Tecnico + asse temporale: secondo score piccolo, Δ%
            giornaliero (dallo snapshot, come la heatmap dashboard) e
            sparkline del trend Qualità (~30 rilevazioni). */}
        <div className="flex items-center justify-between gap-2">
          <div
            title={
              sector.avg_technical !== null
                ? `Score tecnico medio su ${sector.technical_count} stock`
                : "Nessuno score tecnico disponibile"
            }
          >
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono mr-1.5">
              Tecnico
            </span>
            <span
              className={cn(
                "text-sm font-semibold tabular-nums",
                scoreColor(sector.avg_technical),
              )}
            >
              {fmtNum(sector.avg_technical, 1)}
            </span>
          </div>
          <span
            className={cn("text-sm font-semibold tabular-nums", changeTone(sector.change_pct))}
            title="Variazione media giornaliera del settore (ultimo snapshot)"
          >
            {fmtChange(sector.change_pct)}
          </span>
          <ScoreSparkline points={sector.score_trend} />
        </div>

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

        {/* Chip lente Segnali + proxy ETF. Il chip segnali porta alla
            pagina /alerts (nessun filtro per settore esiste lì oggi);
            il chip ETF apre il dettaglio dello SPDR proxy, presente
            solo quando il ticker esiste in catalogo. */}
        {(sector.signals_7d > 0 || sector.etf_proxy) && (
          <div className="flex items-center gap-2 pt-1">
            {sector.signals_7d > 0 && (
              <span
                role="link"
                tabIndex={0}
                onClick={(e) => goTo(e, "/alerts")}
                onKeyDown={(e) => {
                  if (e.key === "Enter") goTo(e, "/alerts");
                }}
                className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                title={`${sector.signals_7d_bull} rialzisti · ${sector.signals_7d_bear} ribassisti — apri Segnali`}
              >
                <BellRing className="h-3 w-3" aria-hidden />
                {sector.signals_7d} segnali · 7g
              </span>
            )}
            {sector.etf_proxy && (
              <span
                role="link"
                tabIndex={0}
                onClick={(e) => goTo(e, `/stocks/${encodeURIComponent(sector.etf_proxy!)}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter")
                    goTo(e, `/stocks/${encodeURIComponent(sector.etf_proxy!)}`);
                }}
                className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                title={`Apri l'ETF proxy del settore (${sector.etf_proxy})`}
              >
                ETF {sector.etf_proxy}
              </span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}

/* ─── Industry row in the breakdown table ─────────────────────────────── */
export function IndustryListItem({ industry }: { industry: IndustryRow }) {
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

/* Flat ("Classifica") variant — like IndustryListItem but with the parent
 * sector shown as a sub-label, for the cross-sector ranked list. */
export function IndustryRankRow({ industry }: { industry: IndustryRow }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="font-medium text-sm truncate">{industry.name}</div>
        {industry.sector && (
          <div className="text-xs text-muted-foreground truncate">
            {industry.sector}
          </div>
        )}
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
