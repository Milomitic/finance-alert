import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { GradinoScalaOut, ScalaStoricaOut } from "@/api/schema.gen";
import { InfoHint } from "@/components/ui/info-hint";
import { cn } from "@/lib/utils";

/* ─── Fin dove arrivano i piani di questo tipo (FA-206) ───────────────────
 *
 * Le posizioni non sono automatiche: l'utente le chiude anche prima del
 * target. Quindi, accanto all'esito di QUESTO piano, serve sapere fin dove
 * arrivano di solito i piani dello stesso detector e verso prima di girarsi:
 * quanti passano da meta' strada, quanti arrivano al 90%, e che cosa succede
 * dopo a chi c'e' arrivato.
 *
 * ⚠️ Ogni quota porta l'intervallo sulle finestre INDIPENDENTI, non sulle
 * righe: venti segnali dello stesso giorno sono un giorno di mercato. Sotto
 * venti piani chiusi la scala non si mostra.
 *
 * ⚠️ Il replay decennale dice che chiudere prima non cambia l'attesa in R
 * (spec 2026-11-15, sezione FA-206): la scala aiuta a decidere con che rischio
 * stare dentro, non promette un guadagno a chi esce. */

const PCT = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });

function pct(frazione: number | null | undefined): string {
  return frazione == null ? "—" : `${PCT.format(frazione * 100)}%`;
}

function etichetta(soglia: number): string {
  return soglia === 100 ? "TP1" : `${soglia}%`;
}

/** Dei piani che hanno toccato il gradino, quanti sono poi finiti a stop. */
function poiStop(g: GradinoScalaOut): number {
  return (g.esiti.stop ?? 0) + (g.esiti.ambigua ?? 0);
}

function Gradino({ g, raggiunto }: { g: GradinoScalaOut; raggiunto: boolean }) {
  const stop = poiStop(g);
  return (
    <li className="grid grid-cols-[2.75rem_1fr_3rem] items-center gap-2 text-sm sm:grid-cols-[2.75rem_1fr_3rem_9.5rem]">
      <span className={cn("text-xs font-semibold tabular-nums", raggiunto ? "text-foreground" : "text-muted-foreground")}>
        {etichetta(g.soglia)}
      </span>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-muted">
        {/* Classi letterali: la barra e' neutra, non e' una direzione. */}
        <div className="absolute inset-y-0 left-0 rounded-full bg-sky-500/70 dark:bg-sky-400/60"
          style={{ width: `${Math.min(100, g.quota)}%` }} />
        {g.intervallo && (
          <div className="absolute inset-y-0 border-x border-sky-800/60 dark:border-sky-200/50"
            style={{ left: `${g.intervallo[0]}%`, width: `${Math.max(0, g.intervallo[1] - g.intervallo[0])}%` }} />
        )}
      </div>
      <span className="text-right text-xs font-semibold tabular-nums"
        title={g.intervallo ? `Intervallo al 95%: da ${PCT.format(g.intervallo[0])}% a ${PCT.format(g.intervallo[1])}%` : undefined}>
        {PCT.format(g.quota)}%
      </span>
      <span className="col-span-3 -mt-1 pl-[3.25rem] text-[0.7rem] text-muted-foreground tabular-nums sm:col-span-1 sm:mt-0 sm:pl-0">
        {g.soglia === 100
          ? `${g.toccati} completati`
          : g.toccati > 0 ? `poi stop ${stop} su ${g.toccati}` : "nessuno"}
      </span>
    </li>
  );
}

