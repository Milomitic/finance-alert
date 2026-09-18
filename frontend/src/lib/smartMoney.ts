import type { ActionAggregate, InstitutionalSummary } from "@/api/types";

/* ─── Le statistiche della pagina superinvestor ───────────────────────────── *
 *
 * Calcolo puro sopra i due payload che la pagina gia' scarica. Sta qui e non
 * dentro il JSX perche' ogni numero di questa fascia e' un'affermazione sul
 * denaro di qualcun altro, e va poter essere provato.
 *
 * ⚠️ Due cose che NON si possono dire con questi dati, e che sarebbe facile
 * scrivere per sbaglio:
 *
 * 1. **Il rapporto fra acquisti e vendite.** `recent_buys` e `recent_sells`
 *    arrivano TAGLIATE a `recent_actions_limit` dal server: contarle misura il
 *    limite, non il mercato. Un «60% di acquisti» su due liste da 15 sarebbe
 *    un numero inventato con l'aria di una misura.
 * 2. **«L'ultimo trimestre» come fotografia completa.** Ogni fondo compare con
 *    la propria ULTIMA dichiarazione, e i 13F arrivano scaglionati fino a 45
 *    giorni dopo la chiusura del trimestre: alla stessa data alcuni fondi sono
 *    gia' sul nuovo trimestre e altri no. Per questo il conteggio dei fondi
 *    che hanno gia' depositato sta ACCANTO al trimestre, invece di lasciar
 *    credere che siano tutti.
 */

/** Oltre due trimestri (~183 giorni) un fondo non sta piu' depositando, o lo
 *  scraper l'ha perso: con la finestra 13F di 45 giorni, un fondo vivo ha
 *  sempre qualcosa di piu' recente. Stessa soglia della tabella dei fondi. */
export const GIORNI_FONDO_FERMO = 183;

export interface StatisticheFondi {
  /** Quanti fondi ci sono in elenco. */
  totale: number;
  /** Somma dei portafogli dichiarati. ⚠️ Non e' una fotografia a una data: e'
   *  la somma delle ULTIME dichiarazioni, che sono di trimestri diversi. */
  capitale: number | null;
  /** Il trimestre piu' recente presente nell'elenco. */
  ultimoTrimestre: string | null;
  /** Quanti fondi hanno gia' depositato PER quel trimestre. */
  fondiSulTrimestre: number;
  /** Quanti non depositano da oltre due trimestri. */
  fermi: number;
}

export function statisticheFondi(
  fondi: readonly InstitutionalSummary[] | undefined,
  adesso: number = Date.now(),
): StatisticheFondi {
  const righe = fondi ?? [];
  const valori = righe
    .map((f) => f.total_value_usd)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const periodi = righe
    .map((f) => f.latest_period_end)
    .filter((p): p is string => !!p);
  /* Confronto lessicografico: le date sono ISO, quindi l'ordine alfabetico E'
   * l'ordine cronologico. Passare da `Date` qui vorrebbe dire creare 200
   * oggetti per trovare un massimo su stringhe gia' ordinabili. */
  const ultimoTrimestre = periodi.length > 0 ? periodi.reduce((a, b) => (b > a ? b : a)) : null;
  return {
    totale: righe.length,
    // Nessun valore utilizzabile non fa zero: zero direbbe «i fondi non hanno
    // niente in portafoglio», che e' un'affermazione, non un'assenza.
    capitale: valori.length > 0 ? valori.reduce((a, b) => a + b, 0) : null,
    ultimoTrimestre,
    fondiSulTrimestre: ultimoTrimestre
      ? righe.filter((f) => f.latest_period_end === ultimoTrimestre).length
      : 0,
    fermi: righe.filter((f) => {
      if (!f.latest_period_end) return false;
      const ts = Date.parse(f.latest_period_end);
      if (Number.isNaN(ts)) return false;
      return adesso - ts > GIORNI_FONDO_FERMO * 86_400_000;
    }).length,
  };
}

/** Le mosse piu' pesanti, per valore della posizione. Il server le ordina gia'
 *  cosi' e bilancia il mix di azioni; qui si taglia alla lunghezza che sta a
 *  schermo e si ri-ordina per non dipendere da quell'ordine.
 *
 *  ⚠️ Una riga senza valore va IN FONDO, non trattata come zero: «valore
 *  ignoto» e «posizione da zero dollari» sono cose diverse, e la seconda
 *  metterebbe in cima chi non ha dichiarato nulla se l'ordine fosse crescente. */
export function mossePiuPesanti(
  righe: readonly ActionAggregate[] | undefined,
  quante: number,
): ActionAggregate[] {
  return [...(righe ?? [])]
    .sort((a, b) => {
      const av = a.value_usd;
      const bv = b.value_usd;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return bv - av;
    })
    .slice(0, quante);
}

/** Il settore col peso maggiore, con la sua quota. Null quando non c'e'
 *  niente da pesare — una quota su un totale zero non esiste. */
export function settoreDominante(
  tilt: Record<string, number> | undefined,
): { settore: string; quota: number } | null {
  const voci = Object.entries(tilt ?? {}).filter(([, v]) => Number.isFinite(v) && v > 0);
  if (voci.length === 0) return null;
  const totale = voci.reduce((s, [, v]) => s + v, 0);
  if (totale <= 0) return null;
  const [settore, valore] = voci.reduce((a, b) => (b[1] > a[1] ? b : a));
  return { settore, quota: (valore / totale) * 100 };
}

/** L'etichetta italiana di un'azione 13F. Le costanti del backend sono in
 *  inglese e comparivano crude in tabella («new», «sold_out»). */
export const AZIONE_LABEL: Record<string, string> = {
  new: "nuova",
  add: "aumento",
  reduce: "riduzione",
  sold_out: "uscita",
  hold: "invariata",
};

/** Un'azione DECISIVA apre o chiude del tutto una posizione: e' la mossa che
 *  dice qualcosa di netto, mentre un aumento del 3% e' manutenzione. */
export function azioneDecisiva(azione: string | null): boolean {
  return azione === "new" || azione === "sold_out";
}
