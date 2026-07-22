import { AlertTriangle, CheckCircle2, Database, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useCatalogStatus, useTriggerCatalogRefresh } from "@/hooks/useCatalogStatus";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";


/* ─── Catalog refresh panel ─────────────────────────────────────────────── */

export function CatalogRefreshPanel() {
  const status = useCatalogStatus();
  const trigger = useTriggerCatalogRefresh();
  const indices = status.data?.indices ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Database}
          label="Stato refresh catalogo"
          right={
            <Button
              size="sm"
              variant="outline"
              disabled={trigger.isPending}
              onClick={() => trigger.mutate(null)}
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5 mr-1",
                  trigger.isPending && "animate-spin",
                )}
              />
              Refresh tutti
            </Button>
          }
          className="mb-3"
        />

        {status.isLoading ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Caricamento…
          </div>
        ) : status.isError ? (
          <div className="py-6">
            <QueryError message="dello stato catalogo" onRetry={status.refetch} isRetrying={status.isFetching} />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Indice</th>
                  <th className="text-left px-3 py-2 font-semibold">Stato</th>
                  <th className="text-right px-3 py-2 font-semibold">
                    Ultimo refresh
                  </th>
                  <th className="text-right px-3 py-2 font-semibold">+/-/=</th>
                  <th className="text-right px-3 py-2 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {indices.map((idx) => {
                  const meta = getIndexMeta(idx.index_code);
                  const completed = idx.last_completed_at
                    ? new Date(idx.last_completed_at).toLocaleString("it-IT", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—";
                  return (
                    <tr
                      key={idx.index_code}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          {meta.countryCode && (
                            <img
                              src={`/flags/${meta.countryCode}.svg`}
                              alt={meta.country}
                              width={20}
                              height={14}
                              style={{ width: "20px", height: "14px", objectFit: "cover" }}
                              className="rounded-[1px] ring-1 ring-border/60 shrink-0"
                              aria-hidden
                            />
                          )}
                          <span className="font-semibold">{meta.displayCode}</span>
                          <span className="text-xs text-muted-foreground">
                            {meta.fullName}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {idx.last_status === "success" && (
                          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            success
                          </span>
                        )}
                        {idx.last_status === "failed" && (
                          <span
                            className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400"
                            title={idx.error_message ?? ""}
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            failed
                          </span>
                        )}
                        {idx.last_status === "in_progress" && (
                          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            in corso
                          </span>
                        )}
                        {idx.last_status == null && (
                          <span className="text-muted-foreground">mai</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2 text-muted-foreground">
                        {completed}
                      </td>
                      <td className="text-right px-3 py-2">
                        {idx.stocks_added != null ? (
                          <span>
                            <span className="text-emerald-700 dark:text-emerald-400">
                              +{idx.stocks_added}
                            </span>
                            {" / "}
                            <span className="text-blue-700 dark:text-blue-400">
                              ~{idx.stocks_updated ?? 0}
                            </span>
                            {" / "}
                            <span className="text-rose-700 dark:text-rose-400">
                              -{idx.stocks_removed ?? 0}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={trigger.isPending}
                          onClick={() => trigger.mutate(idx.index_code)}
                          title={`Refresh ${meta.displayCode}`}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              I refresh leggono Wikipedia per aggiornare i constituent
              di ciascun indice. "+/~/-": aggiunti / aggiornati /
              rimossi vs il run precedente.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
