import {
  CalendarClock,
  Flame,
  Gauge,
  Globe,
  Landmark,
  type LucideIcon,
} from "lucide-react";

import type { MacroImportance } from "@/api/types";

/* ─── Macro importance tone classes ─────────────────────────────────────── */
/* Tailwind purger requires plain string literals — these MUST stay as
 * Record<MacroImportance, string> with literal class strings (CLAUDE.md).
 *
 * The palette deliberately mirrors RISK_TONE in scoreMeta.ts for high/low
 * (rose/slate) but uses amber for medium — different from the moderate-risk
 * sky color so the macro chips don't read as "risk tier" badges by accident.
 * Macros are about scheduled volatility, not portfolio risk. */

export const IMPORTANCE_BG: Record<MacroImportance, string> = {
  high: "bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-200 border-rose-300/80 dark:border-rose-800/70",
  medium:
    "bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border-amber-300/80 dark:border-amber-800/70",
  low: "bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-200 border-slate-300/80 dark:border-slate-700/60",
};

/** Saturated solid bar used as the chip's left ribbon — the "stamp" cue. */
export const IMPORTANCE_RIBBON: Record<MacroImportance, string> = {
  high: "bg-rose-500 dark:bg-rose-400",
  medium: "bg-amber-500 dark:bg-amber-400",
  low: "bg-slate-400 dark:bg-slate-500",
};

export const IMPORTANCE_DOT: Record<MacroImportance, string> = {
  high: "bg-rose-500 dark:bg-rose-400 shadow-[0_0_0_3px_rgba(244,63,94,0.18)]",
  medium:
    "bg-amber-500 dark:bg-amber-400 shadow-[0_0_0_3px_rgba(245,158,11,0.18)]",
  low: "bg-slate-400 dark:bg-slate-500",
};

export const IMPORTANCE_LABEL: Record<MacroImportance, string> = {
  high: "Alta",
  medium: "Media",
  low: "Bassa",
};

export const IMPORTANCE_ICON: Record<MacroImportance, LucideIcon> = {
  high: Flame,
  medium: Gauge,
  low: Globe,
};

/** How many of the 3 dots are "filled" for a given importance tier.
 *  Three small dots in a row read as a star-rating-style importance scale
 *  (1/3 = low, 2/3 = medium, 3/3 = high). The visual is more legible than
 *  the previous shape+color code at the chip-preview scale (h-6) where
 *  iconography becomes a blur.
 *
 *  Tailwind purger contract: keep these as plain literal class strings —
 *  see CLAUDE.md notes on the tone-class purge bug. */
export const IMPORTANCE_FILLED_COUNT: Record<MacroImportance, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

/** Filled-dot tone classes per importance — same hue family as
 *  `IMPORTANCE_RIBBON` so the visual language stays cohesive across
 *  the chip, the day-detail panel, and the legend. */
export const IMPORTANCE_FILLED_DOT: Record<MacroImportance, string> = {
  high: "bg-rose-500 dark:bg-rose-400",
  medium: "bg-amber-500 dark:bg-amber-400",
  low: "bg-slate-500 dark:bg-slate-400",
};

/** Empty-dot tone — same across all tiers (the "off" indicator). */
export const IMPORTANCE_EMPTY_DOT =
  "bg-muted-foreground/25 dark:bg-muted-foreground/30";

/* ─── Region label/flag mapping ─────────────────────────────────────────── */
/* Two-letter code → Italian label + emoji flag. Italian first because the
 * rest of the UI is Italian (the chip subtitle reads "Stati Uniti · CPI",
 * not "US · CPI"). Falls through to the raw code for unmapped regions. */

const REGION_LABEL: Record<string, string> = {
  US: "Stati Uniti",
  EU: "Eurozona",
  EZ: "Eurozona",
  UK: "Regno Unito",
  GB: "Regno Unito",
  JP: "Giappone",
  CN: "Cina",
  CH: "Svizzera",
  CA: "Canada",
  AU: "Australia",
  IT: "Italia",
  DE: "Germania",
  FR: "Francia",
  GLOBAL: "Globale",
};

const REGION_FLAG: Record<string, string> = {
  US: "🇺🇸",
  EU: "🇪🇺",
  EZ: "🇪🇺",
  UK: "🇬🇧",
  GB: "🇬🇧",
  JP: "🇯🇵",
  CN: "🇨🇳",
  CH: "🇨🇭",
  CA: "🇨🇦",
  AU: "🇦🇺",
  IT: "🇮🇹",
  DE: "🇩🇪",
  FR: "🇫🇷",
  GLOBAL: "🌐",
};

export function regionLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return REGION_LABEL[code.toUpperCase()] ?? code.toUpperCase();
}

