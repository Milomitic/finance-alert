import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";

import type {
  ScoreBreakdownComponent,
  StockScore,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useStockScore } from "@/hooks/useStockScore";
import {
  CATEGORY_LABEL,
  RISK_LABEL,
  RISK_TONE,
  scoreBgColor,
  scoreColor,
  scoreHex,
  scoreLabel,
} from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/* ─── Time helpers ──────────────────────────────────────────────────────── */

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 1) return "ora";
  if (diffMin < 60) return `${Math.max(1, Math.round(diffMin))} min fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  const diffD = diffH / 24;
  if (diffD < 30) return `${Math.round(diffD)}g fa`;
  return `${Math.round(diffD / 30)} mesi fa`;
}

/* ─── Composite score gauge (semicircle SVG) ────────────────────────────── */
/* Pure SVG arc, 180°, 0–100. Single solid color picked from the score's tone
 * (rose / amber / sky / emerald) so the visual matches the number color and
 * the spark bars in the dashboard rows. The big composite number sits in the
 * center; the score label ("Buono", "Eccellente", ...) below it.
 *
 * Chosen vs gradient stops for clarity: a uniform tone says "this score is
 * X strength" — a gradient would say "this dial spans the full range" which
 * is a different statement. */

interface GaugeProps {
  score: number;
  size?: number;
}

function ScoreGauge({ score, size = 180 }: GaugeProps) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 12; // 12px stroke + tiny padding
  const stroke = 12;
  const clamped = Math.max(0, Math.min(100, score));
  // Arc spans 180° (left half-circle): angle 0 at the left, 180 at the right.
  // We sweep `pct` of that range from the left end.
  // SVG: pathLength + stroke-dasharray gives us a clean way to render a partial arc.
  // Build a half-circle path going from (cx - r, cy) clockwise to (cx + r, cy).
  const startX = cx - radius;
  const startY = cy;
  const endX = cx + radius;
  const endY = cy;
  // We use pathLength=100 so dasharray maps directly to percent.
  const dashLen = clamped;
  const fillColor = scoreHex(score);

  return (
    <svg
      width={size}
      height={size / 2 + 16}
      viewBox={`0 0 ${size} ${size / 2 + 16}`}
      className="overflow-visible"
      role="img"
      aria-label={`Score ${score.toFixed(1)} su 100`}
    >
      {/* Track */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.12}
        strokeWidth={stroke}
        strokeLinecap="round"
        className="text-foreground"
      />
      {/* Fill */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke={fillColor}
        strokeWidth={stroke}
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${dashLen} 100`}
        style={{ transition: "stroke-dasharray 400ms ease-out" }}
      />
      {/* Tick marks at 40 / 60 / 80 — the threshold boundaries */}
      {[40, 60, 80].map((t) => {
        const angle = Math.PI * (1 - t / 100); // π at 0, 0 at 100
        const tx = cx + Math.cos(angle) * radius;
        const ty = cy - Math.sin(angle) * radius;
        const tx2 = cx + Math.cos(angle) * (radius - stroke / 2 - 2);
        const ty2 = cy - Math.sin(angle) * (radius - stroke / 2 - 2);
        return (
          <line
            key={t}
            x1={tx}
            y1={ty}
            x2={tx2}
            y2={ty2}
            stroke="currentColor"
            strokeOpacity={0.35}
            strokeWidth={1}
            className="text-foreground"
          />
        );
      })}
    </svg>
  );
}

/* ─── Sub-score row with breakdown tooltip ──────────────────────────────── */

const PILLAR_ORDER: Array<keyof StockScore["sub_scores"]> = [
  "quality",
  "growth",
  "value",
  "momentum",
  "sentiment",
];

/** Pretty-format a raw breakdown value. The shape is loose — values are
 *  raw inputs from upstream (yfinance fundamentals, technicals, ...) and
 *  vary in magnitude wildly. We pick the format from the rough scale:
 *    - |v| > 1e6 → big USD
 *    - 0–1 fractional → percent
 *    - else → 2-decimal float
 *  Imperfect but readable; the "max points / earned points" line carries
 *  the meaningful information regardless. */
function fmtRaw(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "n/d";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 1) return v.toFixed(2);
  if (abs > 0) return `${(v * 100).toFixed(1)}%`;
  return "0";
}

interface SubScoreRowProps {
  pillar: keyof StockScore["sub_scores"];
  score: number | null;
  components: Record<string, ScoreBreakdownComponent> | undefined;
}

