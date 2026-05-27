import { BarChart3 } from "lucide-react";
import { Link } from "react-router-dom";

import type { AlertsByIndexPoint } from "@/api/types";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  data: AlertsByIndexPoint[];
}

/**
 * "Per indice" column of the AlertsCompactPanel. Replaces the
 * Fase-3E placeholder. One bar per index, sorted server-side by
 * alert count desc. Bar width is normalized against the heaviest
 * index in the current 30-day window. Click a row to filter the
 * screener by that index.
 */
export function AlertsByIndexBars({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="px-4 py-8 flex flex-col items-center justify-center text-center min-h-[100px]">
        <BarChart3 className="h-6 w-6 text-muted-foreground mb-2" />
        <div className="text-sm text-muted-foreground">
          Nessun segnale nei 30 giorni.
        </div>
      </div>
    );
  }

  // Normalize bar widths against the top index. The first row gets
  // 100%; the rest scale proportionally. min 4% so even tiny counts
  // remain visible (a 0.5%-wide bar reads as nothing).
  const max = Math.max(...data.map((d) => d.alert_count));
  // Total across all indices → each row's SHARE of the 30-day alert flow,
  // so the user sees concentration ("SPX500 is 58% of everything") not just
  // the raw count.
  const total = data.reduce((s, d) => s + d.alert_count, 0);
  return (
    <ul className="divide-y divide-border/40">
      {data.map((d) => {
        const meta = getIndexMeta(d.index_code);
        const widthPct = max > 0 ? Math.max(4, (d.alert_count / max) * 100) : 0;
        const share = total > 0 ? Math.round((d.alert_count / total) * 100) : 0;
        return (
          <li key={d.index_code}>
            <Link
              to={`/stocks?index=${encodeURIComponent(d.index_code)}`}
              className="block px-3 py-1.5 hover:bg-accent/30 transition-colors"
              title={`${meta.fullName} — filtra screener`}
            >
              <div className="flex items-center gap-2 text-sm">
                {meta.countryCode && (
                  <img
                    src={`/flags/${meta.countryCode}.svg`}
                    alt={meta.country}
                    width={18}
                    height={12}
                    style={{ width: "18px", height: "12px", objectFit: "cover" }}
                    className="rounded-[1px] ring-1 ring-border/60 shrink-0"
                    aria-hidden
                  />
                )}
                <span className="font-semibold tabular-nums shrink-0 w-[68px] truncate">
                  {meta.displayCode}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full bg-gradient-to-r from-amber-300 to-amber-500 dark:from-amber-700 dark:to-amber-500",
                      )}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </div>
                <div className="shrink-0 w-[46px] text-right leading-tight">
                  <div className="font-bold tabular-nums">{d.alert_count}</div>
                  <div
                    className="text-[10px] text-muted-foreground tabular-nums"
                    title={`${share}% dei segnali degli ultimi 30 giorni`}
                  >
                    {share}%
                  </div>
                </div>
              </div>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
