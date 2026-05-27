import { Clock } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Alert } from "@/api/types";
import { AlertKindChip, AlertNatureChip } from "@/components/AlertChips";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isDelayedDetection } from "@/lib/alertDates";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

/**
 * Dashboard "FEED" — most recent alerts, newest first.
 *
 * Rebuilt as a real <Table> (was a flex <ul>) so its columns align
 * vertically and match the sibling "TOP STOCKS" table in the same panel:
 * Titolo · Natura · Regola · Conf. · Prezzo · Data. A flex list gives each
 * row its own widths, so the chips never lined up; a table shares one
 * width per column across all rows, which is exactly the alignment the
 * user asked for. Row click opens the detail dialog; the ticker is a Link
 * that navigates to the stock page (and stops row propagation).
 */
export function RecentAlertsFeed({ alerts }: Props) {
  const [openDetail, setOpenDetail] = useState<Alert | null>(null);

  if (alerts.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-muted-foreground">
        Nessun segnale recente. Esegui uno scan da{" "}
        <span className="underline">/alerts</span> per generarli.
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Titolo</TableHead>
            <TableHead className="text-xs">Natura</TableHead>
            <TableHead className="text-xs">Regola</TableHead>
            <TableHead className="text-xs text-right">Conf.</TableHead>
            <TableHead className="text-xs text-right">Prezzo</TableHead>
            <TableHead className="text-xs text-right pr-4">Data</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {alerts.map((a) => {
            const delayed = isDelayedDetection(a.triggered_at, a.signal_date);
            const conf = (a.snapshot as Record<string, unknown> | undefined)?.confidence;
            const pct =
              typeof conf === "number"
                ? Math.max(0, Math.min(100, Math.round(conf)))
                : null;
            const confTxt =
              pct == null
                ? ""
                : pct >= 70
                  ? "text-emerald-600 dark:text-emerald-400"
                  : pct >= 50
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-rose-600 dark:text-rose-400";
            return (
              <TableRow
                key={a.id}
                className="cursor-pointer hover:bg-accent/30"
                onClick={() => setOpenDetail(a)}
              >
                {/* Titolo — identity; ticker links out and stops the row click.
                    max-w caps a very long name so it truncates instead of
                    blowing out the column width. */}
                <TableCell className="py-2">
                  {a.ticker ? (
                    <Link
                      to={`/stocks/${encodeURIComponent(a.ticker)}`}
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-2 min-w-0 max-w-[200px] hover:underline"
                    >
                      <StockIdentity ticker={a.ticker} name={a.name} />
                    </Link>
                  ) : (
                    <span className="font-medium">—</span>
                  )}
                </TableCell>
                {/* Natura — continuazione/inversione chip (signals only;
                    renders nothing for non-signal alerts). */}
                <TableCell className="py-2">
                  <AlertNatureChip alert={a} size="sm" />
                </TableCell>
                {/* Regola — the shared AlertKindChip (same component the
                    alerts-page table uses): friendly label, no "signal:"
                    prefix, colored green/red by the snapshot bull/bear tone. */}
                <TableCell className="py-2">
                  <AlertKindChip alert={a} size="sm" />
                </TableCell>
                {/* Confidenza — colored by conviction; em dash when absent. */}
                <TableCell className="py-2 text-right">
                  {pct == null ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <span
                      className={cn("text-xs font-semibold tabular-nums", confTxt)}
                      title={`Confidenza ${pct}%`}
                    >
                      {pct}%
                    </span>
                  )}
                </TableCell>
                {/* Prezzo */}
                <TableCell className="py-2 text-right tabular-nums font-semibold">
                  ${a.trigger_price}
                </TableCell>
                {/* Data — signal_date primary; orange clock flags a lagged
                    detection (>=1 day after the market bar). */}
                <TableCell className="py-2 text-right pr-4">
                  <span
                    className="inline-flex items-center justify-end gap-1 text-xs text-muted-foreground tabular-nums whitespace-nowrap"
                    title={
                      a.signal_date
                        ? `Segnale: ${a.signal_date} · Rilevato: ${new Date(a.triggered_at).toLocaleString("it-IT")}`
                        : new Date(a.triggered_at).toLocaleString("it-IT")
                    }
                  >
                    {delayed && (
                      <Clock className="h-3 w-3 text-amber-600 dark:text-amber-400" />
                    )}
                    {a.signal_date
                      ? new Date(a.signal_date).toLocaleDateString("it-IT", {
                          day: "2-digit",
                          month: "2-digit",
                        })
                      : new Date(a.triggered_at).toLocaleString("it-IT", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                  </span>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <AlertDetailDialog alert={openDetail} onClose={() => setOpenDetail(null)} />
    </>
  );
}
