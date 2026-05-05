/**
 * Per-sector lucide icon + tone-class mapping. Covers both yfinance
 * canonical names and common variants. Returns sensible fallbacks for
 * unknown sectors.
 */
import {
  Banknote,
  Boxes,
  Briefcase,
  Cpu,
  Factory,
  Heart,
  Layers,
  Lightbulb,
  Pill,
  Radio,
  ShoppingBag,
  ShoppingCart,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  "Technology": Cpu,
  "Energy": Zap,
  "Financial Services": Banknote,
  "Financials": Banknote,
  "Healthcare": Heart,
  "Health Care": Heart,
  "Industrials": Factory,
  "Industrial": Factory,
  "Consumer Cyclical": ShoppingBag,
  "Consumer Discretionary": ShoppingBag,
  "Consumer Defensive": ShoppingCart,
  "Consumer Staples": ShoppingCart,
  "Basic Materials": Boxes,
  "Materials": Boxes,
  "Utilities": Lightbulb,
  "Communication Services": Radio,
  "Communications": Radio,
  "Real Estate": Briefcase,
  "Pharmaceuticals": Pill,
};

export function getSectorIcon(sector: string | null | undefined): LucideIcon {
  if (!sector) return Layers;
  return ICONS[sector] ?? Layers;
}

/* ─── Sector tone classes ───────────────────────────────────────────────── */
/* Tailwind purger requires plain string literals — these MUST stay as a
 * Record<string, string> with literal class strings. Refactoring to template
 * composition will silently strip the classes from the prod bundle. The bug
 * is invisible in dev. (See CLAUDE.md.)
 *
 * Palette logic: each sector gets a distinct hue with consistent saturation,
 * so a row of 12 different earnings chips reads as a coherent set instead
 * of a clown-car. We use the 100/300 light + 900/40-200 dark pattern that
 * matches RISK_TONE / TONE_BG elsewhere — same tonal weight, different hue.
 *
 * Hue choices intentionally avoid duplication of the alert-tone palette
 * (emerald/rose/amber/slate are reserved for bullish/bearish/warning/neutral
 * — using them here would create false semantic associations). */

const FALLBACK_TONE =
  "bg-zinc-100 dark:bg-zinc-800/60 text-zinc-700 dark:text-zinc-200 border-zinc-200/80 dark:border-zinc-700/70";

const FALLBACK_RING = "ring-zinc-300/60 dark:ring-zinc-600/50";

const TONE: Record<string, string> = {
  "Technology":
    "bg-sky-100 dark:bg-sky-950/50 text-sky-800 dark:text-sky-200 border-sky-200/80 dark:border-sky-800/60",
  "Energy":
    "bg-amber-100 dark:bg-amber-950/50 text-amber-800 dark:text-amber-200 border-amber-200/80 dark:border-amber-800/60",
  "Financial Services":
    "bg-violet-100 dark:bg-violet-950/50 text-violet-800 dark:text-violet-200 border-violet-200/80 dark:border-violet-800/60",
  "Financials":
    "bg-violet-100 dark:bg-violet-950/50 text-violet-800 dark:text-violet-200 border-violet-200/80 dark:border-violet-800/60",
  "Healthcare":
    "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-200 border-emerald-200/80 dark:border-emerald-800/60",
  "Health Care":
    "bg-emerald-100 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-200 border-emerald-200/80 dark:border-emerald-800/60",
  "Industrials":
    "bg-stone-200 dark:bg-stone-800/60 text-stone-800 dark:text-stone-200 border-stone-300/80 dark:border-stone-700/60",
  "Industrial":
    "bg-stone-200 dark:bg-stone-800/60 text-stone-800 dark:text-stone-200 border-stone-300/80 dark:border-stone-700/60",
  "Consumer Cyclical":
    "bg-fuchsia-100 dark:bg-fuchsia-950/50 text-fuchsia-800 dark:text-fuchsia-200 border-fuchsia-200/80 dark:border-fuchsia-800/60",
  "Consumer Discretionary":
    "bg-fuchsia-100 dark:bg-fuchsia-950/50 text-fuchsia-800 dark:text-fuchsia-200 border-fuchsia-200/80 dark:border-fuchsia-800/60",
  "Consumer Defensive":
    "bg-teal-100 dark:bg-teal-950/50 text-teal-800 dark:text-teal-200 border-teal-200/80 dark:border-teal-800/60",
  "Consumer Staples":
    "bg-teal-100 dark:bg-teal-950/50 text-teal-800 dark:text-teal-200 border-teal-200/80 dark:border-teal-800/60",
  "Basic Materials":
    "bg-orange-100 dark:bg-orange-950/50 text-orange-800 dark:text-orange-200 border-orange-200/80 dark:border-orange-800/60",
  "Materials":
    "bg-orange-100 dark:bg-orange-950/50 text-orange-800 dark:text-orange-200 border-orange-200/80 dark:border-orange-800/60",
  "Utilities":
    "bg-yellow-100 dark:bg-yellow-950/50 text-yellow-800 dark:text-yellow-200 border-yellow-200/80 dark:border-yellow-800/60",
  "Communication Services":
    "bg-indigo-100 dark:bg-indigo-950/50 text-indigo-800 dark:text-indigo-200 border-indigo-200/80 dark:border-indigo-800/60",
  "Communications":
    "bg-indigo-100 dark:bg-indigo-950/50 text-indigo-800 dark:text-indigo-200 border-indigo-200/80 dark:border-indigo-800/60",
  "Real Estate":
    "bg-rose-100 dark:bg-rose-950/50 text-rose-800 dark:text-rose-200 border-rose-200/80 dark:border-rose-800/60",
  "Pharmaceuticals":
    "bg-lime-100 dark:bg-lime-950/50 text-lime-800 dark:text-lime-200 border-lime-200/80 dark:border-lime-800/60",
};

