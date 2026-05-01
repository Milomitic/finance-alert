import type { SectorBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  sectors: SectorBreadth[];
}

function bgFor(change: number): string {
  if (change >= 1.0) return "bg-green-300 dark:bg-green-800/60 text-green-900 dark:text-green-100";
  if (change >= 0.5) return "bg-green-200 dark:bg-green-900/60 text-green-900 dark:text-green-100";
  if (change >= 0.0) return "bg-green-100 dark:bg-green-900/40 text-green-900 dark:text-green-100";
  if (change >= -0.5) return "bg-red-100 dark:bg-red-900/40 text-red-900 dark:text-red-100";
  if (change >= -1.0) return "bg-red-200 dark:bg-red-900/60 text-red-900 dark:text-red-100";
  return "bg-red-300 dark:bg-red-800/60 text-red-900 dark:text-red-100";
}

export function SectorsHeatmapCard({ sectors }: Props) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Sectors (Avg Δ%)</div>
        {sectors.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-6">Nessun settore</div>
        ) : (
          <table className="w-full text-xs tabular-nums">
            <tbody>
              {sectors.map((s) => (
                <tr key={s.sector}>
                  <td className="px-2 py-1.5 truncate max-w-[140px]">{s.sector}</td>
                  <td className={`px-3 py-1.5 text-right font-semibold w-[60%] ${bgFor(s.avg_change_pct)}`}>
                    {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
