import { Briefcase, CalendarRange, Moon, Star, Sun } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useCalendar } from "@/hooks/useCalendar";
import { useNowTick } from "@/hooks/useNowTick";
import { useTitoliSeguiti } from "@/hooks/useTitoliSeguiti";
import { etichettaGiorno, settimana } from "@/lib/settimana";
import { etToday } from "@/lib/usSession";
import { cn } from "@/lib/utils";

/* ─── Questa settimana (FA-088) ────────────────────────────────────────────
 *
 * Una colonna per giorno, di ALTEZZA FISSA, con lo scorrimento dentro la
 * colonna: il numero di eventi si sa solo a dati arrivati, e una scheda che
 * cresce spingerebbe giu' i segnali sotto (FA-106). Sul telefono le colonne
 * scorrono di lato, come la striscia dei preferiti.
 */

const ALTEZZA_COLONNA = "h-36";

export function SettimanaCard() {
  const adesso = useNowTick(60_000);
  const oggi = etToday(new Date(adesso));
  const a = useMemo(() => {
    const t = new Date(`${oggi}T12:00:00Z`);
    t.setUTCDate(t.getUTCDate() + 6);
    return t.toISOString().slice(0, 10);
  }, [oggi]);

  const calendarioQ = useCalendar({ from: oggi, to: a, kinds: ["macro", "earnings"] });
  const { titoli } = useTitoliSeguiti();

  const giorni = useMemo(
    () => settimana(calendarioQ.data?.events, oggi, titoli),
    [calendarioQ.data, oggi, titoli],
  );

  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={CalendarRange}
          label="Questa settimana"
          className="mb-2"
          right={
            <span className="text-[0.6471rem] uppercase tracking-wider text-muted-foreground">
              macro importanti · trimestrali dei tuoi titoli
            </span>
          }
        />
        {calendarioQ.isError ? (
          <p className={cn(ALTEZZA_COLONNA, "text-xs text-muted-foreground")}>
            Calendario non disponibile.
          </p>
        ) : (
          <div className="flex gap-2 overflow-x-auto">
            {calendarioQ.isLoading
              ? Array.from({ length: 5 }, (_, i) => (
                  <div key={i} className={cn(ALTEZZA_COLONNA, "min-w-[9.5rem] flex-1 animate-pulse rounded-md bg-muted/50")} aria-hidden />
                ))
              : giorni.map((g) => (
                  <section
                    key={g.giorno}
                    aria-label={etichettaGiorno(g.giorno, g.distanza)}
                    className={cn(ALTEZZA_COLONNA, "flex min-w-[9.5rem] flex-1 flex-col rounded-md border border-border/60 bg-muted/20 p-2")}
                  >
                    {/* Un `div` e non un'intestazione: la scheda sta sopra
                        l'`h2` della pagina, e un `h3` qui salterebbe un livello
                        (axe `heading-order`, trovato dal gate). Il nome della
                        colonna lo porta gia' `aria-label`. */}
                    <div className="mb-1 flex items-baseline justify-between gap-1 text-xs font-semibold">
                      <span>{etichettaGiorno(g.giorno, g.distanza)}</span>
                      {g.distanza > 1 && (
                        <span className="font-normal text-muted-foreground">tra {g.distanza} gg</span>
                      )}
                    </div>
                    <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto text-[0.7059rem] leading-snug">
                      {g.macro.map((m) => (
                        <li key={`${m.etichetta}-${m.oraET}`} className="flex gap-1">
                          <span className="shrink-0 font-semibold tabular-nums">{m.oraET ?? "—"}</span>
                          <span className="break-words">
                            {m.etichetta}
                            <span className="text-muted-foreground"> · {m.regione}</span>
                          </span>
                        </li>
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
                      {g.macro.length === 0 && g.trimestrali.length === 0 && (
                        <li className="text-muted-foreground">niente in arrivo</li>
                      )}
                    </ul>
                  </section>
                ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
