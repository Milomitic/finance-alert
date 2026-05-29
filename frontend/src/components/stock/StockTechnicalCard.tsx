import { scores } from "@/api/scores";
import { Card, CardContent } from "@/components/ui/card";
import { CardErrorOverlay } from "@/components/stock/CardErrorOverlay";
import { CardRefreshButton } from "@/components/stock/CardRefreshButton";
import { CardUpdatedAt } from "@/components/stock/CardUpdatedAt";
import { useCardRefresh } from "@/hooks/useCardRefresh";
import { useStockTechnical } from "@/hooks/useStockTechnical";
import { scoreColor } from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

const DIMS: { key: "trend" | "momentum" | "structure" | "volume" | "rel_strength"; label: string }[] = [
  { key: "trend", label: "Trend" },
  { key: "momentum", label: "Momentum" },
  { key: "structure", label: "Struttura" },
  { key: "volume", label: "Volume" },
  { key: "rel_strength", label: "Forza relativa" },
];

const POSTURE_CLS: Record<string, string> = {
  Forte: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  Neutro: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  Debole: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

/** Continuous technical evaluation card (composite + dimensions + posture),
 *  the technical twin of StockScoreCard. */
export function StockTechnicalCard({ ticker }: { ticker: string | undefined }) {
  const { data, isLoading, noScoreYet } = useStockTechnical(ticker);
  const { refresh, isRefreshing, refreshError } = useCardRefresh({
    queryKey: ["stock-technical", ticker],
    mutationFn: () => scores.recomputeTechnicalForStock(ticker!),
  });
  return (
    <Card>
      <CardContent className="p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
            Valutazione tecnica
          </span>
          <div className="flex items-center gap-2">
            {data && (
              <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", POSTURE_CLS[data.posture] ?? "bg-muted text-muted-foreground")}>
                {data.posture}
              </span>
            )}
            <CardUpdatedAt updatedAt={data?.computed_at} />
            <CardRefreshButton
              onClick={refresh}
              busy={isRefreshing}
              title="Ricalcola score tecnico"
            />
          </div>
        </div>
        {refreshError ? (
          <CardErrorOverlay
            error={refreshError}
            onRetry={refresh}
            retrying={isRefreshing}
          />
        ) : isLoading ? (
          <div className="text-xs text-muted-foreground italic">Caricamento...</div>
        ) : noScoreYet || !data ? (
          <div className="text-xs text-muted-foreground italic">Punteggio tecnico non ancora calcolato.</div>
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <span className={cn("text-3xl font-bold tabular-nums", scoreColor(data.composite))}>
                {data.composite.toFixed(0)}
              </span>
              <span className="text-xs text-muted-foreground">/ 100 composito</span>
            </div>
            <div className="space-y-1">
              {DIMS.map((d) => {
                const v = data[d.key];
                const pct = v != null ? Math.max(0, Math.min(100, v)) : 0;
                return (
                  <div key={d.key} className="flex items-center gap-2">
                    <span className="w-28 text-xs text-foreground/70 shrink-0">{d.label}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-sky-500/70" style={{ width: `${pct}%` }} />
                    </div>
                    <span className={cn("w-8 text-right text-[11px] tabular-nums", v != null ? scoreColor(v) : "text-muted-foreground")}>
                      {v != null ? v.toFixed(0) : "-"}
                    </span>
                  </div>
                );
              })}
            </div>
            {data.signals != null && (
              <div className="text-[11px] text-muted-foreground">
                Segnale recente: confidenza {data.signals.toFixed(0)}%
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
