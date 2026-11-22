import { ArrowLeftRight } from "lucide-react";
import { Link } from "react-router-dom";

import type { OperazioneFondo } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useOperazioniFondi } from "@/hooks/useInstitutionals";
import { AZIONE_LABEL } from "@/lib/smartMoney";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

import { StockLogo } from "./StockLogo";

/* ─── Le operazioni dei fondi nell'ultimo trimestre (2026-11-22) ──────────
 *
 * Ordinate dal server per SPOSTAMENTO DI PESO nel portafoglio di chi le ha
 * fatte, in punti: dice quanto contava la mossa per il fondo, non quanto e'
 * grande il fondo. Ogni riga sta su una riga: titolo, fondo (cede per primo),
 * azione, peso prima → dopo, e lo spostamento colorato per verso. */

const PUNTI = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function trimestreBreve(iso: string | null): string {
  if (!iso) return "";
  const [a, m] = iso.split("-").map(Number);
  return `T${Math.ceil(m / 3)} ${a}`;
}

function Riga({ o, primo }: { o: OperazioneFondo; primo: boolean }) {
  const su = o.delta_pp >= 0;
  // Un 13F identifica a volte un titolo solo col CUSIP (gli ETF, in
  // produzione «CUSIP:46090E103»): il codice non dice niente a chi legge, il
  // nome della societa' si'.
  const soloCusip = o.ticker.startsWith("CUSIP:");
  const ticker = soloCusip ? (
    <span className="block max-w-[9rem] truncate font-semibold" title={o.ticker}>
      {o.company_name ?? o.ticker}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 font-semibold">
      <StockLogo ticker={o.ticker} size="xs" />
      {o.ticker}
    </span>
  );
  return (
    <li className={cn("flex items-center gap-2 py-1.5 text-sm", !primo && "border-t border-border/40")}>
      {o.stock_id != null ? (
        <Link to={`/stocks/${encodeURIComponent(o.ticker)}`} className="shrink-0 hover:underline">{ticker}</Link>
      ) : (
        <span className="shrink-0">{ticker}</span>
      )}
      <Link
        to={`/institutionals/${encodeURIComponent(o.institutional_slug)}`}
        className="min-w-0 flex-1 truncate text-xs text-muted-foreground hover:text-foreground hover:underline"
        title={o.institutional_name}
      >
        {o.institutional_name}
      </Link>
      <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
        {AZIONE_LABEL[o.action] ?? o.action}
        <span className="hidden sm:inline">
          {" · "}
          {PUNTI.format(o.peso_prima)}→{PUNTI.format(o.peso_dopo)}%
        </span>
      </span>
      <span
        className={cn("w-14 shrink-0 text-right text-xs font-semibold tabular-nums", su ? TESTO_SU : TESTO_GIU)}
        title={`Peso nel portafoglio del fondo: ${PUNTI.format(o.peso_prima)}% prima, ${PUNTI.format(o.peso_dopo)}% dopo`}
      >
        {su ? "+" : "−"}{PUNTI.format(Math.abs(o.delta_pp))} pt
      </span>
    </li>
  );
}

export function OperazioniFondiCard({ limit = 12, className }: { limit?: number; className?: string }) {
  const q = useOperazioniFondi({ limit });
  const d = q.data;
  return (
    <Card className={cn("flex h-full flex-col overflow-hidden", className)}>
      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        <div className="shrink-0 border-b bg-muted/30 px-3 py-2">
          <SectionTitle
            icon={ArrowLeftRight}
            label="Operazioni dei fondi"
            /* Sempre presente, anche vuoto: arrivando coi dati alzava
               l'intestazione di 5px e la pagina saltava (CLS nel gate). */
            right={
              <span className="text-xs text-muted-foreground">
                {d?.trimestre ? `${trimestreBreve(d.trimestre)} · ${d.fondi} fondi` : " "}
              </span>
            }
          />
        </div>
        <div className="flex min-h-0 flex-1 flex-col p-3">
          {q.isLoading ? (
            /* Le stesse righe dei dati, una per operazione attesa: il
               caricamento ha l'altezza del contenuto e la pagina non salta. */
            <ul aria-hidden className="flex-1">
              {Array.from({ length: limit }).map((_, i) => (
                <li key={i} className={cn("py-1.5", i > 0 && "border-t border-border/40")}>
                  <div className="h-5 animate-pulse rounded bg-muted/40" />
                </li>
              ))}
            </ul>
          ) : q.isError ? (
            <QueryError message="delle operazioni dei fondi" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />
          ) : d && d.operazioni.length > 0 ? (
            <div className="relative min-h-0 flex-1 overflow-y-auto pr-1">
              <p className="sr-only">
                Ordinate per spostamento del peso nel portafoglio del fondo, in punti percentuali.
              </p>
              <ul>
                {d.operazioni.map((o, i) => (
                  <Riga key={`${o.institutional_slug}-${o.ticker}-${o.action}`} o={o} primo={i === 0} />
                ))}
              </ul>
            </div>
          ) : (
            <div className="grid flex-1 place-items-center text-sm text-muted-foreground">
              Nessuna operazione nell'ultimo trimestre.
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
