import { Briefcase, CalendarClock, Moon, Star, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { EarningsEvent } from "@/api/types";
import { earningsBeatTone, formatEps } from "@/lib/calendarMeta";
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

/** Una trimestrale nello stile del calendario: stima prima dell'uscita,
 *  EPS reale contro stima dopo, colorato e con la freccia della sorpresa.
 *  ⚠️ Una voce per titolo invece della riga «12 trimestrali prima
 *  dell'apertura (AAPL, MSFT…)»: nelle settimane piene quella riga usciva
 *  dal riquadro sul telefono e i nomi oltre il quarto non si vedevano. */
function VoceTrimestrale({ e, segno }: { e: EarningsEvent; segno?: ReactNode }) {
  const uscita = earningsBeatTone(e.surprise_pct) != null;
  const battuta = uscita && (e.surprise_pct ?? 0) >= 0;
  const colore = !uscita
    ? "text-foreground"
    : battuta
      ? "text-emerald-800 dark:text-emerald-300"
      : "text-rose-700 dark:text-rose-300";
  return (
    <li className="flex min-w-0 items-center gap-1 tabular-nums">
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

/** Una o due colonne: una sul telefono, dove due voci affiancate non ci
 *  stanno, due appena c'e' spazio. Letterale per il purger di Tailwind. */
const GRIGLIA_TRIMESTRALI = "grid grid-cols-1 gap-x-3 gap-y-0.5 min-[420px]:grid-cols-2";

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
  // Prima della seduta, dopo, poi senza orario: l'ordine in cui escono.
  const trimestraliOggi = [...oggi.primaDellApertura, ...oggi.dopoLaChiusura, ...oggi.senzaOrario];
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
                <>
                  <ul className="space-y-0.5">
                    {oggi.macro.slice(0, 5).map((m) => (
                      <Voce
                        key={`${m.etichetta}-${m.oraET}`}
                        ora={m.oraET}
                        testo={m.etichetta}
                        forte={m.importanza === "high"}
                      />
                    ))}
                  </ul>
                  {trimestraliOggi.length > 0 && (
                    <div className="mt-1">
                      <div className="text-[0.6471rem] text-muted-foreground">
                        {trimestraliOggi.length} {trimestraliOggi.length === 1 ? "trimestrale" : "trimestrali"}
                      </div>
                      <ul className={GRIGLIA_TRIMESTRALI}>
                        {trimestraliOggi.map((e) => <VoceTrimestrale key={e.ticker} e={e} />)}
                      </ul>
                    </div>
                  )}
                </>
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
                </ul>
                {g.trimestrali.length > 0 && (
                  <ul className={GRIGLIA_TRIMESTRALI}>
                    {g.trimestrali.map(({ evento, rilevanza }) => (
                      <VoceTrimestrale
                        key={evento.ticker}
                        e={evento}
                        segno={rilevanza === "posizione" ? (
                          <Briefcase className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="in posizione" />
                        ) : (
                          <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-label="preferito" />
                        )}
                      />
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
