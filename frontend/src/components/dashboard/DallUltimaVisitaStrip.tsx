import { useQuery } from "@tanstack/react-query";
import { Briefcase, History, Star } from "lucide-react";
import { Link } from "react-router-dom";

import { registraVisita, type NovitaTitolo } from "@/api/cruscotto";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { contati, etichettaDal } from "@/lib/dallUltimaVisita";

/* ─── «Dall'ultima visita», in cima al cruscotto (2026-09-29) ─────────────
 *
 * Il cruscotto si apre ~17 volte al giorno e mostrava lo STATO, che per chi
 * l'ha visto un'ora prima e' quasi tutto gia' noto. Questa riga dice la
 * DIFFERENZA. Che cosa sia «l'ultima visita» lo decide il server
 * (`ultima_visita_service`): l'apertura precedente a una pausa di mezz'ora,
 * cosi' una ricarica non azzera la riga.
 *
 * ⚠️ Altezza fissa, come la striscia dei preferiti qui sotto: la risposta
 * arriva dopo la pagina, e una riga che nasce a dati arrivati spingerebbe giu'
 * tutto il resto (FA-106). Una riga sola che scorre di lato.
 */

const PASTIGLIA =
  "inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border " +
  "border-border/60 bg-card px-2 text-xs transition-colors hover:bg-muted";

function Segno({ rilevanza }: { rilevanza: NovitaTitolo["rilevanza"] }) {
  return rilevanza === "posizione" ? (
    <Briefcase className="h-3 w-3 shrink-0 text-muted-foreground" aria-label="in posizione" />
  ) : (
    <Star className="h-3 w-3 shrink-0 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" aria-label="preferito" />
  );
}

function Novita({ novita }: { novita: NovitaTitolo[] }) {
  return (
    <Popover>
      <PopoverTrigger className={PASTIGLIA}>
        {contati(novita.length, "novità", "novità")} sui tuoi titoli
      </PopoverTrigger>
      <PopoverContent align="start" collisionPadding={16} className="w-80 max-w-[calc(100vw-2rem)] p-2">
        <ul className="space-y-1.5 text-xs">
          {novita.map((n) => (
            <li key={`${n.ticker}-${n.tipo}-${n.data}-${n.testo}`} className="flex gap-1.5">
              <Segno rilevanza={n.rilevanza} />
              <span className="min-w-0">
                <Link to={`/stocks/${encodeURIComponent(n.ticker)}`} className="font-semibold hover:underline">
                  {n.ticker}
                </Link>{" "}
                <span className="text-muted-foreground tabular-nums">
                  {n.data.slice(8, 10)}/{n.data.slice(5, 7)}
                </span>{" "}
                {n.testo}
              </span>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export function DallUltimaVisitaStrip() {
  const q = useQuery({
    queryKey: ["dall-ultima-visita"],
    queryFn: ({ signal }) => registraVisita(signal),
    // Tornando sulla scheda dopo una pausa la risposta cambia, ed e' giusto:
    // e' una visita nuova. Una ricarica ravvicinata rende la stessa riga.
    staleTime: 60_000,
  });
  const d = q.data;
  const niente =
    d && d.segnali === 0 && d.novita.length === 0 && d.target_raggiunti === 0 && d.posizioni_chiuse === 0;

  return (
    <section aria-label="Dall'ultima visita" className="flex h-9 items-center gap-2 overflow-x-auto px-1">
      <span className="inline-flex shrink-0 items-center gap-1 text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
        <History className="h-3.5 w-3.5" aria-hidden />
        {d?.dal ? etichettaDal(d.dal) : "Dall'ultima visita"}
      </span>
      {q.isLoading ? (
        <span className="h-7 w-48 shrink-0 animate-pulse rounded-md bg-muted/60" aria-hidden />
      ) : q.isError || !d ? (
        <span className="shrink-0 text-xs text-muted-foreground">non disponibile</span>
      ) : d.dal === null ? (
        <span className="shrink-0 text-xs text-muted-foreground">
          prima visita: dalla prossima, qui trovi cosa è cambiato
        </span>
      ) : niente ? (
        <span className="shrink-0 text-xs text-muted-foreground">niente di nuovo</span>
      ) : (
        <>
          {d.segnali > 0 && (
            <Link to="/alerts" className={PASTIGLIA}>
              {contati(d.segnali, "segnale nuovo", "segnali nuovi")}
            </Link>
          )}
          {d.segnali_miei > 0 && (
            <Link to="/alerts?solo_rilevanti=true" className={PASTIGLIA}>
              {d.segnali_miei} sui tuoi titoli
            </Link>
          )}
          {d.novita.length > 0 && <Novita novita={d.novita} />}
          {d.target_raggiunti > 0 && (
            <span className={PASTIGLIA}>
              {contati(d.target_raggiunti, "target di prezzo raggiunto", "target di prezzo raggiunti")}
            </span>
          )}
          {d.posizioni_chiuse > 0 && (
            <Link to="/positions" className={PASTIGLIA}>
              {contati(d.posizioni_chiuse, "posizione chiusa", "posizioni chiuse")}
            </Link>
          )}
        </>
      )}
    </section>
  );
}
