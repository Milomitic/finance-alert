import { Briefcase, CalendarClock, Moon, Star, Sun } from "lucide-react";
import { Link } from "react-router-dom";

import type { AgendaOggi } from "@/lib/oggiMercato";
import { etichettaGiorno, type GiornoSettimana } from "@/lib/settimana";
import { cn } from "@/lib/utils";

/* ─── L'agenda nel jumbotron: oggi e i giorni che vengono ──────────────────
 *
 * Prima erano due cose separate: una riga «Oggi» in fondo al jumbotron e la
 * scheda «Questa settimana» sotto di lui, con una colonna per giorno. Qui stanno
 * insieme e piccole, accanto a indici e materie prime: OGGI per intero (tutti i
 * rilasci macro con l'ora di New York e le trimestrali prima e dopo la seduta),
 * i giorni dopo solo cio' che conta — macro importanti e trimestrali dei tuoi
 * titoli.
 *
 * ⚠️ ALTEZZA FISSA, con lo scorrimento dentro (FA-106): il calendario arriva
 * dopo il resto della fascia, e un riquadro che cresce sposterebbe tutto quello
 * che sta sotto. Il riquadro c'e' anche vuoto, e lo dice.
 */

const ALTEZZA = "h-[9.5rem]";

function Voce({ ora, testo, forte }: { ora: string | null; testo: string; forte: boolean }) {
  return (
    <li className="flex min-w-0 items-baseline gap-1.5">
      <span className="w-10 shrink-0 font-semibold tabular-nums">
        {ora ?? <span className="font-normal text-muted-foreground" title="Orario di rilascio non pubblicato">n/d</span>}
      </span>
      <span className={cn("truncate", forte ? "font-semibold text-foreground" : "text-muted-foreground")} title={testo}>
        {testo}
      </span>
    </li>
  );
}

function Trimestrali({ quante, quando, tickers }: { quante: number; quando: string; tickers: string[] }) {
  if (quante === 0) return null;
  return (
    <li className="min-w-0 truncate text-muted-foreground">
      <span className="font-semibold text-foreground">{quante}</span> {quando}
      {tickers.length > 0 && (
        <span className="ml-1">
          ({tickers.slice(0, 4).join(", ")}
          {tickers.length > 4 ? "…" : ""})
        </span>
      )}
    </li>
  );
}

export function AgendaCompatta({ oggi, prossimi, stato }: {
  /** Il giorno di New York per intero. */
  oggi: AgendaOggi;
  /** I giorni dopo oggi, gia' ridotti a macro importanti e tuoi titoli. */
  prossimi: GiornoSettimana[];
  stato: "pronto" | "carica" | "errore";
}) {
  const pieni = prossimi.filter((g) => g.distanza > 0 && (g.macro.length > 0 || g.trimestrali.length > 0));
  const nienteOggi =
    oggi.macro.length === 0 &&
    oggi.primaDellApertura.length === 0 &&
    oggi.dopoLaChiusura.length === 0 &&
    oggi.senzaOrario.length === 0;
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
      <div className={cn(ALTEZZA, "min-h-0 overflow-y-auto rounded-md border border-border/60 bg-muted/20 px-2 py-1.5")}>
        {stato === "carica" ? (
          <div className="h-full animate-pulse rounded bg-muted/40" aria-hidden />
        ) : stato === "errore" ? (
          <p className="text-muted-foreground">Calendario non disponibile.</p>
        ) : (
          <div className="space-y-1.5">
            {/* Un `div` e non un'intestazione: il jumbotron sta sopra l'`h2`
                della pagina, e un `h3` qui salterebbe un livello (axe
                `heading-order`, la stessa ragione della scheda di prima). */}
            <div>
              <div className="text-[0.6765rem] font-bold uppercase tracking-wide">Oggi</div>
              {nienteOggi ? (
                <p className="text-muted-foreground">Niente in calendario oggi.</p>
              ) : (
                <ul className="space-y-0.5">
                  {oggi.macro.slice(0, 5).map((m) => (
                    <Voce
                      key={`${m.etichetta}-${m.oraET}`}
                      ora={m.oraET}
                      testo={m.etichetta}
                      forte={m.importanza === "high"}
                    />
                  ))}
                  <Trimestrali quante={oggi.primaDellApertura.length} quando="trimestrali prima dell'apertura"
                    tickers={oggi.primaDellApertura.map((e) => e.ticker)} />
                  <Trimestrali quante={oggi.dopoLaChiusura.length} quando="dopo la chiusura"
                    tickers={oggi.dopoLaChiusura.map((e) => e.ticker)} />
                </ul>
              )}
            </div>
            {pieni.map((g) => (
              <div key={g.giorno}>
                <div className="text-[0.6765rem] font-bold uppercase tracking-wide text-muted-foreground">
                  {etichettaGiorno(g.giorno, g.distanza)}
                </div>
                <ul className="space-y-0.5">
                  {g.macro.map((m) => (
                    <Voce key={`${m.etichetta}-${m.oraET}`} ora={m.oraET} testo={m.etichetta} forte />
                  ))}
                  {g.trimestrali.map(({ evento, rilevanza }) => (
                    <li key={evento.ticker} className="flex items-center gap-1">
                      {rilevanza === "posizione" ? (
                        <Briefcase className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="in posizione" />
                      ) : (
                        <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-label="preferito" />
                      )}
                      <Link to={`/stocks/${encodeURIComponent(evento.ticker)}`} className="font-semibold hover:underline">
                        {evento.ticker}
                      </Link>
                      <span className="text-muted-foreground">trimestrale</span>
                      {evento.earnings_when === "pre" && <Sun className="h-3 w-3 text-muted-foreground" aria-label="prima dell'apertura" />}
                      {evento.earnings_when === "after" && <Moon className="h-3 w-3 text-muted-foreground" aria-label="dopo la chiusura" />}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
