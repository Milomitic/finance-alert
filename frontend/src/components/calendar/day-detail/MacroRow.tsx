import { ExternalLink, Landmark } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { MacroEvent } from "@/api/types";
import {
  IMPORTANCE_BG,
  IMPORTANCE_LABEL,
  regionFlag,
  regionFlagAsset,
  regionLabel,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { ImportanceDots } from "../ImportanceDots";

/* ─── Macro row (kept as card — different shape than tabular earnings) ──── */

export function MacroRow({ event }: { event: MacroEvent }) {
  const flagAsset = regionFlagAsset(event.region);
  // V3.4: card background neutral; importance hue moves to a small
  // chip on the right. The previous full-card rose tint for high-
  // importance events screamed too loud and didn't leave a visual
  // budget for the actual data — that's the user's main complaint.
  const importanceChipTone = IMPORTANCE_BG[event.importance];
  const hasInsight =
    event.prev_value != null || (event.history?.length ?? 0) > 0;
  return (
    <div className="relative rounded-lg border border-border/60 bg-card overflow-hidden py-2 px-3">
      <div className="flex items-center gap-2 flex-wrap">
        {flagAsset ? (
          <img
            src={`/flags/${flagAsset}.svg`}
            alt={event.region ?? ""}
            width={22}
            height={16}
            style={{ width: "22px", height: "16px", objectFit: "cover" }}
            className="rounded-[2px] ring-1 ring-black/10 dark:ring-white/10 shrink-0"
            aria-hidden
          />
        ) : (
          <span className="text-base leading-none shrink-0" aria-hidden>
            {regionFlag(event.region)}
          </span>
        )}
        <Landmark className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-[14px] font-semibold leading-tight truncate flex-1 min-w-0">
          {event.label}
        </span>
        {event.release_time && (
          <span
            className="inline-flex items-center gap-0.5 text-[11px] tabular-nums text-muted-foreground shrink-0"
            title={`Orario di rilascio: ${event.release_time} UTC. Convertilo nel tuo fuso aggiungendo / sottraendo l'offset locale.`}
          >
            ⏱ {event.release_time} UTC
          </span>
        )}
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground shrink-0">
          {regionLabel(event.region)}
        </span>
        {/* Importance label — the ONLY surface that carries the rose/amber
            tint. Compact chip on the right, not a full card flood. */}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold shrink-0",
            importanceChipTone,
          )}
        >
          <ImportanceDots
            importance={event.importance}
            size="h-1.5 w-1.5"
            gap="gap-0.5"
          />
          {IMPORTANCE_LABEL[event.importance]}
        </span>
      </div>
      {hasInsight && <MacroInsightStrip event={event} />}
    </div>
  );
}

/* ─── FRED-driven insight strip ────────────────────────────────────────── *
 *
 * Shown only when the event carries prev_value / change_pct / history
 * from the FRED join. Three-part layout:
 *   - Prev value (e.g. "Prec. 3.2%")
 *   - Change vs prior (colored arrow + pct, e.g. "▲ +0.4%")
 *   - Mini sparkline of the last ~12 observations
 *
 * The "consensus" piece referenced in the user spec isn't yet sourced
 * (FRED doesn't publish forecasts; we'd need TradingEconomics or a
 * broker feed for that). Hidden until that integration ships rather
 * than rendering an empty placeholder.
 */
