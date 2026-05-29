import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Relative "last updated" label shown to the LEFT of a card's refresh button.
 *
 * Fed by react-query's `dataUpdatedAt` (ms) — the moment the card's data was
 * last written to the cache, which includes the forced-refresh path
 * (`setQueryData`). So right after a successful refresh it flips to "pochi
 * secondi fa", giving immediate confirmation the update landed even when the
 * fetch itself was instant.
 *
 * Re-renders itself every 20s so the label stays current without a card
 * re-render.
 */
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
  updatedAt: number | undefined;
  className?: string;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 20_000);
    return () => window.clearInterval(id);
  }, []);

  if (!updatedAt) return null;
  return (
    <span
      className={cn("text-[10px] leading-none text-muted-foreground", className)}
      title={`Ultimo aggiornamento: ${absolute(updatedAt)}`}
    >
      aggiornato {relative(updatedAt)}
    </span>
  );
}
