import type { QueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { dashboard } from "@/api/dashboard";
import { fetchEtoroVivo } from "@/api/etoro";
import { market } from "@/api/market";
import { QUERY_CRITICHE_HOME } from "@/lib/freschezzaHome";

/* ─── Il primo caricamento della home parte prima (FA-179, fase C) ─────────
 *
 * Due cose, entrambe prima che React monti la pagina:
 *
 * 1. Le richieste della home partono SUBITO, in parallelo al download del
 *    codice delle schede, invece che dopo il montaggio.
 * 2. L'ultima risposta buona di ogni query critica si conserva sul
 *    dispositivo e si rimette in cache all'apertura, ma SOLO se e' entro la
 *    sua eta' massima (`freschezzaHome`) e se l'ha salvata la stessa versione
 *    dell'app. Altrimenti niente: meglio lo scheletro di un dato di tre giorni
 *    prima, e meglio nessun dato di uno con una forma che il codice nuovo non
 *    conosce. */

const PREFISSO = "home:";

/** Le funzioni d'accesso delle query critiche: le stesse dei loro hook. */
const CARICA: Record<string, (signal?: AbortSignal) => Promise<unknown>> = {
  "dashboard/summary": (s) => dashboard.summary(s),
  "dashboard/market-summary": (s) => market.summary(s),
  "live-assets": (s) => api("/api/dashboard/live-assets", { signal: s }),
  "etoro/vivo": (s) => fetchEtoroVivo(s),
};

const nome = (chiave: readonly unknown[]) => chiave.join("/");

/** La versione dell'app: il bundle d'ingresso ha l'hash nel nome, e cambia a
 *  ogni rilascio. Un dato salvato da un'altra versione non si ripristina. */
export function versioneApp(doc: Document = document): string {
  return doc.querySelector('script[type="module"][src*="/assets/index-"]')?.getAttribute("src") ?? "sviluppo";
}

export function ripristinaHome(qc: QueryClient, ora: number = Date.now(), versione = versioneApp()): number {
  let ripristinate = 0;
  for (const c of QUERY_CRITICHE_HOME) {
    try {
      const testo = localStorage.getItem(PREFISSO + nome(c.chiave));
      if (!testo) continue;
      const salvato = JSON.parse(testo) as { v: string; t: number; d: unknown };
      if (salvato.v !== versione || ora - salvato.t > c.etaMassimaMs) continue;
      qc.setQueryData(c.chiave, salvato.d, { updatedAt: salvato.t });
      ripristinate += 1;
    } catch {
      /* storage assente o voce rovinata: si carica dal server */
    }
  }
  return ripristinate;
}

/** Salva ogni risposta riuscita delle query critiche. Rende la funzione che
 *  smette di ascoltare. */
export function persistiHome(qc: QueryClient, versione = versioneApp()): () => void {
  const critiche = new Set(QUERY_CRITICHE_HOME.map((c) => nome(c.chiave)));
  return qc.getQueryCache().subscribe((evento) => {
    if (evento.type !== "updated" || evento.action.type !== "success") return;
    const chiave = nome(evento.query.queryKey);
    if (!critiche.has(chiave)) return;
    try {
      localStorage.setItem(
        PREFISSO + chiave,
        JSON.stringify({ v: versione, t: evento.query.state.dataUpdatedAt, d: evento.query.state.data }),
      );
    } catch {
      /* storage pieno o bloccato: la cache sul dispositivo e' un di piu' */
    }
  });
}

/** Fa partire le richieste della home prima del montaggio, solo sulla home. */
export function precaricaHome(qc: QueryClient, percorso: string = window.location.pathname): void {
  if (percorso !== "/") return;
  for (const c of QUERY_CRITICHE_HOME) {
    const carica = CARICA[nome(c.chiave)];
    if (carica) void qc.prefetchQuery({ queryKey: c.chiave, queryFn: ({ signal }) => carica(signal) });
  }
}
