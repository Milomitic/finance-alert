/* Le colonne della lista Esiti › Segnali, come DATO (2026-09-22).
 *
 * Ordinabili e nascondibili come quelle della tabella Segnali, su richiesta
 * dell'utente. La lista pero' non e' una `<table>`: e' una griglia, una riga
 * per segnale, e una griglia ha un numero FISSO di tracce — nascondere una
 * cella senza togliere la sua traccia farebbe scivolare ogni valore sotto
 * l'intestazione accanto.
 *
 * Quindi le tracce si calcolano qui, dalle colonne visibili, per ciascuna
 * larghezza, e arrivano alla griglia come variabili CSS. ⚠️ Le classi che le
 * leggono sono letterali (`grid-cols-[var(--g)]`, …): il purger di Tailwind
 * vede solo stringhe intere, e un template composto a runtime sparirebbe dal
 * bundle di produzione.
 *
 * ⚠️ `null` in una traccia vuol dire che a quella larghezza la CELLA e'
 * nascosta dalle sue classi (`hidden xl:block` e simili). Le due cose vanno
 * tenute insieme: una traccia per una cella `display:none` sposta tutto di
 * una colonna, ed e' il difetto che i quattro template letterali di prima
 * evitavano a mano. */

/** Le chiavi di ordinamento che il server accetta (`ORDINAMENTI_ESITI`). */
export type OrdineEsiti =
  | "ticker" | "detector" | "esito" | "resolved_date" | "pl" | "r_multiple" | "bars_to_outcome";

export type ColonnaEsitiId =
  | "titolo" | "condizione" | "esito" | "chiusa" | "pl" | "r" | "sedute" | "sequenza" | "dopo";

export interface ColonnaEsiti {
  id: ColonnaEsitiId;
  label: string;
  /** Tracce a < sm, sm, lg, xl. */
  tracce: readonly [string | null, string | null, string | null, string | null];
  /** Il titolo e' l'identita' della riga: non si nasconde. */
  nascondibile: boolean;
  ordina?: OrdineEsiti;
}

export const COLONNE_ESITI: readonly ColonnaEsiti[] = [
  { id: "titolo", label: "Titolo", nascondibile: false, ordina: "ticker",
    tracce: ["minmax(0,1fr)", "minmax(0,1fr)", "minmax(0,1fr)", "minmax(0,1fr)"] },
  { id: "condizione", label: "Condizione", nascondibile: true, ordina: "detector",
    tracce: [null, null, null, "136px"] },
  { id: "esito", label: "Esito", nascondibile: true, ordina: "esito",
    tracce: ["auto", "116px", "116px", "116px"] },
  { id: "chiusa", label: "Chiusa", nascondibile: true, ordina: "resolved_date",
    tracce: [null, "68px", "68px", "68px"] },
  { id: "pl", label: "P/L", nascondibile: true, ordina: "pl",
    tracce: ["auto", "60px", "60px", "60px"] },
  { id: "r", label: "R", nascondibile: true, ordina: "r_multiple",
    tracce: ["auto", "64px", "64px", "64px"] },
  { id: "sedute", label: "Sedute", nascondibile: true, ordina: "bars_to_outcome",
    tracce: [null, null, null, "60px"] },
  { id: "sequenza", label: "Sequenza", nascondibile: true,
    tracce: ["64px", "96px", "96px", "120px"] },
  { id: "dopo", label: "Dopo chiusura", nascondibile: true,
    tracce: [null, null, "112px", "112px"] },
];

/** Per il menu «Colonne»: solo quelle che si possono spegnere. */
export const COLONNE_ESITI_NASCONDIBILI = COLONNE_ESITI
  .filter((c) => c.nascondibile)
  .map(({ id, label }) => ({ id, label }));

/** Le variabili CSS della griglia per le colonne visibili. */
export function trackEsiti(visibile: (id: ColonnaEsitiId) => boolean): Record<string, string> {
  const nomi = ["--g", "--g-sm", "--g-lg", "--g-xl"] as const;
  const out: Record<string, string> = {};
  nomi.forEach((nome, i) => {
    out[nome] = COLONNE_ESITI
      .filter((c) => !c.nascondibile || visibile(c.id))
      .map((c) => c.tracce[i])
      .filter((t): t is string => t !== null)
      .join(" ");
  });
  return out;
}

/** Il verso di partenza quando si sceglie una colonna nuova: le parole in
 *  ordine alfabetico, i numeri e le date dal piu' grande — il migliore e il
 *  piu' recente in cima, che e' la domanda con cui si arriva. */
export function versoIniziale(o: OrdineEsiti): "asc" | "desc" {
  return o === "ticker" || o === "detector" || o === "esito" ? "asc" : "desc";
}

/** Un ordinamento letto dall'URL, o null se non e' uno che il server accetta:
 *  un segnalibro con un refuso apre l'ordine predefinito invece di un 400. */
export function ordineDa(raw: string | null): OrdineEsiti | null {
  return COLONNE_ESITI.some((c) => c.ordina === raw) ? (raw as OrdineEsiti) : null;
}
