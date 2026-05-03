import type { SectorBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { getSectorIcon } from "@/lib/sectorMeta";

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
    <Card className="h-full overflow-hidden">
      <CardContent className="p-4 flex flex-col h-full min-h-0">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 shrink-0">Sectors (Avg Δ%)</div>
        {sectors.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center py-6">Nessun settore</div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto">
          {/* Re-balanced: sector name takes the bulk of the row, % stays
              right-aligned with a fixed width tinted by sign. The previous
              w-[60%] on the % cell forced the heatmap blob to be wider than
              the sector label even on long names — flipping it makes the
              text the focal point. */}
          <table className="w-full text-sm tabular-nums table-fixed">
            <colgroup>
              <col style={{ width: "70%" }} />
              <col style={{ width: "30%" }} />
            </colgroup>
            <tbody>
              {sectors.map((s) => {
                const Icon = getSectorIcon(s.sector);
                return (
                  <tr key={s.sector} className="hover:bg-muted/30 transition-colors">
                    <td className="px-2 py-1.5">
                      <span className="inline-flex items-center gap-1.5 min-w-0 w-full">
                        <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate" title={s.sector}>{s.sector}</span>
                      </span>
                    </td>
                    <td className={`px-2 py-1.5 text-right font-semibold ${bgFor(s.avg_change_pct)}`}>
                      {s.avg_change_pct >= 0 ? "+" : ""}{s.avg_change_pct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