function MacroInsightStrip({ event }: { event: MacroEvent }) {
  const [expanded, setExpanded] = useState(false);
  const prev = event.prev_value;
  const prevDate = event.prev_date;
  const prior = event.prior_value;
  const unit = event.unit ?? "";
  const history = event.history ?? [];
  // Phase 3G: consensus + actual + surprise from Forexfactory weekly XML.
  // The "Δ vs prec." slot was removed per user feedback — it was
  // misleading on rate decisions (a percent-change reading on a 3.75%
  // rate is meaningless) and noisy elsewhere. Only the "Sorpresa vs
  // atteso" axis is editorially useful pre/post release.
  const expected = event.expected_value;
  const actual = event.actual_value;
  const surprise = event.surprise_pct;
  // The displayed "Attuale" value: prefer the post-release actual, fall
  // back to the latest published prev_value (FRED) so the panel always
  // shows a number when one exists.
  const attuale = actual ?? prev;
  const attualeTone =
    actual != null && expected != null
      ? actual > expected
        ? "pos"
        : actual < expected
          ? "neg"
          : "neutral"
      : "neutral";

  return (
    <div className="mt-2.5 pt-2.5 border-t border-border/40 space-y-2.5">
      {/* Primary KPI strip — Investing-style "Attuale / Previsto / Precedente"
          with Attuale visually dominating. The previous 3-column "Ultimo /
          Atteso / Sorpresa" is replaced because the user explicitly
          asked for clearer separation between the latest reading and the
          comparison axes (forecast + prior) on a single visual line. */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <KpiSlot
          label="Attuale"
          hint="Valore della release. Quando esiste un consensus, il colore segue il segno della sorpresa (verde = sopra atteso, rosso = sotto)."
          value={attuale}
          unit={unit}
          tone={attualeTone}
          big
          dateBadge={actual == null && prevDate ? formatMacroDate(prevDate) : undefined}
          // % variation vs Precedente, shown beneath the Attuale value
          // so the operator reads the trend direction at a glance
          // ("inflation up 0.2pp vs last release"). Hidden for rate
          // decisions (handled below via the `compareTo` heuristic).
          compareTo={prior ?? null}
        />
        <KpiSlot
          label="Previsto"
          hint="Consensus forecast (mediana analisti) dal feed Forexfactory. Disponibile per i principali eventi US/EU/UK/JP."
          value={expected ?? null}
          unit={unit}
        />
        <KpiSlot
          label="Precedente"
          hint="Valore della release precedente. Permette di leggere la direzione del trend a colpo d'occhio."
          value={prior ?? null}
          unit={unit}
        />
      </div>

      {/* Surprise badge — separate row, only when meaningful. Replaces the
          old "Sorpresa" 3rd column so Attuale/Previsto/Precedente can use
          the full width like the user's reference screenshot. */}
      {surprise != null && (
        <div
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums",
            surprise > 0
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
              : surprise < 0
                ? "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300"
                : "bg-muted text-muted-foreground",
          )}
          title={
            expected != null && actual != null
              ? `Atteso ${formatMacroValue(expected, unit)} → Uscito ${formatMacroValue(actual, unit)}`
              : undefined
          }
        >
          Sorpresa {surprise > 0 ? "▲" : surprise < 0 ? "▼" : "·"}{" "}
          {surprise >= 0 ? "+" : ""}{surprise.toFixed(2)}%
        </div>
      )}

      {/* Mini bar chart of recent releases + history toggle + detail link.
          Replaces the 60×16 sparkline so the user has at-a-glance pattern
          recognition (positive vs negative bars) without leaving the
          panel. The full Investing-style page is one click away. */}
      {history.length >= 2 && (
        <div className="flex items-center gap-2 flex-wrap">
          <MacroMiniBars history={history.slice(-12)} />
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-0.5"
            aria-expanded={expanded}
          >
            {expanded ? "Riduci ▴" : "Storico ▾"}
          </button>
          {event.series_id != null && (
            <Link
              to={`/macro/${event.series_id}`}
              className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
              title="Apri la pagina di dettaglio dell'indicatore"
            >
              Apri dettaglio
              <ExternalLink className="h-3 w-3" />
            </Link>
          )}
        </div>
      )}

      {expanded && history.length >= 2 && (
        <ExtendedHistoryChart history={history} unit={unit} />
      )}
    </div>
  );
}

/* ─── KpiSlot — Investing-style header KPI cell ─────────────────────────── */

