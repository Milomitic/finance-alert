import {
  Activity,
  ArrowUpToLine,
  Bell,
  ChevronsUp,
  TrendingDown,
  TrendingUp,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { Alert } from "@/api/types";

/* ─── Shared alert-kind metadata ────────────────────────────────────────── */
/* One source of truth for the per-kind label / icon / semantic tone used by
 * StockAlertsHistoryCard, AlertDetailDialog, RecentAlertsFeed, and AlertsTable.
 * Rule-kind entries have been removed — the rule engine is retired. Only
 * signals and price alerts exist now. */

export type AlertTone = "bullish" | "bearish" | "warning" | "neutral";

export interface AlertKindMeta {
  /** Human-readable label shown in chips and table cells. */
  label: string;
  /** Lucide icon. Picked to match the indicator's directional meaning. */
  icon: LucideIcon;
  /** Semantic tone — drives the chip background / accent color. */
  tone: AlertTone;
}

/** Get metadata for a rule kind. NULL/unknown maps to a generic "Price alert"
 *  with a Bell icon — matches the legacy convention used for non-rule alerts
 *  (e.g. user-defined price targets that bypass the rule engine). */
export function getAlertKindMeta(rule_kind: string | null | undefined): AlertKindMeta {
  // Signal kinds get a friendly label + icon (no "signal:" prefix). Tone
  // stays neutral here because a bare kind string carries no bull/bear
  // direction - that lives in the per-alert snapshot, which kind-only
  // callers (Top Stocks aggregate, Settings perf table) do not have.
  if (isSignalKind(rule_kind)) {
    const { label, icon } = signalMeta(rule_kind as string);
    return { label, icon, tone: "neutral" };
  }
  return {
    label: rule_kind ?? "Price alert",
    icon: Bell,
    tone: "neutral",
  };
}

/** True when the alert kind is a signal-engine kind ("signal:<name>"). */
export function isSignalKind(rule_kind: string | null | undefined): boolean {
  return typeof rule_kind === "string" && rule_kind.startsWith("signal:");
}

/** Friendly label + icon per signal detector name (the part after "signal:").
 *  Tone is NOT here - it comes from the snapshot's bull/bear field. */
const SIGNAL_META: Record<string, { label: string; icon: LucideIcon }> = {
  volume_breakout: { label: "Volume Breakout", icon: Zap },
  trend_pullback: { label: "Trend + Pullback", icon: TrendingUp },
  rsi_divergence: { label: "Divergenza RSI", icon: Activity },
  squeeze_expansion: { label: "Squeeze + Espansione", icon: ChevronsUp },
  high52_momentum: { label: "Massimo 52 settimane", icon: ArrowUpToLine },
  gap_and_go: { label: "Gap and Go", icon: Zap },
  adx_confirmation: { label: "Conferma ADX", icon: Activity },
  sr_flip: { label: "Flip S/R", icon: Activity },
  structure_break: { label: "Rottura struttura", icon: ChevronsUp },
  hidden_divergence: { label: "Divergenza nascosta", icon: Activity },
  pead: { label: "Drift post-utili", icon: Zap },
  analyst_momentum: { label: "Momentum analisti", icon: TrendingUp },
  macd_divergence: { label: "Divergenza MACD", icon: Activity },
  oversold_reversal: { label: "Inversione ipervenduto", icon: Activity },
  candle_reversal: { label: "Inversione a candela", icon: Activity },
  insider_buy: { label: "Acquisti insider", icon: TrendingUp },
  chart_pattern: { label: "Pattern grafico", icon: Activity },
};

function signalMeta(rule_kind: string): { label: string; icon: LucideIcon } {
  const name = rule_kind.slice("signal:".length);
  return SIGNAL_META[name] ?? { label: name.replace(/_/g, " "), icon: Bell };
}

/** Get metadata for an alert as a whole — for SIGNAL alerts it derives label
 *  and icon from the signal name + tone from the snapshot; for PRICE alerts it
 *  derives the directional tone from `snapshot.direction`:
 *
 *    direction "above"  → price broke UP through target → bullish
 *    direction "below"  → price broke DOWN through target → bearish
 *
 *  This gives every Alert a usable directional read, so the UI can show a
 *  Bullish/Bearish chip everywhere instead of collapsing price alerts to a
 *  meaningless "neutral" tone.
 *
 *  Use THIS helper everywhere a UI needs the alert's effective meta —
 *  list rows, table cells, dialog headers. Reserve `getAlertKindMeta`
 *  for the few places that genuinely care about kind only (e.g. the
 *  rule-name dropdown in AlertFilters). */
export function getAlertMeta(alert: Alert): AlertKindMeta {
  if (isSignalKind(alert.rule_kind)) {
    const { label, icon } = signalMeta(alert.rule_kind as string);
    const snapTone = (alert.snapshot as Record<string, unknown> | undefined)?.tone;
    const tone: AlertTone =
      snapTone === "bull" ? "bullish" : snapTone === "bear" ? "bearish" : "neutral";
    return { label, icon, tone };
  }
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

/* ─── Forza / Probabilità — the two-score signal model ──────────────────── */
/* Since the confidence→(Forza, Probabilità) split, every signal carries two
 * first-class metrics. `Forza` = pattern strength (tone-colored); `Probabilità`
 * = historical hit-rate "di accadimento" (neutral/info-colored). Both are
 * always emitted by the backend (legacy alerts were backfilled), so the
 * helpers below simply read them — no legacy confidence/calibration fallback. */

/** Tooltip copy for Probabilità — surfaced everywhere the metric appears so
 *  users understand it's an educational estimate, not a guarantee.
 *  Honest labeling (2026-07-08): the value is the DETECTOR's historical base
 *  rate from the 10y replay — it does not vary per-signal. Per-factor
 *  adjustments were fitted and REJECTED out-of-sample (no Brier improvement
 *  on either the stock or temporal split), so claiming per-signal precision
 *  would be false. */
export const PROBABILITA_TOOLTIP =
  "Tasso storico del detector (replay 10 anni): quanto spesso segnali di questo " +
  "tipo si sono realizzati sull'orizzonte. È una base rate — uguale per tutti i " +
  "segnali dello stesso detector, non una previsione del singolo segnale né una garanzia.";

/** Forza (pattern strength) for a signal snapshot.
 *  Reads `snapshot.strength`; null when it's not a number. */
export function snapshotForza(
  snap: Record<string, unknown> | null | undefined,
): number | null {
  if (!snap) return null;
  const s = snap["strength"];
  return typeof s === "number" ? Math.round(s) : null;
}

/** Probabilità (historical hit-rate) for a signal snapshot.
 *  Reads `snapshot.probability`; null when it's not a number. */
export function snapshotProbabilita(
  snap: Record<string, unknown> | null | undefined,
): number | null {
  if (!snap) return null;
  const p = snap["probability"];
  return typeof p === "number" ? Math.round(p) : null;
}

/** One-line "headline" summary for a snapshot — the single most
 *  informative value the row can show. For signal alerts, shows Forza,
 *  Probabilità (when present) and the chain length. Returns null for unknown
 *  kinds — caller renders nothing instead of an empty placeholder. */
export function getSnapshotHeadline(
  rule_kind: string | null | undefined,
  snap: Record<string, unknown> | null | undefined,
): string | null {
  if (!snap) return null;
  if (isSignalKind(rule_kind)) {
    const forza = snapshotForza(snap);
    const prob = snapshotProbabilita(snap);
    const chain = snap["chain"];
    const nEvents = Array.isArray(chain) ? chain.length : 0;
    const parts: string[] = [];
    if (forza != null) parts.push(`Forza ${forza}%`);
    if (prob != null) parts.push(`Probabilità ${prob}%`);
    const head = parts.length > 0 ? parts.join(" · ") : "Segnale";
    return nEvents > 0 ? `${head} - ${nEvents} eventi` : head;
  }
  return null;
}

/* ─── Snapshot rendering ────────────────────────────────────────────────── */
/* The Alert.snapshot field is a free-form JSON dict whose shape depends on
 * the kind that produced it. Rather than render raw JSON in the dialog,
 * the resolver below maps known kinds to a list of "human" rows. Unknown
 * kinds fall back to formatted JSON (complete: false). */

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

/** Translate a typed snapshot dict into labeled UI rows.
 *
 * Only signal snapshots are handled explicitly; all other kinds fall back
 * to the raw-JSON toggle (complete: false).
 */
export function resolveSnapshot(
  _rule_kind: string | null | undefined,
  _snap: Record<string, unknown>,
): SnapshotResolution {
  return { rows: [], complete: false };
}

/* ─── Signal nature: continuation vs reversal ───────────────────────────── */
const _CONTINUATION = new Set([
  "volume_breakout", "high52_momentum", "trend_pullback", "squeeze_expansion",
  "gap_and_go", "adx_confirmation", "sr_flip", "structure_break",
  "hidden_divergence", "pead", "analyst_momentum",
]);
const _REVERSAL = new Set([
  "rsi_divergence", "macd_divergence", "oversold_reversal", "candle_reversal",
  "insider_buy",
]);

export type SignalNature = "continuazione" | "inversione" | "misto";

/** Classify a signal as trend-continuation vs reversal. chart_pattern is mixed
 *  and resolved from the chain labels (double top/bottom + H&S = reversal,
 *  triangle/flag = continuation). Null for non-signal alerts. */
export function signalNature(
  rule_kind: string | null | undefined,
  chain?: { label?: string }[],
): SignalNature | null {
  if (!isSignalKind(rule_kind)) return null;
  const name = (rule_kind as string).slice("signal:".length);
  if (_CONTINUATION.has(name)) return "continuazione";
  if (_REVERSAL.has(name)) return "inversione";
  if (name === "chart_pattern") {
    const labels = (chain ?? []).map((c) => (c.label ?? "").toLowerCase()).join(" ");
    if (/doppio|testa e spalle|inverse/.test(labels)) return "inversione";
    if (/triangolo|flag|bandiera|cuneo/.test(labels)) return "continuazione";
    return "misto";
  }
  return "misto";
}

export const NATURE_LABEL: Record<SignalNature, string> = {
  continuazione: "Continuazione",
  inversione: "Inversione",
  misto: "Misto",
};

export const NATURE_BG: Record<SignalNature, string> = {
  continuazione: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300",
  inversione: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-950/50 dark:text-fuchsia-300",
  misto: "bg-muted text-muted-foreground",
};
