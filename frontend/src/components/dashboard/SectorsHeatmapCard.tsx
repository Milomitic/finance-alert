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
      <CardContent className="p-3">
        <div className="text-[10px] font-semibold uppercase text-muted-foreground mb-1">Sectors (Avg Δ%)</div>
        {sectors.length === 0 ? (
          <div className="text-[10px] text-muted-foreground text-center py-4">Nessun settore</div>
        ) : (
          <table className="w-full text-[10px] tabular-nums">
            <tbody>
              {sectors.map((s) => (
                <tr key={s.sector}>
                  <td className="px-1 py-0.5 truncate max-w-[120px]">{s.sector}</td>
                  <td className={`px-2 py-0.5 text-right font-semibold ${bgFor(s.avg_change_pct)}`}>
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
