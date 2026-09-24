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
  TableRow,
} from "@/components/ui/table";
import { formatMoney } from "@/lib/money";
import { barraDiversaDalSegnale, giornoDelSegnale, isAlertDelayed } from "@/lib/alertDates";
import { FORZA_TOOLTIP, PROBABILITA_TOOLTIP, snapshotForza, snapshotProbabilita } from "@/lib/alertMeta";
import { pianoDelSegnale, primoTarget } from "@/lib/tradePlaybook";
import { cn } from "@/lib/utils";

interface Props {
  alerts: Alert[];
}

/** «+8.4%» / «−3.1%», col segno tipografico: un trattino corto accanto a
 *  cifre tabulari si confonde con un separatore. */
function variazione(pct: number): string {
  const v = Math.abs(pct).toFixed(1);
  return `${pct > 0 ? "+" : pct < 0 ? "\u2212" : ""}${v}%`;
}

/**
 * Dashboard "FEED" — most recent alerts, newest first.
 *
 * Rebuilt as a real <Table> (was a flex <ul>) so its columns align
 * vertically and match the sibling "TOP STOCKS" table in the same panel:
 * Titolo · Natura · Regola · Forza · Prob. · Target · Δ% · Data. A flex list gives each
 * row its own widths, so the chips never lined up; a table shares one
 * width per column across all rows, which is exactly the alignment the
 * user asked for. Row click opens the detail dialog; the ticker is a Link
 * that navigates to the stock page (and stops row propagation).
 *
 * 2026-09-22 (richiesta dell'utente): al posto del prezzo di rilevazione, il
 * 1° TARGET del piano e quanto dista dall'ingresso. ⚠️ E' la stessa geometria
 * del dialogo di dettaglio e del magazzino `plan_outcomes` (`pianoDelSegnale`),
 * non un numero nuovo: un target calcolato qui in un altro modo sarebbe un
 * terzo piano, diverso da quello che poi viene misurato.
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
        {/* L'intestazione visibile e' stata tolta (richiesta dell'utente).
            ⚠️ Portava DUE spiegazioni — Forza e Probabilita' — e non sono state
            cancellate: sono risalite accanto al titolo «Feed» della colonna, in
            `AlertsCompactPanel`. Toglierle sarebbe stato togliere proprio la
            prosa che dice che la Probabilita' e' un tasso di base per
            rilevatore, cioe' la parte onesta del numero. */}
        <caption className="sr-only">Segnali più recenti</caption>
        <TableBody>
          {alerts.map((a) => {
            const delayed = isAlertDelayed(a);
            const snap = a.snapshot as Record<string, unknown> | undefined;
            const forza = snapshotForza(snap);
            const forzaTxt =
              forza == null
                ? ""
                : forza >= 70
                  ? "text-emerald-800 dark:text-emerald-400"
                  : forza >= 50
                    ? "text-amber-700 dark:text-amber-400"
                    : "text-rose-600 dark:text-rose-400";
            const prob = snapshotProbabilita(snap);
            const piano = pianoDelSegnale(a);
            const target = piano ? primoTarget(piano) : null;
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
                      <StockIdentity ticker={a.ticker} name={a.name} forma="riga" />
                    </Link>
                  ) : (
                    <span className="font-medium">—</span>
                  )}
                </TableCell>
                {/* Natura — continuazione/inversione chip (signals only;
                    renders nothing for non-signal alerts). */}
                <TableCell className="py-2">
                  <AlertNatureChip alert={a} size="sm" breve />
                </TableCell>
                {/* Regola — the shared AlertKindChip (same component the
                    alerts-page table uses): friendly label, no "signal:"
                    prefix, colored green/red by the snapshot bull/bear tone. */}
                <TableCell className="py-2">
                  <AlertKindChip alert={a} size="sm" breve />
                </TableCell>
                {/* Forza — pattern strength, colored by conviction; em dash when absent. */}
                <TableCell className="py-2 text-right">
                  {forza == null ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <span
                      className={cn("text-[0.7647rem] font-semibold tabular-nums", forzaTxt)}
                      title={`Forza ${forza}% — ${FORZA_TOOLTIP}`}
                    >
                      {forza}%
                    </span>
                  )}
                </TableCell>
                {/* Probabilità — historical hit-rate, neutral/info (slate); em
                    dash for legacy alerts lacking it. */}
                <TableCell className="py-2 text-right">
                  {prob == null ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    <span
                      className="text-[0.7647rem] font-semibold tabular-nums text-slate-700 dark:text-slate-300"
                      title={`Probabilità ${prob}% — ${PROBABILITA_TOOLTIP}`}
                    >
                      {prob}%
                    </span>
                  )}
                </TableCell>
                {/* Target — il 1° target del piano, e accanto quanto dista
                    dall'ingresso. «—» quando il piano non esiste: il detector
                    non ha emesso un livello di invalidazione, o non e' un
                    segnale. */}
                {target ? (
                  <>
                    <TableCell
                      className="py-2 text-right tabular-nums font-semibold"
                      title={`1° target del piano, dall'ingresso a ${formatMoney(target.ingresso, a.currency)}`}
                    >
                      {formatMoney(target.prezzo, a.currency)}
                    </TableCell>
                    <TableCell className="py-2 text-right">
                      <span
                        className={cn(
                          "whitespace-nowrap text-[0.7647rem] font-semibold tabular-nums",
                          target.variazionePct >= 0
                            ? "text-emerald-800 dark:text-emerald-400"
                            : "text-rose-600 dark:text-rose-400",
                        )}
                        title={`Il 1° target dista ${variazione(target.variazionePct)} dal prezzo d'ingresso`}
                      >
                        {variazione(target.variazionePct)}
                      </span>
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="py-2 text-right text-muted-foreground">—</TableCell>
                    <TableCell className="py-2 text-right text-muted-foreground">—</TableCell>
                  </>
                )}
                {/* Data — il giorno in cui il segnale e' COMPARSO, che e'
                    quello del prezzo d'ingresso mostrato qui accanto. La barra
                    di mercato, quando e' un altro giorno, resta nel titolo
                    insieme all'orologio. */}
                <TableCell className="py-2 text-right pr-4">
                  {(() => {
                    const barra = barraDiversaDalSegnale(a);
                    return (
                      <span
                        className="inline-flex items-center justify-end gap-1 text-[0.7647rem] text-muted-foreground tabular-nums whitespace-nowrap"
                        title={[
                          `Comparso il ${giornoDelSegnale(a)}`,
                          barra ? `barra di mercato ${barra}` : null,
                        ].filter(Boolean).join(" · ")}
                      >
                        {delayed && (
                          <Clock className="h-3 w-3 text-amber-700 dark:text-amber-400" />
                        )}
                        {new Date(`${giornoDelSegnale(a)}T00:00:00`).toLocaleDateString("it-IT", {
                          day: "2-digit",
                          month: "2-digit",
                        })}
                      </span>
                    );
                  })()}
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
