import { useState } from "react";

import type { EtoroStrumento } from "@/api/etoro";
import { useAbbinaEtoro } from "@/hooks/useEtoro";

/* ─── Gli strumenti eToro da abbinare al catalogo (FA-124) ────────────────
 *
 * Dentro la scheda del portafoglio e non in Diagnostica: li' comparirebbe a
 * dati arrivati e spingerebbe giu' il log (FA-106), e un abbinamento si decide
 * guardando la posizione, non la salute del sistema.
 *
 * L'abbinamento automatico chiede simbolo identico E nome compatibile. Quando
 * manca uno dei due, lo strumento aspetta qui: un abbinamento sbagliato
 * metterebbe la posizione sul titolo di un'altra societa', con le sue novita'
 * e le sue notifiche, ed e' esattamente il tipo di errore che sembra giusto.
 *
 * Gli strumenti fuori catalogo per natura (crypto, materie prime, indici)
 * si possono dichiarare tali: la posizione resta visibile, solo senza titolo.
 */

function Riga({ s }: { s: EtoroStrumento }) {
  const abbina = useAbbinaEtoro();
  const [ticker, setTicker] = useState("");
  const errore = abbina.error instanceof Error ? abbina.error.message : null;
  return (
    <li className="space-y-1.5 py-2">
      <div className="text-sm">
        <span className="font-semibold">{s.simbolo ?? `#${s.instrument_id}`}</span>
        {s.nome && <span className="text-muted-foreground"> · {s.nome}</span>}
        {s.tipo && <span className="text-muted-foreground"> · {s.tipo}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {s.candidato_ticker && (
          <button
            type="button"
            disabled={abbina.isPending}
            onClick={() => abbina.mutate({ instrumentId: s.instrument_id, ticker: s.candidato_ticker })}
            className="rounded-md border border-border/60 px-2 py-1 text-xs font-semibold hover:bg-muted disabled:opacity-50"
          >
            È {s.candidato_ticker}{s.candidato_nome ? ` (${s.candidato_nome})` : ""}
          </button>
        )}
        <form
          className="flex items-center gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (ticker.trim()) abbina.mutate({ instrumentId: s.instrument_id, ticker: ticker.trim() });
          }}
        >
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            aria-label={`Ticker del catalogo per ${s.simbolo ?? s.instrument_id}`}
            placeholder="altro ticker"
            className="h-7 w-28 rounded-md border bg-background px-2 text-xs"
          />
          <button
            type="submit"
            disabled={abbina.isPending || !ticker.trim()}
            className="rounded-md border border-border/60 px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
          >
            Abbina
          </button>
        </form>
        <button
          type="button"
          disabled={abbina.isPending}
          onClick={() => abbina.mutate({ instrumentId: s.instrument_id, ticker: null })}
          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
        >
          Non è nel catalogo
        </button>
      </div>
      {errore && <p className="text-xs text-red-600 dark:text-red-400">{errore}</p>}
    </li>
  );
}

/** `lista` arriva gia' filtrata dal server (`da_decidere`), nella stessa
 *  risposta del portafoglio. */
export function EtoroDaAbbinare({ lista }: { lista: readonly EtoroStrumento[] }) {
  if (lista.length === 0) return null;
  return (
    <div className="rounded-md border border-amber-300/60 bg-amber-50/40 px-3 py-2 dark:border-amber-800/50 dark:bg-amber-950/20">
      <div className="text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">
        Da abbinare al catalogo
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Non si sono abbinati da soli: il simbolo non c'è nel catalogo, oppure c'è ma il nome non coincide.
        Finché non decidi, la posizione non conta fra i tuoi titoli.
      </p>
      <ul className="divide-y divide-border/40">
        {lista.map((s) => <Riga key={s.instrument_id} s={s} />)}
      </ul>
    </div>
  );
}