export function ScalaStoricaBlock({ id, piccoChiuso }: {
  id: number;
  /** Il massimo del piano di questo segnale, se gia' risolto; se aperto lo
   *  si legge dal percorso del piano aperto (stessa chiave di cache). */
  piccoChiuso?: number | null;
}) {
  const q = useQuery({
    queryKey: ["scala-storica", id],
    queryFn: ({ signal }) => api<ScalaStoricaOut | null>(`/api/alerts/${id}/scala-storica`, { signal }),
    staleTime: 10 * 60_000,
  });
  const aperto = useQuery({
    queryKey: ["open-plan-path", id],
    queryFn: ({ signal }) => api<{ peak_fraction: number; current_fraction: number } | null>(
      `/api/alerts/${id}/open-plan-path`, { signal }),
    staleTime: 60_000,
    enabled: piccoChiuso === undefined,
  });
  const picco = piccoChiuso ?? aperto.data?.peak_fraction ?? null;

  if (q.isLoading) return <div className="h-24 animate-pulse rounded-lg bg-muted/40" aria-hidden />;
  if (q.isError) {
    return (
      <button type="button" className="text-xs underline" onClick={() => q.refetch()}>
        Riprova a caricare la scala storica
      </button>
    );
  }
  const d = q.data;
  if (!d) return null;
  if (!d.sufficiente) {
    return (
      <p className="rounded-lg border border-dashed border-border/60 p-3 text-xs text-muted-foreground">
        Solo {d.piani} piani chiusi di questo tipo: troppo pochi per dire fin dove arrivano di solito.
      </p>
    );
  }
  const gradini = d.gradini ?? [];
  const stop = d.stop;
  const scaduti = d.scaduti;
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-sm font-semibold">Fin dove arrivano i piani di questo tipo</span>
        <InfoHint
          label="Scala storica"
          text={
            "Su tutti i piani chiusi dello stesso detector e verso: quanti hanno toccato il 25, 50, 75 e 90% della distanza fra ingresso e primo target, e quanti l'hanno completato. " +
            "«Poi stop» conta quelli che, dopo aver toccato il gradino, sono finiti allo stop. Le linee sottili sono l'intervallo al 95%, dimensionato sulle finestre indipendenti e non sui singoli segnali."
          }
        />
        <span className="text-xs text-muted-foreground tabular-nums">
          {d.piani} piani · {d.finestre} finestre indipendenti
        </span>
      </div>

      {picco != null && (
        <p className="text-xs">
          Questo piano: massimo al <strong className="tabular-nums">{pct(Math.min(1, picco))}</strong> della strada verso TP1.
        </p>
      )}

      <ul className="space-y-1.5" aria-label="Quota di piani che ha toccato ogni gradino">
        {gradini.map((g) => (
          <Gradino key={g.soglia} g={g} raggiunto={picco != null && picco >= g.soglia / 100 - 1e-9} />
        ))}
      </ul>

      <dl className="grid gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-md bg-muted/30 px-2.5 py-2">
          <dt className="text-muted-foreground">Massimo tipico</dt>
          <dd className="font-semibold tabular-nums">
            {d.giorni_al_picco == null ? "—" : `${PCT.format(d.giorni_al_picco)} giorni dopo l'ingresso`}
          </dd>
        </div>
        {stop && stop.numero > 0 && (
          <div className="rounded-md bg-muted/30 px-2.5 py-2">
            <dt className="text-muted-foreground">Stop passati da metà strada</dt>
            <dd className="font-semibold tabular-nums">
              {stop.passati_da_meta} su {stop.numero} ({pct(stop.passati_da_meta / stop.numero)})
            </dd>
          </div>
        )}
        {scaduti && scaduti.numero > 0 && (
          <div className="rounded-md bg-muted/30 px-2.5 py-2">
            <dt className="text-muted-foreground">Scaduti: massimo e chiusura tipici</dt>
            <dd className="font-semibold tabular-nums">
              {pct(scaduti.picco_mediano)} poi {pct(scaduti.chiusura_mediana)}
            </dd>
          </div>
        )}
      </dl>

      <p className="text-[0.7rem] text-muted-foreground">
        Descrive i piani passati dal {d.dal} al {d.al}, non prevede questo. Nel replay di dieci anni, chiudere prima
        (sul ritracciamento o vicino al target) ha lasciato l'attesa in R quasi invariata: cambia il rischio, non il
        rendimento medio.
      </p>
    </div>
  );
}
