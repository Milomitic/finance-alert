import { ArrowDown, ArrowUp, Pencil, Power, Trash2 } from "lucide-react";
import { useState } from "react";

import type { PriceAlert } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PriceAlertDialog } from "@/components/stock/PriceAlertDialog";
import {
  useCreatePriceAlert, useDeletePriceAlert, useStockPriceAlerts, useUpdatePriceAlert,
} from "@/hooks/useStockPriceAlerts";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

export function PriceAlertsCard({ ticker }: Props) {
  const q = useStockPriceAlerts(ticker);
  const create = useCreatePriceAlert(ticker);
  const update = useUpdatePriceAlert(ticker);
  const remove = useDeletePriceAlert(ticker);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<PriceAlert | null>(null);

  const items = q.data ?? [];

  return (
    <>
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Price alerts
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => { setEditing(null); setDialogOpen(true); }}
            >
              + Aggiungi
            </Button>
          </div>
          {items.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-4">
              Nessuna price alert. Click su "+ Aggiungi" o sul chart per crearne una.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {items.map((pa) => {
                const isTriggered = pa.triggered_at != null;
                return (
                  <li
                    key={pa.id}
                    className={cn(
                      "flex items-center gap-2 px-2 py-1.5 rounded text-sm border",
                      !pa.enabled && "opacity-50",
                      isTriggered && "bg-amber-50 dark:bg-amber-900/10",
                    )}
                  >
                    {pa.direction === "above"
                      ? <ArrowUp className="h-3.5 w-3.5 text-green-600" />
                      : <ArrowDown className="h-3.5 w-3.5 text-red-600" />}
                    <span className="font-semibold tabular-nums">${pa.target_price.toFixed(2)}</span>
                    {pa.note && <span className="text-muted-foreground truncate">{pa.note}</span>}
                    {isTriggered && <span className="text-amber-700 dark:text-amber-400 text-sm">scattato</span>}
                    <span className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => update.mutate({ id: pa.id, body: { enabled: !pa.enabled } })}
                        title={pa.enabled ? "Disabilita" : "Abilita"}
                        className="p-1 hover:bg-muted rounded"
                      >
                        <Power className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => { setEditing(pa); setDialogOpen(true); }}
                        title="Modifica"
                        className="p-1 hover:bg-muted rounded"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => { if (confirm("Eliminare?")) remove.mutate(pa.id); }}
                        title="Elimina"
                        className="p-1 hover:bg-destructive/10 hover:text-destructive rounded"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>
      <PriceAlertDialog
        open={dialogOpen}
        editing={editing}
        onClose={() => setDialogOpen(false)}
        onSubmit={(body) => {
          if (editing) {
            update.mutate({ id: editing.id, body });
          } else {
            create.mutate(body);
          }
          setDialogOpen(false);
        }}
      />
    </>
  );
}
