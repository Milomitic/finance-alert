import { Clock } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

interface Props {
  computedAt: string | null | undefined;
  isStale: boolean;
  nextScanAt: string | null;
}

function formatShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function DataFreshnessCard({ computedAt, isStale, nextScanAt }: Props) {
  return (
    <Card>
      <CardContent className="p-4 flex flex-col items-center justify-center text-center h-full">
        <Clock className="h-5 w-5 text-muted-foreground/60 mb-1" />
        <div className="text-xs uppercase text-muted-foreground tracking-wide">Dati aggiornati</div>
        <div className="text-base font-bold mt-1 tabular-nums">{formatShort(computedAt)}</div>
        {isStale && (
          <div className="text-sm text-amber-600 dark:text-amber-400 mt-1">⚠ Dati &gt; 24h</div>
        )}
        <div className="text-sm text-blue-600 dark:text-blue-400 mt-2">
          Prossimo scan: {formatShort(nextScanAt)}
        </div>
      </CardContent>
    </Card>
  );
}
