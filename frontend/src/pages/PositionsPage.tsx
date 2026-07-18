import { Archive, Briefcase, Loader2, Trash2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";

import type { Position } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { PortfolioSummary } from "@/components/PortfolioSummary";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDeletePosition,
  usePositions,
  useUpdatePosition,
} from "@/hooks/usePositions";
import { cn } from "@/lib/utils";

/* Tone maps as plain string literals — Tailwind's purger only sees literals
   (see CLAUDE.md), don't refactor to template composition. */
const SIDE_CHIP: Record<Position["side"], string> = {
  long: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  short: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};
const SIDE_LABEL: Record<Position["side"], string> = {
  long: "Long",
  short: "Short",
};
const EXIT_CHIP: Record<string, string> = {
  stop: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
  target: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  manual: "bg-muted text-muted-foreground",
};
const EXIT_LABEL: Record<string, string> = {
  stop: "Stop",
  target: "Target",
  manual: "Manuale",
};

function fmtPrice(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `$${n >= 1 ? n.toFixed(2) : n.toFixed(3)}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function PnlCell({ pct, abs }: { pct: number | null; abs: number | null }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const positive = pct >= 0;
  return (
    <span
      className={cn(
        "font-bold tabular-nums",
        positive
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-rose-600 dark:text-rose-400",
      )}
    >
      {fmtPct(pct)}
      {abs != null && (
        <span className="ml-1 text-xs font-medium opacity-80">
          ({abs >= 0 ? "+" : ""}
          {abs.toFixed(2)}$)
        </span>
      )}
    </span>
  );
}

function TickerCell({ p }: { p: Position }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <StockLogo ticker={p.ticker} size="xs" />
      <div className="min-w-0">
        <Link
          to={`/stocks/${encodeURIComponent(p.ticker)}`}
          className="font-semibold hover:underline underline-offset-2"
        >
          {p.ticker}
        </Link>
        {p.name && (
          <div className="text-xs text-muted-foreground truncate max-w-[16ch]">
            {p.name}
          </div>
        )}
      </div>
    </div>
  );
}

function SideChip({ side }: { side: Position["side"] }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
        SIDE_CHIP[side],
      )}
    >
      {SIDE_LABEL[side]}
    </span>
  );
}

export default function PositionsPage() {
  const q = usePositions();
  const update = useUpdatePosition();
  const remove = useDeletePosition();

  const all = q.data ?? [];
  const open = all.filter((p) => p.closed_at == null);
  const closed = all.filter((p) => p.closed_at != null);

  const onClose = (p: Position) => {
    if (
      confirm(
        `Chiudere la posizione ${SIDE_LABEL[p.side]} su ${p.ticker} al prezzo corrente?`,
      )
    ) {
      update.mutate({ id: p.id, body: { close: true } });
    }
  };
  const onDelete = (p: Position) => {
    if (confirm(`Eliminare definitivamente la posizione su ${p.ticker}?`)) {
      remove.mutate(p.id);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 flex items-center gap-4">
          <div>
            <h2 className="text-2xl font-bold">Posizioni</h2>
            <p className="text-sm text-muted-foreground">
              Trade tracciati dal piano operativo dei segnali — {open.length}{" "}
              apert{open.length === 1 ? "a" : "e"} · {closed.length} chius
              {closed.length === 1 ? "a" : "e"}. Stop e target vengono
              controllati in automatico (sweep live + scan EOD).
            </p>
          </div>
        </CardContent>
      </Card>

      {q.isLoading && (
        <div className="flex min-h-[20vh] items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}
      {q.isError && (
        <Card>
          <CardContent className="p-4 text-sm text-rose-600 dark:text-rose-400">
            Errore nel caricamento delle posizioni.
          </CardContent>
        </Card>
      )}

      {!q.isLoading && !q.isError && (
        <>
          <PortfolioSummary open={open} closed={closed} />
          {/* Posizioni aperte — P&L live (poll 15s, quote condivise 10s) */}
          <Card>
            <CardContent className="p-4">
              <SectionTitle icon={Briefcase} label="Posizioni aperte" className="mb-3" />
              {open.length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-6">
                  Nessuna posizione aperta. Apri il dettaglio di un segnale e
                  usa “Traccia trade” nel piano operativo.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Titolo</TableHead>
                        <TableHead>Lato</TableHead>
                        <TableHead className="text-right">Entry</TableHead>
                        <TableHead className="text-right">Stop</TableHead>
                        <TableHead className="text-right">Target</TableHead>
                        <TableHead className="text-right">Prezzo</TableHead>
                        <TableHead className="text-right">P&amp;L</TableHead>
                        <TableHead className="text-right">Aperta il</TableHead>
                        <TableHead className="text-right" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {open.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>
                            <TickerCell p={p} />
                          </TableCell>
                          <TableCell>
                            <SideChip side={p.side} />
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtPrice(p.entry_price)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-rose-600 dark:text-rose-400">
                            {fmtPrice(p.stop_price)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                            {fmtPrice(p.target_price)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtPrice(p.last_price)}
                            {p.price_source === "live" && (
                              <span
                                className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse align-middle"
                                title="Quotazione live"
                              />
                            )}
                            {p.price_source === "eod" && (
                              <span
                                className="ml-1 text-[10px] uppercase text-muted-foreground"
                                title="Ultima chiusura giornaliera"
                              >
                                eod
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <PnlCell pct={p.unrealized_pct} abs={p.unrealized_abs} />
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {fmtDate(p.opened_at)}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => onClose(p)}
                              disabled={update.isPending}
                              title="Chiudi manualmente al prezzo corrente"
                            >
                              <XCircle className="h-3.5 w-3.5 mr-1" />
                              Chiudi
                            </Button>
                            <button
                              onClick={() => onDelete(p)}
                              title="Elimina"
                              className="ml-1 p-1.5 hover:bg-destructive/10 hover:text-destructive rounded align-middle"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Posizioni chiuse — esito + P&L realizzato */}
          <Card>
            <CardContent className="p-4">
              <SectionTitle icon={Archive} label="Posizioni chiuse" className="mb-3" />
              {closed.length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-6">
                  Nessuna posizione chiusa.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Titolo</TableHead>
                        <TableHead>Lato</TableHead>
                        <TableHead className="text-right">Entry</TableHead>
                        <TableHead className="text-right">Exit</TableHead>
                        <TableHead>Esito</TableHead>
                        <TableHead className="text-right">P&amp;L realizzato</TableHead>
                        <TableHead className="text-right">Chiusa il</TableHead>
                        <TableHead className="text-right" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {closed.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>
                            <TickerCell p={p} />
                          </TableCell>
                          <TableCell>
                            <SideChip side={p.side} />
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtPrice(p.entry_price)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {fmtPrice(p.exit_price)}
                          </TableCell>
                          <TableCell>
                            <span
                              className={cn(
                                "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
                                EXIT_CHIP[p.exit_reason ?? "manual"] ?? EXIT_CHIP.manual,
                              )}
                            >
                              {EXIT_LABEL[p.exit_reason ?? "manual"] ?? p.exit_reason}
                            </span>
                          </TableCell>
                          <TableCell className="text-right">
                            <PnlCell pct={p.realized_pct} abs={p.realized_abs} />
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-muted-foreground">
                            {fmtDate(p.closed_at)}
                          </TableCell>
                          <TableCell className="text-right">
                            <button
                              onClick={() => onDelete(p)}
                              title="Elimina"
                              className="p-1.5 hover:bg-destructive/10 hover:text-destructive rounded"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
