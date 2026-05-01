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
      <CardContent className="p-3">
        <div className="text-[9px] uppercase text-muted-foreground">Dati aggiornati</div>
        <div className="text-xs font-bold mt-0.5 tabular-nums">{formatShort(computedAt)}</div>
        {isStale && (
          <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">⚠ Dati &gt; 24h</div>
        )}
        <div className="text-[10px] text-blue-600 dark:text-blue-400 mt-1">
          Prossimo scan: {formatShort(nextScanAt)}
        </div>
      </CardContent>
    </Card>
  );
}