export function regionFlag(code: string | null | undefined): string {
  if (!code) return "📅";
  return REGION_FLAG[code.toUpperCase()] ?? "📅";
}

/* ─── Date helpers ──────────────────────────────────────────────────────── */
/* All work in local time on date-only strings (YYYY-MM-DD). The backend
 * sends ISO dates, never datetimes — there's no timezone ambiguity to
 * resolve here. Avoid `new Date("2026-05-08")` which UTC-anchors and can
 * shift by a day in negative offsets — we parse the string directly. */

/** Parse a YYYY-MM-DD string into a local-midnight Date. Safe across
 *  timezones — no UTC drift. */
export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/** Serialize a local Date back into YYYY-MM-DD. */
export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Today as YYYY-MM-DD in the user's local timezone. */
export function todayISO(): string {
  return toISODate(new Date());
}

/** Are these two ISO date strings the same calendar day? */
export function isSameISODay(a: string | null | undefined, b: string): boolean {
  if (!a) return false;
  return a === b;
}

/** Italian month-name + year formatter for the page header. The Intl API
 *  is browser-built-in — no extra dep. */
export function formatMonthLabel(d: Date): string {
  const f = new Intl.DateTimeFormat("it-IT", {
    month: "long",
    year: "numeric",
  });
  // Capitalize the first letter — Italian dateformat returns lowercase
  // "maggio 2026" but the page header reads better as "Maggio 2026".
  const s = f.format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Short Italian weekday names for the day-of-week strip. Monday-first
 *  (Italian locale convention). 3-letter uppercase to fit in the strip
 *  without wrapping on dense weeks. */
export const ITALIAN_WEEKDAYS_MON_FIRST: ReadonlyArray<{
  short: string;
  long: string;
  /** Sunday-based index (0=Sun). Used to test against Date.getDay(). */
  jsDayIndex: number;
}> = [
  { short: "Lun", long: "Lunedì", jsDayIndex: 1 },
  { short: "Mar", long: "Martedì", jsDayIndex: 2 },
  { short: "Mer", long: "Mercoledì", jsDayIndex: 3 },
  { short: "Gio", long: "Giovedì", jsDayIndex: 4 },
  { short: "Ven", long: "Venerdì", jsDayIndex: 5 },
  { short: "Sab", long: "Sabato", jsDayIndex: 6 },
  { short: "Dom", long: "Domenica", jsDayIndex: 0 },
];

/** Build the visible 7×N grid for a given month, Monday-first.
 *
 *  Returns 6 weeks (always — keeps the layout stable across months).
 *  Days outside the target month are flagged via `inMonth=false` so the
 *  cell can render them at low opacity per the spec. */
export interface GridDay {
  iso: string;
  day: number;
  inMonth: boolean;
  isWeekend: boolean;
  jsDayIndex: number;
}

export function buildMonthGrid(year: number, month0: number): GridDay[] {
  // First day of the visible target month
  const first = new Date(year, month0, 1);
  const firstJsDay = first.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  // How many days back we need to include from the previous month so the
  // week starts on Monday. If the month starts on Sun (jsDay=0), we need
  // 6 leading days; otherwise jsDay-1.
  const leading = (firstJsDay + 6) % 7;
  // Always emit 6 weeks so the grid layout is stable month-to-month.
  const totalCells = 42;

  const start = new Date(year, month0, 1 - leading);
  const out: GridDay[] = [];
  for (let i = 0; i < totalCells; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    const jsDay = d.getDay();
    out.push({
      iso: toISODate(d),
      day: d.getDate(),
      inMonth: d.getMonth() === month0 && d.getFullYear() === year,
      isWeekend: jsDay === 0 || jsDay === 6,
      jsDayIndex: jsDay,
    });
  }
  return out;
}

/* ─── Number formatters ─────────────────────────────────────────────────── */

/** Compact market-cap formatter — "$2.4T", "$890B", "$45.6B" etc. The
 *  threshold logic mirrors what the rest of the app uses. */
export function formatMarketCap(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1_000_000_000_000) return `$${(v / 1_000_000_000_000).toFixed(2)}T`;
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

export function formatRevenueEstimate(v: number | null | undefined): string {
  return formatMarketCap(v);
}

export function formatEps(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `$${v.toFixed(2)}`;
}

/** Long-form Italian date — "giovedì 8 maggio 2026". Used in the
 *  day-detail panel header. */
export function formatLongDate(iso: string): string {
  const d = parseISODate(iso);
  const f = new Intl.DateTimeFormat("it-IT", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const s = f.format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const CALENDAR_ICON: LucideIcon = CalendarClock;
export const MACRO_ICON: LucideIcon = Landmark;