function SubScoreRow({ pillar, score, components }: SubScoreRowProps) {
  const label = CATEGORY_LABEL[pillar];
  const isMissing = score == null;
  const fillCls = isMissing ? "bg-muted" : scoreBgColor(score);
  const valueCls = isMissing ? "text-muted-foreground" : scoreColor(score);
  const widthPct = isMissing ? 0 : Math.max(0, Math.min(100, score));

  const componentEntries = components ? Object.entries(components) : [];

  const trigger = (
    <div className="grid grid-cols-[80px_1fr_38px] items-center gap-2 py-1.5 cursor-help">
      <span className="text-xs font-medium text-muted-foreground truncate">
        {label}
      </span>
      <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", fillCls)}
          style={{ width: `${widthPct}%` }}
        />
      </div>
      <span
        className={cn(
          "text-sm font-bold tabular-nums text-right",
          valueCls,
        )}
      >
        {isMissing ? "—" : Math.round(score!)}
      </span>
    </div>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent
        side="left"
        align="start"
        sideOffset={8}
        collisionPadding={12}
        className="w-72 p-3"
      >
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3 pb-1.5 border-b border-border/50">
            <span className="text-xs font-bold uppercase tracking-wider">
              {label}
            </span>
            <span
              className={cn(
                "text-sm font-bold tabular-nums",
                isMissing ? "text-muted-foreground" : scoreColor(score!),
              )}
            >
              {isMissing ? "n/d" : `${Math.round(score!)}/100`}
            </span>
          </div>
          {isMissing ? (
            <div className="text-xs text-muted-foreground">
              Dati insufficienti per questo pilastro — escluso dal calcolo,
              i pesi vengono rinormalizzati sugli altri.
            </div>
          ) : componentEntries.length === 0 ? (
            <div className="text-xs text-muted-foreground">
              Dettaglio componenti non disponibile.
            </div>
          ) : (
            <ul className="space-y-1 text-xs">
              {componentEntries.map(([name, comp]) => (
                <li
                  key={name}
                  className="flex items-baseline justify-between gap-2"
                >
                  <span className="text-muted-foreground capitalize">
                    {name.replace(/_/g, " ")}
                  </span>
                  <span className="tabular-nums shrink-0">
                    <span className="text-foreground/90">
                      {fmtRaw(comp.raw)}
                    </span>
                    <span className="text-muted-foreground ml-2">
                      {comp.points.toFixed(1)}/{comp.max} pt
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/* ─── Card body wrappers ────────────────────────────────────────────────── */

function CardShell({
  children,
  onRefresh,
  isFetching,
}: {
  children: React.ReactNode;
  onRefresh?: () => void;
  isFetching?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Sparkles}
          label="Stock score"
          className="mb-3"
          right={
            onRefresh ? (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isFetching}
                className={cn(
                  "p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50",
                )}
                title="Ricarica score"
                aria-label="Ricarica score"
              >
                <RefreshCw
                  className={cn(
                    "h-3.5 w-3.5",
                    isFetching && "animate-spin",
                  )}
                />
              </button>
            ) : undefined
          }
        />
        {children}
      </CardContent>
    </Card>
  );
}

/* ─── Main component ────────────────────────────────────────────────────── */

export function StockScoreCard({ ticker }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, noScoreYet, refetch } =
    useStockScore(ticker);

  const onRefresh = () => {
    qc.invalidateQueries({ queryKey: ["stock-score", ticker] });
    refetch();
  };

  if (isLoading) {
    return (
      <CardShell>
        <div className="space-y-3">
          <div className="h-[110px] rounded bg-muted/40 animate-pulse" />
          <div className="h-5 w-24 mx-auto rounded bg-muted/40 animate-pulse" />
          <div className="space-y-2 mt-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-4 w-full rounded bg-muted/30 animate-pulse"
              />
            ))}
          </div>
        </div>
      </CardShell>
    );
  }

  if (noScoreYet) {
    return (
      <CardShell onRefresh={onRefresh} isFetching={false}>
        <div className="py-6 text-center text-xs text-muted-foreground leading-relaxed">
          Score non ancora calcolato per questo ticker — sarà disponibile al
          prossimo scan.
        </div>
      </CardShell>
    );
  }

  if (isError || !data) {
    return (
      <CardShell onRefresh={onRefresh} isFetching={false}>
        <div className="py-6 text-center text-xs text-muted-foreground">
          Errore nel caricamento dello score.
        </div>
      </CardShell>
    );
  }

  const composite = data.composite;
  const compTone = scoreColor(composite);

  return (
    <CardShell onRefresh={onRefresh}>
      {/* Gauge + composite number */}
      <div className="flex flex-col items-center">
        <div className="relative">
          <ScoreGauge score={composite} size={180} />
          {/* Number overlaid in the center of the gauge */}
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
            <span
              className={cn(
                "text-3xl font-bold tabular-nums leading-none",
                compTone,
              )}
            >
              {composite.toFixed(1)}
            </span>
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground mt-1">
              {scoreLabel(composite)}
            </span>
          </div>
        </div>
        {/* Risk-tier chip */}
        <span
          className={cn(
            "mt-2 px-2 py-0.5 rounded border text-[11px] uppercase tracking-wider font-semibold",
            RISK_TONE[data.risk_tier],
          )}
        >
          {RISK_LABEL[data.risk_tier]}
        </span>
      </div>

      {/* Sub-score bars */}
      <div className="mt-4 border-t border-border/40 pt-2">
        {PILLAR_ORDER.map((pillar) => (
          <SubScoreRow
            key={pillar}
            pillar={pillar}
            score={data.sub_scores[pillar]}
            components={data.breakdown[pillar]}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
        <span title={new Date(data.computed_at).toLocaleString("it-IT")}>
          Calcolato {formatRelative(data.computed_at)}
        </span>
      </div>
    </CardShell>
  );
}
