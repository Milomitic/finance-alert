/**
 * Per-sector lucide icon mapping. Covers both yfinance canonical names and
 * common variants. Returns a fallback (Layers) for unknown sectors.
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
