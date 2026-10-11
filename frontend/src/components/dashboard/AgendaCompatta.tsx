import { Briefcase, CalendarClock, Moon, Star, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { EarningsEvent } from "@/api/types";
import { type GiornoAgenda, ripartisciRighe, taglia, vociDelGiorno } from "@/lib/agendaGiorni";
import { earningsBeatTone, formatEps } from "@/lib/calendarMeta";
import { etichettaGiorno } from "@/lib/settimana";
import { cn } from "@/lib/utils";

/* ─── L'agenda nel jumbotron: quattro giorni lavorativi in due righe ───────
 *
 * Oggi (o il primo giorno lavorativo) e i tre successivi, due per riga, coi
 * rilasci macro e le trimestrali di ciascun giorno (2026-10-12, su richiesta:
 * prima era una colonna che scorreva).
 *
 * ⚠️ ALTEZZA FISSA e NESSUNO scorrimento. Il calendario arriva dopo il resto
 * della fascia, e un riquadro che cresce sposterebbe tutto cio' che sta sotto
 * (FA-106). Le due righe si dividono l'altezza in proporzione alle voci del
 * giorno piu' pieno di ciascuna (`ripartisciRighe`), e un giorno che non ci
 * sta dice quante ne restano fuori con «+N altre». Ogni voce e' alta una
 * linea esatta (`h-4`): e' quello che rende l'aritmetica vera a schermo.
 */

/** Righe (linee di voci + intestazione) piu' lo spazio fra le due: deve
 *  restare in pari con `LINEE_AGENDA` e con `h-4` delle voci. */
const ALTEZZA = "h-[13.75rem]";

function Voce({ ora, testo, forte }: { ora: string | null; testo: string; forte: boolean }) {
  return (
    <li className="flex h-4 min-w-0 items-baseline gap-1.5 leading-4">
      <span className="w-9 shrink-0 font-semibold tabular-nums">
        {ora ?? <span className="font-normal text-muted-foreground">n/d</span>}
      </span>
      <span className={cn("truncate", forte ? "font-semibold text-foreground" : "text-muted-foreground")} title={testo}>
        {testo}
      </span>
    </li>
  );
}

/** Una trimestrale nello stile del calendario: stima prima dell'uscita,
 *  EPS reale contro stima dopo, colorato e con la freccia della sorpresa. */
function VoceTrimestrale({ e, segno }: { e: EarningsEvent; segno?: ReactNode }) {
  const uscita = earningsBeatTone(e.surprise_pct) != null;
  const battuta = uscita && (e.surprise_pct ?? 0) >= 0;
  const colore = !uscita
    ? "text-foreground"
    : battuta
      ? "text-emerald-800 dark:text-emerald-300"
      : "text-rose-700 dark:text-rose-300";
  return (
    <li className="flex h-4 min-w-0 items-center gap-1 leading-4 tabular-nums">
      {segno}
      <Link to={`/stocks/${encodeURIComponent(e.ticker)}`} className={cn("shrink-0 font-semibold hover:underline", colore)}>
        {e.ticker}
      </Link>
      {e.earnings_when === "pre" && <Sun className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="prima dell'apertura" />}
      {e.earnings_when === "after" && <Moon className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="dopo la chiusura" />}
      {uscita ? (
        <span className="ml-auto flex min-w-0 items-baseline gap-1">
          <span className={cn("font-semibold", colore)}>{formatEps(e.eps_reported)}</span>
          <span className="truncate text-muted-foreground">vs {formatEps(e.eps_estimate)}</span>
          <span className={cn("shrink-0 font-bold", colore)} title={battuta ? "Ha battuto le stime" : "Sotto le stime"}>
            {battuta ? "▲" : "▼"} {(e.surprise_pct ?? 0) >= 0 ? "+" : ""}{(e.surprise_pct ?? 0).toFixed(1)}%
          </span>
        </span>
      ) : (
        <span className="ml-auto truncate text-muted-foreground">
          stim. <span className="font-semibold text-foreground/80">{formatEps(e.eps_estimate)}</span>
        </span>
      )}
    </li>
  );
}

function Giorno({ g, linee }: { g: GiornoAgenda; linee: number }) {
  const voci = vociDelGiorno(g);
  const { mostrate, altre } = taglia(voci, linee);
  const macro = g.macro.slice(0, mostrate);
  const trimestrali = g.trimestrali.slice(0, Math.max(0, mostrate - macro.length));
  const n = g.trimestrali.length;
  return (
    <div className="flex min-w-0 flex-col">
      {/* Un `div` e non un'intestazione: il jumbotron sta sopra l'`h2` della
          pagina, e un `h3` qui salterebbe un livello (axe `heading-order`). */}
      <div className="mb-0.5 flex h-4 min-w-0 items-baseline justify-between gap-2 leading-4">
        <span className={cn("truncate text-[0.6765rem] font-bold uppercase tracking-wide",
          g.distanza === 0 ? "text-foreground" : "text-muted-foreground")}>
          {etichettaGiorno(g.giorno, g.distanza)}
        </span>
        {n > 0 && (
          <span className="shrink-0 text-[0.6471rem] text-muted-foreground">
            {n} {n === 1 ? "trimestrale" : "trimestrali"}
          </span>
        )}
      </div>
      {voci === 0 ? (
        <p className="h-4 leading-4 text-muted-foreground">
          {g.distanza === 0 ? "Niente in calendario oggi." : "Niente in calendario."}
        </p>
      ) : (
        <ul className="min-w-0">
          {macro.map((m) => (
            <Voce key={`${m.etichetta}-${m.oraET}`} ora={m.oraET} testo={m.etichetta}
              forte={m.importanza === "high"} />
          ))}
          {trimestrali.map(({ evento, rilevanza }) => (
            <VoceTrimestrale
              key={evento.ticker}
              e={evento}
              segno={rilevanza === "posizione" ? (
                <Briefcase className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="in posizione" />
              ) : rilevanza === "preferito" ? (
                <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-label="preferito" />
              ) : undefined}
            />
          ))}
          {altre > 0 && (
            <li className="h-4 leading-4">
              <Link to="/calendar" className="text-muted-foreground underline underline-offset-2 hover:text-foreground">
                +{altre} {altre === 1 ? "altra" : "altre"}
              </Link>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export function AgendaCompatta({ giorni, stato }: {
  /** Quattro giorni lavorativi da oggi (`giorniAgenda`). */
  giorni: GiornoAgenda[];
  stato: "pronto" | "carica" | "errore";
}) {
  const righe = [giorni.slice(0, 2), giorni.slice(2, 4)];
  const bisogni = righe.map((r) => Math.max(0, ...r.map(vociDelGiorno))) as [number, number];
  const linee = ripartisciRighe(bisogni);
  return (
    <section aria-label="Agenda" className="flex min-w-0 flex-col text-xs">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground/70">
          <CalendarClock className="h-3.5 w-3.5" aria-hidden />
          Agenda
        </span>
        <Link
          to="/calendar"
          className="text-[0.6765rem] text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          calendario
        </Link>
      </div>
      <div className={cn(ALTEZZA, "flex flex-col gap-1.5 overflow-hidden rounded-md border border-border/60 bg-muted/20 px-2 py-1.5")}>
        {stato === "carica" ? (
          <div className="h-full animate-pulse rounded bg-muted/40" aria-hidden />
        ) : stato === "errore" ? (
          <p className="text-muted-foreground">Calendario non disponibile.</p>
        ) : (
          righe.map((r, i) => (
            <div
              key={i}
              className={cn("grid min-h-0 grid-cols-2 gap-x-3", i === 1 && "border-t border-border/50 pt-1")}
              // Intestazione (1rem + margine) piu' le linee assegnate alla riga.
              style={{ height: `${linee[i] + 1.125 + (i === 1 ? 0.25 : 0)}rem` }}
            >
              {r.map((g) => <Giorno key={g.giorno} g={g} linee={linee[i]} />)}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