/** Tailwind classes to tint an earnings chip by sector. Falls back to a
 *  neutral zinc palette for unknown sectors — covers the case where the
 *  fundamentals service hasn't classified a stock yet. */
export function getSectorTone(sector: string | null | undefined): string {
  if (!sector) return FALLBACK_TONE;
  return TONE[sector] ?? FALLBACK_TONE;
}

/* ─── Sector hairline accent (left ribbon on the chip) ──────────────────── */
/* A thin saturated stripe along the left edge of the chip, matching the
 * sector hue at higher saturation than the bg. Adds a printed-stationery
 * feel without dominating the chip surface. */

const RING: Record<string, string> = {
  "Technology": "ring-sky-400/70 dark:ring-sky-500/60",
  "Energy": "ring-amber-400/70 dark:ring-amber-500/60",
  "Financial Services": "ring-violet-400/70 dark:ring-violet-500/60",
  "Financials": "ring-violet-400/70 dark:ring-violet-500/60",
  "Healthcare": "ring-emerald-400/70 dark:ring-emerald-500/60",
  "Health Care": "ring-emerald-400/70 dark:ring-emerald-500/60",
  "Industrials": "ring-stone-400/70 dark:ring-stone-500/60",
  "Industrial": "ring-stone-400/70 dark:ring-stone-500/60",
  "Consumer Cyclical": "ring-fuchsia-400/70 dark:ring-fuchsia-500/60",
  "Consumer Discretionary": "ring-fuchsia-400/70 dark:ring-fuchsia-500/60",
  "Consumer Defensive": "ring-teal-400/70 dark:ring-teal-500/60",
  "Consumer Staples": "ring-teal-400/70 dark:ring-teal-500/60",
  "Basic Materials": "ring-orange-400/70 dark:ring-orange-500/60",
  "Materials": "ring-orange-400/70 dark:ring-orange-500/60",
  "Utilities": "ring-yellow-400/70 dark:ring-yellow-500/60",
  "Communication Services": "ring-indigo-400/70 dark:ring-indigo-500/60",
  "Communications": "ring-indigo-400/70 dark:ring-indigo-500/60",
  "Real Estate": "ring-rose-400/70 dark:ring-rose-500/60",
  "Pharmaceuticals": "ring-lime-400/70 dark:ring-lime-500/60",
};

/** A `ring-` color for the chip's outer ring on hover. Same hue as the
 *  background, higher saturation. Plain literals — purger-safe. */
export function getSectorRing(sector: string | null | undefined): string {
  if (!sector) return FALLBACK_RING;
  return RING[sector] ?? FALLBACK_RING;
}
