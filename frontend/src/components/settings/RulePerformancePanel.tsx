import { Loader2, TrendingUp } from "lucide-react";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useRulePerformance } from "@/hooks/useRulePerformance";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";


/* ─── Rule performance panel ────────────────────────────────────────────── */

export function RulePerformancePanel() {
  const [days, setDays] = useState(90);
  const q = useRulePerformance(days);
  const items = q.data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={TrendingUp}
          label="Efficacia segnali — forward return"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Finestra:</span>
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value={30}>30 giorni</option>
                <option value={90}>90 giorni</option>
                <option value={180}>180 giorni</option>
                <option value={365}>1 anno</option>
              </select>
            </div>
          }
          className="mb-3"
        />

        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo statistiche…
          </div>
        ) : q.isError ? (
          <div className="py-8">
            <QueryError message="delle statistiche" onRetry={q.refetch} isRetrying={q.isFetching} />
          </div>
        ) : items.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Nessun segnale nel periodo — esegui uno scan per generare
            dati di efficacia.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Segnale</th>
                  <th className="text-right px-3 py-2 font-semibold">N</th>
                  {[1, 5, 20].flatMap((w) => [
                    <th key={`m${w}`} className="text-right px-3 py-2 font-semibold">
                      Media {w}d
                    </th>,
                    <th key={`h${w}`} className="text-right px-3 py-2 font-semibold">
                      Hit {w}d
                    </th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const meta = getAlertKindMeta(row.rule_kind);
                  const Icon = meta.icon;
                  return (
                    <tr
                      key={row.rule_kind}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          <span className="font-semibold">{meta.label}</span>
                          <span
                            className={cn(
                              "px-1.5 py-px rounded text-[10px] uppercase tracking-wider font-semibold",
                              row.tone === "bullish"
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                                : row.tone === "bearish"
                                  ? "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200"
                                  : "bg-muted text-muted-foreground",
                            )}
                          >
                            {row.tone}
                          </span>
                        </span>
                      </td>
                      <td className="text-right px-3 py-2 font-bold">
                        {row.total_alerts}
                      </td>
                      {[1, 5, 20].flatMap((w) => {
                        const s = row.stats[String(w)];
                        return [
                          <td
                            key={`m${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.mean_pct == null
                                ? "text-muted-foreground"
                                : s.mean_pct > 0
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.mean_pct < 0
                                    ? "text-rose-700 dark:text-rose-400"
                                    : "",
                            )}
                            title={
                              s?.median_pct != null
                                ? `Mediana ${s.median_pct.toFixed(2)}%`
                                : undefined
                            }
                          >
                            {s?.mean_pct == null
                              ? "—"
                              : `${s.mean_pct >= 0 ? "+" : ""}${s.mean_pct.toFixed(2)}%`}
                          </td>,
                          <td
                            key={`h${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.hit_rate == null
                                ? "text-muted-foreground"
                                : s.hit_rate >= 0.55
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.hit_rate >= 0.45
                                    ? ""
                                    : "text-rose-700 dark:text-rose-400",
                            )}
                            title={
                              s?.count != null
                                ? `${s.count} osservazioni`
                                : undefined
                            }
                          >
                            {s?.hit_rate == null
                              ? "—"
                              : `${(s.hit_rate * 100).toFixed(0)}%`}
                          </td>,
                        ];
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              "Hit" = % di alert con direzione coerente con il tono del
              segnale entro la finestra (bullish → ritorno positivo,
              bearish → negativo). I segnali neutri non hanno hit-rate.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
