import {
  Activity,
  ArrowDownFromLine,
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowUpToLine,
  Bell,
  ChevronsDown,
  ChevronsUp,
  Magnet,
  TrendingDown,
  TrendingUp,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { Alert } from "@/api/types";

/* ─── Shared rule-kind metadata ─────────────────────────────────────────── */
/* One source of truth for the per-rule label / icon / semantic tone used by
 * StockAlertsHistoryCard, AlertDetailDialog, RecentAlertsFeed, and AlertsTable.
 * Centralizing this avoids the drift bug where adding a new rule kind would
 * require updating 4 separate label maps and 4 separate icon maps. */

export type AlertTone = "bullish" | "bearish" | "warning" | "neutral";

export interface AlertKindMeta {
  /** Human-readable label shown in chips and table cells. */
  label: string;
  /** Lucide icon. Picked to match the indicator's directional meaning. */
  icon: LucideIcon;
  /** Semantic tone — drives the chip background / accent color. */
  tone: AlertTone;
}

const META_BY_KIND: Record<string, AlertKindMeta> = {
  rsi_oversold: { label: "RSI Oversold", icon: ArrowDownToLine, tone: "bullish" },
  rsi_overbought: { label: "RSI Overbought", icon: ArrowUpToLine, tone: "bearish" },
  golden_cross: { label: "Golden Cross", icon: TrendingUp, tone: "bullish" },
  death_cross: { label: "Death Cross", icon: TrendingDown, tone: "bearish" },
  volume_spike: { label: "Volume Spike", icon: Activity, tone: "warning" },
  breakout: { label: "Breakout", icon: Zap, tone: "bullish" },
  macd_bullish_cross: { label: "MACD Bullish", icon: TrendingUp, tone: "bullish" },
  macd_bearish_cross: { label: "MACD Bearish", icon: TrendingDown, tone: "bearish" },
  bollinger_breakout: { label: "BB Breakout", icon: Zap, tone: "warning" },
  // Desk/trader signals replacing bollinger_squeeze (retired in
  // backend migration 47c2035665bd_drop_bollinger_squeeze_rules):
  adx_bullish_trend: { label: "ADX Trend ↑", icon: ChevronsUp, tone: "bullish" },
  adx_bearish_trend: { label: "ADX Trend ↓", icon: ChevronsDown, tone: "bearish" },
  gap_up: { label: "Gap Up", icon: ArrowUpFromLine, tone: "bullish" },
  gap_down: { label: "Gap Down", icon: ArrowDownFromLine, tone: "bearish" },
  mean_reversion_long: { label: "Mean Rev. (long)", icon: Magnet, tone: "bullish" },
  mean_reversion_short: { label: "Mean Rev. (short)", icon: Magnet, tone: "bearish" },
  composite: { label: "Composite", icon: Activity, tone: "neutral" },
};

/** Get metadata for a rule kind. NULL/unknown maps to a generic "Price alert"
 *  with a Bell icon — matches the legacy convention used for non-rule alerts
 *  (e.g. user-defined price targets that bypass the rule engine). */
export function getAlertKindMeta(rule_kind: string | null | undefined): AlertKindMeta {
  if (!rule_kind) {
    return { label: "Price alert", icon: Bell, tone: "neutral" };
  }
  return (
    META_BY_KIND[rule_kind] ?? {
      label: rule_kind,
      icon: Bell,
      tone: "neutral",
    }
  );
}

/** Get metadata for an alert as a whole — same as `getAlertKindMeta` for
 *  rule-based alerts, but for PRICE alerts it derives the directional tone
 *  from `snapshot.direction`:
 *
 *    direction "above"  → price broke UP through target → bullish
 *    direction "below"  → price broke DOWN through target → bearish
 *
 *  This gives every Alert (rule-based OR price-target) a usable directional
 *  read, so the UI can show a Bullish/Bearish chip everywhere instead of
 *  collapsing price alerts to a meaningless "neutral" tone.
 *
 *  Use THIS helper everywhere a UI needs the alert's effective meta —
 *  list rows, table cells, dialog headers. Reserve `getAlertKindMeta`
 *  for the few places that genuinely care about kind only (e.g. the
 *  rule-name dropdown in AlertFilters). */
export function getAlertMeta(alert: Alert): AlertKindMeta {
  if (alert.rule_kind) return getAlertKindMeta(alert.rule_kind);
  // Price alert — read direction from the snapshot dict the backend
  // wrote (`backend/app/services/price_alert_service.py`).
  const direction =
    (alert.snapshot as Record<string, unknown> | undefined)?.direction;
  if (direction === "above") {
    return { label: "Price target ↑", icon: TrendingUp, tone: "bullish" };
  }
  if (direction === "below") {
    return { label: "Price target ↓", icon: TrendingDown, tone: "bearish" };
  }
  // Truly unknown (legacy rows without snapshot): keep the generic label.
  return { label: "Price alert", icon: Bell, tone: "neutral" };
}

/* ─── Tone → Tailwind class maps ────────────────────────────────────────── */
/* Kept as plain string maps (not utility functions) so Tailwind's purger sees
 * the literals at build time and doesn't tree-shake them. Don't refactor to
 * template-string composition — the classes will silently disappear in prod. */

export const TONE_BG: Record<AlertTone, string> = {
  bullish: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300",
  bearish: "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300",
  warning: "bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300",
  neutral: "bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300",
};

export const TONE_BORDER_LEFT: Record<AlertTone, string> = {
  bullish: "border-l-emerald-400 dark:border-l-emerald-500",
  bearish: "border-l-rose-400 dark:border-l-rose-500",
  warning: "border-l-amber-400 dark:border-l-amber-500",
  neutral: "border-l-slate-300 dark:border-l-slate-600",
};

export const TONE_TEXT: Record<AlertTone, string> = {
  bullish: "text-emerald-600 dark:text-emerald-400",
  bearish: "text-rose-600 dark:text-rose-400",
  warning: "text-amber-600 dark:text-amber-400",
  neutral: "text-slate-600 dark:text-slate-400",
};

/** Italian one-word label per tone, used by the explicit "tone badge" we
 *  now show alongside the kind chip on the stock-detail alerts row.
 *  Kind label says WHAT it is ("RSI Oversold"), tone label says what
 *  DIRECTION it implies ("Bullish") — two complementary axes. */
export const TONE_LABEL: Record<AlertTone, string> = {
  bullish: "Bullish",
  bearish: "Bearish",
  warning: "Allerta",
  neutral: "Neutro",
};

/** One-line "headline" summary for a snapshot — the single most
 *  informative value the row can show (e.g. "RSI 28.5", "Volume 3.2×",
 *  "MACD ↑ sopra signal"). Used as a subtitle in the stock-detail alert
 *  row so the user sees the "why" without opening the dialog.
 *
 *  Returns null when the rule kind isn't known or the snapshot is empty
 *  — caller renders nothing instead of an empty placeholder. */
export function getSnapshotHeadline(
  rule_kind: string | null | undefined,
  snap: Record<string, unknown> | null | undefined,
): string | null {
  if (!snap) return null;
  const get = (k: string): unknown => snap[k];
  const fmt = (v: unknown, digits = 2): string =>
    typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";

  switch (rule_kind) {
    case "rsi_oversold":
    case "rsi_overbought": {
      const rsi = get("rsi");
      const period = get("period");
      const cmp = rule_kind === "rsi_oversold" ? "≤" : "≥";
      const threshold = get("threshold");
      const periodTxt =
        typeof period === "number" ? `RSI(${period})` : "RSI";
      return `${periodTxt} ${fmt(rsi)} ${cmp} ${fmt(threshold)}`;
    }
    case "golden_cross":
      return "SMA fast ↑ incrociata sopra SMA slow";
    case "death_cross":
      return "SMA fast ↓ incrociata sotto SMA slow";
    case "breakout": {
      const period = get("period");
      const close = get("close");
      const priorMax = get("prior_max");
      return `Chiusura ${fmt(close)} > max ${period ?? "?"}d (${fmt(priorMax)})`;
    }
    case "volume_spike": {
      const ratio = get("ratio");
      const threshold = get("threshold");
      const r =
        typeof ratio === "number" ? `${ratio.toFixed(2)}×` : "—";
      const t =
        typeof threshold === "number" ? `≥ ${threshold}×` : "—";
      return `Volume ${r} media · soglia ${t}`;
    }
    case "macd_bullish_cross":
      return "MACD ↑ sopra signal line";
    case "macd_bearish_cross":
      return "MACD ↓ sotto signal line";
    case "bollinger_breakout": {
      const close = get("close");
      return typeof close === "number"
        ? `Chiusura ${fmt(close)} fuori dalle bande`
        : "Chiusura fuori dalle bande";
    }
    case "adx_bullish_trend":
    case "adx_bearish_trend": {
      const adxV = get("adx");
      const plus = get("plus_di");
      const minus = get("minus_di");
      const cmp = rule_kind === "adx_bullish_trend" ? "+DI > -DI" : "-DI > +DI";
      return `ADX ${fmt(adxV, 1)} · ${cmp} (${fmt(plus, 1)} vs ${fmt(minus, 1)})`;
    }
    case "gap_up":
    case "gap_down": {
      const gap = get("gap_pct");
      const open = get("open");
      const prevClose = get("prev_close");
      const sign = rule_kind === "gap_up" ? "+" : "";
      const gapStr =
        typeof gap === "number" ? `${sign}${(gap * 100).toFixed(2)}%` : "—";
      return `Apertura ${fmt(open)} vs chiusura ${fmt(prevClose)} (gap ${gapStr})`;
    }
    case "mean_reversion_long":
    case "mean_reversion_short": {
      const z = get("z_score");
      const period = get("period");
      const periodTxt =
        typeof period === "number" ? `SMA(${period})` : "SMA";
      const dir =
        rule_kind === "mean_reversion_long" ? "sotto" : "sopra";
      return `Close a ${fmt(z, 2)}σ ${dir} ${periodTxt}`;
    }
    default:
      return null;
  }
}

/* ─── Snapshot rendering ────────────────────────────────────────────────── */
/* The Alert.snapshot field is a free-form JSON dict whose shape depends on
 * the rule_kind that produced it. Rather than render raw JSON in the dialog,
 * the resolver below maps each known kind to a list of "human" rows: a
 * label + value + optional comparison hint (e.g. "RSI 85.02 > 70 threshold").
 * Unknown kinds (composite, future rules) fall back to formatted JSON. */

export interface SnapshotRow {
  label: string;
  /** Pre-formatted display value. */
  value: string;
  /** Optional secondary line shown below the value, e.g. "soglia 70". */
  hint?: string;
  /** Optional tone for the value (overrides the rule-level tone). Used to
   *  highlight when a measured value sits on the "trigger" side of a
   *  threshold (e.g. RSI 85 vs threshold 70 → bearish red). */
  valueTone?: AlertTone;
}

export interface SnapshotResolution {
  rows: SnapshotRow[];
  /** When true, the rows fully describe the snapshot — no need to also dump
   *  the raw JSON. False for partial coverage (we'll render rows + a
   *  collapsed "raw" toggle). */
  complete: boolean;
}

function fmtNum(v: unknown, digits = 2): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtPrice(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `$${v.toFixed(2)}`;
}

/** Translate a typed snapshot dict into labeled UI rows.
 *
 * The labels lean on Italian like the rest of the UI ("soglia", "periodo")
 * because the user-facing strings everywhere else are in Italian; keeping
 * this consistent avoids context-switch when scanning between the table
 * row label and the dialog body.
 */
export function resolveSnapshot(
  rule_kind: string | null | undefined,
  snap: Record<string, unknown>,
): SnapshotResolution {
  const get = (k: string) => snap[k];

  switch (rule_kind) {
    case "rsi_oversold":
    case "rsi_overbought": {
      const rsi = get("rsi") as number | null;
      const period = get("period") as number | null;
      const threshold = get("threshold") as number | null;
      // Tone mirrors the trigger semantics: RSI low → oversold → bullish
      // potential; RSI high → overbought → bearish potential.
      const valueTone: AlertTone =
        rule_kind === "rsi_oversold" ? "bullish" : "bearish";
      const cmp =
        rule_kind === "rsi_oversold"
          ? `≤ ${fmtNum(threshold)} (oversold)`
          : `≥ ${fmtNum(threshold)} (overbought)`;
      return {
        rows: [
          {
            label: `RSI(${period ?? "?"})`,
            value: fmtNum(rsi),
            hint: `soglia ${cmp}`,
            valueTone,
          },
        ],
        complete: true,
      };
    }

    case "golden_cross":
    case "death_cross": {
      const fastSma = get("fast_sma") as number | null;
      const slowSma = get("slow_sma") as number | null;
      const fast = get("fast") as number | null;
      const slow = get("slow") as number | null;
      const valueTone: AlertTone =
        rule_kind === "golden_cross" ? "bullish" : "bearish";
      const arrow = rule_kind === "golden_cross" ? "↑ incrociata sopra" : "↓ incrociata sotto";
      return {
        rows: [
          {
            label: `SMA(${fast ?? "?"})`,
            value: fmtPrice(fastSma),
            hint: arrow,
            valueTone,
          },
          {
            label: `SMA(${slow ?? "?"})`,
            value: fmtPrice(slowSma),
          },
        ],
        complete: true,
      };
    }

    case "breakout": {
      const close = get("close") as number | null;
      const priorMax = get("prior_max") as number | null;
      const period = get("period") as number | null;
      return {
        rows: [
          {
            label: "Chiusura",
            value: fmtPrice(close),
            hint: `breakout sopra il massimo ${period}d`,
            valueTone: "bullish",
          },
          {
            label: `Max precedente ${period ?? "?"}d`,
            value: fmtPrice(priorMax),
          },
        ],
        complete: true,
      };
    }

    case "volume_spike": {
      const ratio = get("ratio") as number | null;
      const window = get("window") as number | null;
      const threshold = get("threshold") as number | null;
      return {
        rows: [
          {
            label: "Volume × media",
            value: ratio != null ? `${ratio.toFixed(2)}×` : "—",
            hint: `soglia ≥ ${threshold}× su finestra ${window}g`,
            valueTone: "warning",
          },
        ],
        complete: true,
      };
    }

    case "macd_bullish_cross":
    case "macd_bearish_cross": {
      const line = get("line") as number | null;
      const signal = get("signal") as number | null;
      const hist = get("hist") as number | null;
      const fast = get("fast") as number | null;
      const slow = get("slow") as number | null;
      const sigP = get("signal_period") as number | null;
      const valueTone: AlertTone =
        rule_kind === "macd_bullish_cross" ? "bullish" : "bearish";
      const arrow =
        rule_kind === "macd_bullish_cross"
          ? "MACD ↑ sopra signal"
          : "MACD ↓ sotto signal";
      return {
        rows: [
          {
            label: `MACD(${fast ?? "?"},${slow ?? "?"},${sigP ?? "?"})`,
            value: fmtNum(line, 4),
            hint: arrow,
            valueTone,
          },
          { label: "Signal line", value: fmtNum(signal, 4) },
          {
            label: "Histogram",
            value: fmtNum(hist, 4),
            valueTone:
              typeof hist === "number"
                ? hist > 0
                  ? "bullish"
                  : "bearish"
                : undefined,
          },
        ],
        complete: true,
      };
    }

    case "bollinger_breakout": {
      const close = get("close") as number | null;
      const upper = get("upper") as number | null;
      const lower = get("lower") as number | null;
      // Direction not always recorded — show both bands and let the user pick
      return {
        rows: [
          {
            label: "Chiusura",
            value: fmtPrice(close),
            valueTone: "warning",
          },
          { label: "Banda superiore", value: fmtPrice(upper) },
          { label: "Banda inferiore", value: fmtPrice(lower) },
        ],
        complete: true,
      };
    }

    case "adx_bullish_trend":
    case "adx_bearish_trend": {
      const adxV = get("adx") as number | null;
      const plus = get("plus_di") as number | null;
      const minus = get("minus_di") as number | null;
      const period = get("period") as number | null;
      const threshold = get("threshold") as number | null;
      const valueTone: AlertTone =
        rule_kind === "adx_bullish_trend" ? "bullish" : "bearish";
      const dirHint =
        rule_kind === "adx_bullish_trend"
          ? "+DI > -DI (trend rialzista forte)"
          : "-DI > +DI (trend ribassista forte)";
      return {
        rows: [
          {
            label: `ADX(${period ?? "?"})`,
            value: fmtNum(adxV, 1),
            hint: `≥ ${fmtNum(threshold, 1)} · ${dirHint}`,
            valueTone,
          },
          { label: "+DI", value: fmtNum(plus, 1) },
          { label: "-DI", value: fmtNum(minus, 1) },
        ],
        complete: true,
      };
    }

    case "gap_up":
    case "gap_down": {
      const open = get("open") as number | null;
      const prev = get("prev_close") as number | null;
      const gap = get("gap_pct") as number | null;
      const threshold = get("threshold_pct") as number | null;
      const valueTone: AlertTone =
        rule_kind === "gap_up" ? "bullish" : "bearish";
      const sign = rule_kind === "gap_up" ? "+" : "";
      const gapStr =
        gap != null ? `${sign}${(gap * 100).toFixed(2)}%` : "—";
      const thresholdStr =
        threshold != null ? `${(threshold * 100).toFixed(1)}%` : "—";
      return {
        rows: [
          {
            label: "Gap (open vs prev close)",
            value: gapStr,
            hint: `soglia ${rule_kind === "gap_up" ? "≥" : "≤"} ${rule_kind === "gap_up" ? "" : "-"}${thresholdStr}`,
            valueTone,
          },
          { label: "Open", value: fmtPrice(open) },
          { label: "Prev close", value: fmtPrice(prev) },
        ],
        complete: true,
      };
    }

    case "mean_reversion_long":
    case "mean_reversion_short": {
      const close = get("close") as number | null;
      const sma = get("sma") as number | null;
      const sigma = get("sigma") as number | null;
      const z = get("z_score") as number | null;
      const period = get("period") as number | null;
      const threshold = get("threshold_sigma") as number | null;
      const valueTone: AlertTone =
        rule_kind === "mean_reversion_long" ? "bullish" : "bearish";
      const sign = rule_kind === "mean_reversion_long" ? "≤ -" : "≥ +";
      const dirCtx =
        rule_kind === "mean_reversion_long"
          ? "estensione anomala al ribasso → bounce atteso"
          : "estensione anomala al rialzo → fade atteso";
      return {
        rows: [
          {
            label: "Z-score",
            value: fmtNum(z, 2),
            hint: `soglia ${sign}${fmtNum(threshold, 1)}σ · ${dirCtx}`,
            valueTone,
          },
          { label: "Close", value: fmtPrice(close) },
          { label: `SMA(${period ?? "?"})`, value: fmtPrice(sma) },
          { label: "σ", value: fmtNum(sigma, 4) },
        ],
        complete: true,
      };
    }

    default:
      return { rows: [], complete: false };
  }
}