function KpiSlot({
  label,
  hint,
  value,
  unit,
  tone,
  big,
  dateBadge,
  compareTo,
}: {
  label: string;
  hint: string;
  value: number | null | undefined;
  unit: string;
  tone?: "pos" | "neg" | "neutral";
  big?: boolean;
  dateBadge?: string;
  /** Previous reading. When provided AND meaningful (see below), the
   *  slot renders a "Δ ±N% vs prec." sub-line so the user can read the
   *  trend direction without doing the math. */
  compareTo?: number | null;
}) {
  const valueTone =
    tone === "pos"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "neg"
        ? "text-rose-600 dark:text-rose-400"
        : "text-foreground";

  // Variation vs the comparison reading. Computed as relative change
  // for indicators where it makes sense ("CPI +0.5% vs prior"); skipped
  // for rate decisions where a relative read is misleading (a Fed move
  // from 3.75% → 4.00% reads as "+6.67%" which is confusing — that's
  // what the absolute level + the bps shift convey). Heuristic: the
  // unit "pct" identifies rate indicators in this codebase; we suppress
  // the relative pct change for those and show ΔPP (percentage points)
  // instead, which is the standard way to talk about rate moves.
  const isRate = unit === "pct";
  let deltaLabel: string | null = null;
  let deltaTone: "pos" | "neg" | "neutral" = "neutral";
  if (value != null && compareTo != null && compareTo !== 0) {
    const diff = value - compareTo;
    deltaTone = diff > 0 ? "pos" : diff < 0 ? "neg" : "neutral";
    if (isRate) {
      // Percentage points (ΔPP) for rate decisions / CPI rates: a move
      // from 3.75 → 4.00 reads as "+0.25 pp", which is unambiguous.
      const sign = diff > 0 ? "+" : "";
      deltaLabel = `${sign}${diff.toFixed(2)} pp vs prec.`;
    } else {
      // Relative percent change for index/level/dollars indicators.
      const pct = (diff / Math.abs(compareTo)) * 100;
      const sign = pct > 0 ? "+" : "";
      deltaLabel = `${sign}${pct.toFixed(1)}% vs prec.`;
    }
  }

  return (
    <div className="flex flex-col gap-0.5 min-w-0" title={hint}>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/80">
        {label}
      </span>
      <span
        className={cn(
          "font-bold tabular-nums leading-tight",
          big ? "text-lg" : "text-sm",
          valueTone,
        )}
      >
        {value != null ? formatMacroValue(value, unit) : <span className="text-muted-foreground italic font-normal">—</span>}
      </span>
      {deltaLabel && (
        <span
          className={cn(
            "text-[10.5px] tabular-nums font-medium",
            deltaTone === "pos" && "text-emerald-600 dark:text-emerald-400",
            deltaTone === "neg" && "text-rose-600 dark:text-rose-400",
            deltaTone === "neutral" && "text-muted-foreground",
          )}
        >
          {deltaLabel}
        </span>
      )}
      {dateBadge && (
        <span className="text-[9px] text-muted-foreground/70 tabular-nums">
          {dateBadge}
        </span>
      )}
    </div>
  );
}

/* ─── MacroMiniBars — 90×24 bar chart of recent releases ────────────────── */

function MacroMiniBars({
  history,
}: {
  history: { date: string; value: number | null }[];
}) {
  const pts = history.filter(
    (p): p is { date: string; value: number } =>
      p.value != null && Number.isFinite(p.value),
  );
  if (pts.length < 2) return null;
  const W = 90;
  const H = 24;
  const max = Math.max(...pts.map((p) => Math.abs(p.value)));
  const barW = W / pts.length;
  const zeroY = H / 2;
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="block"
      aria-hidden
    >
      {/* Zero baseline so positive/negative bars have visual context */}
      <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke="currentColor" strokeWidth="0.5" opacity="0.25" />
      {pts.map((p, i) => {
        const h = max > 0 ? Math.abs(p.value / max) * (H / 2 - 1) : 0;
        const x = i * barW + barW * 0.15;
        const w = barW * 0.7;
        const y = p.value >= 0 ? zeroY - h : zeroY;
        return (
          <rect
            key={i}
            x={x}
            y={y}
            width={w}
            height={Math.max(h, 0.5)}
            fill={p.value >= 0 ? "#1ed760" : "#f43f5e"}
            opacity={i === pts.length - 1 ? 1 : 0.7}
          />
        );
      })}
    </svg>
  );
}

