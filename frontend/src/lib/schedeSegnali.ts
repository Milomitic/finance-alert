/* Le schede della pagina Segnali, come DATO.
 *
 * Vivono fuori dalla pagina per la stessa ragione di `lib/nav.ts`: un file che
 * esporta un componente E una costante rompe il Fast Refresh, e un elenco di
 * destinazioni non e' un componente. Il test delle schede legge questo senza
 * montare niente. */

/** ⚠️ L'ordine e' la vita di un'idea, non un gusto: un setup diventa un
 *  segnale che diventa un esito. Invertirle racconterebbe la storia al
 *  contrario, che e' esattamente il difetto che la barra laterale aveva prima
 *  del raggruppamento. */
export const SCHEDE = [
  { id: "formazione", label: "In formazione" },
  { id: "segnali", label: "Segnali" },
  { id: "esiti", label: "Esiti" },
] as const;

export type SchedaId = (typeof SCHEDE)[number]["id"];

/** La scheda chiesta dall'URL. Un valore sconosciuto — un segnalibro vecchio,
 *  un refuso — apre i segnali invece di una pagina vuota. */
export function schedaDa(raw: string | null): SchedaId {
  return SCHEDE.some((s) => s.id === raw) ? (raw as SchedaId) : "segnali";
}
