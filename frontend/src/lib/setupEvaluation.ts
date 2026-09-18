import type { LiveQuote } from "@/api/types";
import type { Setup } from "@/hooks/useSetups";

/** Other detectors' levels may be support or invalidation, not a price gate. */
export function setupPriceComparison(setup: Setup, quote?: LiveQuote): "above" | "below" | null {
  if (setup.status !== "active" || setup.detector !== "trend_pullback") return null;
  const level = setup.annotations?.levels?.find((l) => l.label === "EMA50");
  const evaluation = setup.annotations?.evaluation;
  const currency = evaluation?.currency ?? setup.currency;
  const evaluatedAt = Date.parse(setup.last_seen_at ?? "");
  // Legacy rows only record a scan timestamp. A later calendar date is a
  // conservative comparison; never reconstruct their unrecorded input price.
  const barDate = evaluation?.bar_date ?? setup.last_seen_at?.slice(0, 10);
  if (!level || !Number.isFinite(level.price) || !quote || quote.ticker !== setup.ticker
    || quote.error || quote.market_state === "STALE" || !quote.as_of_date
    || !barDate || quote.as_of_date <= barDate || !Number.isFinite(evaluatedAt)
    || !Number.isFinite(quote.fetched_at) || quote.fetched_at * 1000 <= evaluatedAt
    || !currency || quote.currency !== currency
    || quote.price == null || !Number.isFinite(quote.price)) return null;
  if (setup.tone === "bull" && quote.price > level.price) return "above";
  if (setup.tone === "bear" && quote.price < level.price) return "below";
  return null;
}

export function setupPrice(value: number, currency?: string | null): string {
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 2 })}${currency ? ` ${currency}` : ""}`;
}

export function setupDate(value: string): string {
  return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString("it-IT");
}