/* `Slot` removed — replaced by `KpiSlot` defined alongside MacroInsightStrip
 * which carries the bigger Investing-style typography + tone-aware Attuale. */

/** Taller chart of the last ~36 observations. Used when the user
 *  expands the macro insight strip in the detail panel. */
function ExtendedHistoryChart({
  history,
  unit,
}: {
  history: { date: string; value: number | null }[];
  unit: string;
}) {
  const pts = history.filter(
    (p): p is { date: string; value: number } =>
      p.value != null && Number.isFinite(p.value),
  );
  if (pts.length < 2) return null;
  const W = 360;
  const H = 80;
  const pad = 4;
  const min = Math.min(...pts.map((p) => p.value));
  const max = Math.max(...pts.map((p) => p.value));
  const range = max - min || 1;
  const points = pts.map((p, i) => {
    const x = pad + (i / (pts.length - 1)) * (W - pad * 2);
    const y = H - pad - ((p.value - min) / range) * (H - pad * 2);
    return { x, y, value: p.value, date: p.date };
  });
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  const last = points[points.length - 1];
  return (
    <div className="rounded border border-current/15 bg-current/5 p-2">
      <div className="flex items-baseline justify-between text-[10px] opacity-70 tabular-nums mb-1">
        <span>{formatMacroDate(pts[0].date)}</span>
        <span className="opacity-90 italic">
          {pts.length} osservazioni · max {formatMacroValue(max, unit)} · min{" "}
          {formatMacroValue(min, unit)}
        </span>
        <span>{formatMacroDate(pts[pts.length - 1].date)}</span>
      </div>
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="block"
        aria-hidden
      >
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle
          cx={last.x}
          cy={last.y}
          r="3"
          fill="currentColor"
          stroke="white"
          strokeWidth="1"
        />
      </svg>
      <div className="text-[10px] opacity-70 mt-1 text-right tabular-nums">
        Ultimo:{" "}
        <span className="font-semibold">
          {formatMacroValue(last.value, unit)}
        </span>
        {" · "}
        {formatMacroDate(last.date)}
      </div>

      {/* Tabular history. Per user feedback (Phase 3G), the "Δ vs prec."
          column was dropped — comparing raw observations of e.g. CPI
          index numbers via percent-change is structurally noisy and
          not the editorially useful number. We keep "Periodo" + "Valore"
          and leave Atteso/Sorpresa as placeholders for past observations
          since Forexfactory's consensus is only published the week of
          the release; historical consensus values aren't free to
          backfill (would need TradingEconomics). */}
      <div className="mt-2 pt-2 border-t border-current/15 overflow-x-auto">
        <table className="w-full text-[11px] tabular-nums">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider opacity-60">
              <th className="text-left font-semibold pb-1">Periodo</th>
              <th className="text-right font-semibold pb-1">Valore</th>
            </tr>
          </thead>
          <tbody>
            {pts
              .slice(-8)
              .map((p) => (
                <tr key={p.date} className="border-t border-current/10">
                  <td className="py-1 text-left">{formatMacroDate(p.date)}</td>
                  <td className="py-1 text-right font-semibold">
                    {formatMacroValue(p.value, unit)}
                  </td>
                </tr>
              ))
              .reverse()}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Format a YYYY-MM-DD ISO date as Italian short ("15 mar 2026"). */
function formatMacroDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });
}

/** Format a macro observation value for display. `unit` switches the
 *  suffix: "pct" / "yield" → "%", "level" → raw with K/M/B grouping,
 *  "index" → 1 decimal, else default 2 decimals. */
function formatMacroValue(v: number, unit: string): string {
  if (!Number.isFinite(v)) return "—";
  if (unit === "pct" || unit === "yield") {
    return `${v.toFixed(2)}%`;
  }
  if (unit === "level") {
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toFixed(0);
  }
  if (unit === "index") return v.toFixed(1);
  return v.toFixed(2);
}

/* `MacroSparkline` removed — replaced by `MacroMiniBars` (a small
 * positive/negative bar chart) defined alongside MacroInsightStrip.
 * The bars give better at-a-glance pattern recognition than a line
 * sparkline for indicators whose sign matters (CPI MoM, retail sales). */
