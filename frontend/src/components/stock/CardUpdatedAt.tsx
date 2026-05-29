import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Relative "last updated" label shown to the LEFT of a card's refresh button.
 *
 * Fed by the backend's TRUE fetch/compute time so it reflects real data age and
 * survives page reloads (unlike react-query's client-side `dataUpdatedAt`).
 * Accepts whatever shape the card has on hand:
 *   - ISO datetime string  → e.g. TechnicalScore/StockScore `computed_at`
 *   - epoch seconds (number < 1e12) → e.g. Fundamentals/News `fetched_at`
 *   - epoch ms (number ≥ 1e12)      → already-ms timestamps
 * After a successful force-refresh the backend stamps "now", so the label flips
 * to "pochi secondi fa", confirming the update landed.
 *
 * Re-renders itself every 20s so the label stays current without a card
 * re-render.
 */
function toMs(v: number | string | null | undefined): number | undefined {
  if (v == null) return undefined;
  if (typeof v === "number") {
    if (!Number.isFinite(v) || v <= 0) return undefined;
    // Heuristic: real epoch-seconds are ~1.7e9 (< 1e12); ms are ~1.7e12.
    return v < 1e12 ? v * 1000 : v;
  }
  const t = Date.parse(v);
  return Number.isNaN(t) ? undefined : t;
}

function relative(ms: number): string {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 45) return "pochi secondi fa";
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

function absolute(ms: number): string {
  try {
    return new Date(ms).toLocaleString("it-IT");
  } catch {
    return "";
  }
}

export function CardUpdatedAt({
  updatedAt,
  className,
}: {
  updatedAt: number | string | null | undefined;
  className?: string;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 20_000);
    return () => window.clearInterval(id);
  }, []);

  const ms = toMs(updatedAt);
  if (!ms) return null;
  return (
    <span
      className={cn("text-[10px] leading-none text-muted-foreground", className)}
      title={`Ultimo aggiornamento: ${absolute(ms)}`}
    >
      aggiornato {relative(ms)}
    </span>
  );
}
