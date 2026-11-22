import { ArrowLeftRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { OperazioneFondo, OperazioniTrimestre } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { Segmentato } from "@/components/ui/segmentato";
import { useOperazioniFondi } from "@/hooks/useInstitutionals";
import { useIsPhone } from "@/hooks/useMediaQuery";
import { fmtBig } from "@/lib/format";
import { AZIONE_LABEL } from "@/lib/smartMoney";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

import { StockLogo } from "./StockLogo";

/* ─── Le operazioni dei fondi nell'ultimo trimestre (2026-11-22) ──────────
 *
 * Ordinate dal server per VALORE dell'operazione in dollari. Ogni riga sta su
 * una riga: titolo, fondo (cede per primo), valore, e lo spostamento del peso
 * nel portafoglio del fondo, colorato per verso.
 *
 * Due forme: la scheda della home (un elenco solo, con l'azione scritta) e il
 * pannello della pagina dei fondi, a colonne per tipo di operazione. */

type Azione = "new" | "add" | "reduce" | "sold_out";
const COLONNE: { id: Azione; label: string; breve: string }[] = [
  { id: "new", label: "Nuove posizioni", breve: "Nuove" },
  { id: "add", label: "Aumenti", breve: "Aumenti" },
  { id: "reduce", label: "Riduzioni", breve: "Riduzioni" },
  { id: "sold_out", label: "Uscite", breve: "Uscite" },
];

const PESO = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function trimestreBreve(iso: string | null | undefined): string {
  if (!iso) return "";
  const [a, m] = iso.split("-").map(Number);
  return `T${Math.ceil(m / 3)} ${a}`;
}

/** L'azione in una pastiglia: piena per le mosse decisive (apre o chiude
 *  una posizione), tenue per gli aggiustamenti; il verso nel colore. */
const PASTIGLIA: Record<string, string> = {
  new: "bg-emerald-700 text-white dark:bg-emerald-500 dark:text-emerald-950",
  add: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  reduce: "bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300",
  sold_out: "bg-rose-700 text-white dark:bg-rose-500 dark:text-rose-950",
};

function Riga({ o, primo }: { o: OperazioneFondo; primo: boolean }) {
  const su = o.delta_pp >= 0;
  // Un 13F identifica a volte un titolo solo col CUSIP (gli ETF, in
  // produzione «CUSIP:46090E103»): il codice non dice niente a chi legge, il
  // nome della societa' si'.
  const soloCusip = o.ticker.startsWith("CUSIP:");
  const ticker = soloCusip ? (
    <span className="block max-w-[8rem] truncate font-semibold" title={o.ticker}>
      {o.company_name ?? o.ticker}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 font-semibold">
      <StockLogo ticker={o.ticker} size="xs" />
      {o.ticker}
    </span>
  );
  return (
    <li className={cn("flex h-7 items-center gap-2 text-sm", !primo && "border-t border-border/40")}>
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
      {/* Etichetta, variazione, valore: l'ordine chiesto il 2026-11-22. */}
      <span
        className={cn(
          "w-[4.5rem] shrink-0 rounded px-1 py-px text-center text-[0.6765rem] font-semibold",
          PASTIGLIA[o.action] ?? "bg-muted text-muted-foreground",
        )}
      >
        {AZIONE_LABEL[o.action] ?? o.action}
      </span>
      <span
        className={cn("w-12 shrink-0 text-right text-xs tabular-nums", su ? TESTO_SU : TESTO_GIU)}
        title={`Peso nel portafoglio del fondo: ${PESO.format(o.peso_prima)}% prima, ${PESO.format(o.peso_dopo)}% dopo`}
      >
        {su ? "+" : "−"}{PESO.format(Math.abs(o.delta_pp))}%
      </span>
      <span className="w-14 shrink-0 whitespace-nowrap text-right text-xs tabular-nums text-muted-foreground">
        {o.valore_operazione != null ? fmtBig(o.valore_operazione) : "—"}
      </span>
    </li>
  );
}

type Interrogazione = ReturnType<typeof useOperazioniFondi>;

/** Lo scheletro e' fatto delle stesse righe: alto quanto i dati, niente salto. */
function Righe({ q, n, vuoto }: { q: Interrogazione; n: number; vuoto: string }) {
  if (q.isLoading) {
    return (
      <ul aria-hidden>
        {Array.from({ length: n }).map((_, i) => (
          <li key={i} className={cn("flex h-7 items-center", i > 0 && "border-t border-border/40")}>
            <div className="h-4 w-full animate-pulse rounded bg-muted/40" />
          </li>
        ))}
      </ul>
    );
  }
  if (q.isError) {
    return <QueryError message="delle operazioni dei fondi" errore={q.error} onRetry={q.refetch} isRetrying={q.isFetching} />;
  }
  const righe = q.data?.operazioni ?? [];
  if (righe.length === 0) return <p className="py-2 text-sm text-muted-foreground">{vuoto}</p>;
  return (
    <ul>
      {righe.map((o, i) => (
        <Riga key={`${o.institutional_slug}-${o.ticker}-${o.action}`} o={o} primo={i === 0} />
      ))}
    </ul>
  );
}

const SPIEGAZIONE =
  "Ordinate per valore dell'operazione in dollari; la percentuale e' lo spostamento del peso nel portafoglio del fondo.";

function Riepilogo({ d }: { d?: OperazioniTrimestre }) {
  /* Sempre presente, anche vuoto: arrivando coi dati alzava l'intestazione
     di 5px e la pagina saltava (CLS nel gate). */
  return (
    <span className="text-xs text-muted-foreground">
      {d?.trimestre ? `${trimestreBreve(d.trimestre)} · ${d.fondi} fondi` : " "}
    </span>
  );
}

/** La scheda della home: un elenco solo, dalla piu' grande. */
export function OperazioniFondiCard({ limit = 12, className }: { limit?: number; className?: string }) {
  const q = useOperazioniFondi({ limit });
  return (
    <Card className={cn("flex h-full flex-col overflow-hidden", className)}>
      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        <div className="shrink-0 border-b bg-muted/30 px-3 py-2">
          <SectionTitle icon={ArrowLeftRight} label="Operazioni dei fondi" right={<Riepilogo d={q.data} />} />
        </div>
        <div className="relative min-h-0 flex-1 overflow-y-auto p-3 pr-2">
          <p className="sr-only">{SPIEGAZIONE}</p>
          <Righe q={q} n={limit} vuoto="Nessuna operazione nell'ultimo trimestre." />
        </div>
      </CardContent>
    </Card>
  );
}

function Colonna({ azione, label, limit }: { azione: Azione; label: string; limit: number }) {
  const q = useOperazioniFondi({ limit, azione });
  return (
    <section aria-label={label} className="min-w-0">
      {/* Un paragrafo, non un h3: sopra non c'e' un h2 (il titolo della
          scheda non e' un'intestazione) e axe lo segnalava come salto di
          livello. La colonna ha gia' il suo nome come regione. */}
      <p aria-hidden className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <Righe q={q} n={limit} vuoto="Nessuna nel trimestre." />
    </section>
  );
}

/** Il pannello della pagina dei fondi: una colonna per tipo di operazione,
 *  quattro sugli schermi larghi e due sui medi. Su telefono una alla volta,
 *  scelta con un selettore: quattro elenchi impilati sarebbero quattro
 *  schermate prima del resto della pagina. */
export function PannelloOperazioniFondi({ limit = 12 }: { limit?: number }) {
  const isPhone = useIsPhone();
  const [scelta, setScelta] = useState<Azione>("new");
  // La stessa chiave della colonna «Nuove»: una richiesta sola, dalla cache.
  const riepilogo = useOperazioniFondi({ limit, azione: "new" });
  const attiva = COLONNE.find((c) => c.id === scelta) ?? COLONNE[0];
  return (
    <Card>
      <CardContent className="space-y-2 p-3">
        <SectionTitle icon={ArrowLeftRight} label="Operazioni dei fondi" right={<Riepilogo d={riepilogo.data} />} />
        <p className="sr-only">{SPIEGAZIONE}</p>
        {isPhone ? (
          <>
            <Segmentato
              etichetta="Tipo di operazione"
              valore={scelta}
              onCambia={(id) => setScelta(id as Azione)}
              voci={COLONNE.map((c) => ({ id: c.id, label: c.breve }))}
            />
            <Colonna key={scelta} azione={attiva.id} label={attiva.label} limit={limit} />
          </>
        ) : (
          <div className="grid gap-x-6 gap-y-3 md:grid-cols-2 2xl:grid-cols-4 [&>*]:min-w-0">
            {COLONNE.map((c) => <Colonna key={c.id} azione={c.id} label={c.label} limit={limit} />)}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
