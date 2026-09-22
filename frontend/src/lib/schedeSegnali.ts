import { Flag, Hourglass, Zap } from "lucide-react";

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
  {
    id: "formazione", label: "In formazione", icon: Hourglass,
    descrizione: "Condizioni che stanno convergendo",
  },
  { id: "segnali", label: "Segnali", icon: Zap, descrizione: "Segnali scattati" },
  { id: "esiti", label: "Esiti", icon: Flag, descrizione: "Come si sono chiusi" },
] as const;

export type SchedaId = (typeof SCHEDE)[number]["id"];

/** La scheda chiesta dall'URL. Un valore sconosciuto — un segnalibro vecchio,
 *  un refuso — apre i segnali invece di una pagina vuota. */
export function schedaDa(raw: string | null): SchedaId {
  return SCHEDE.some((s) => s.id === raw) ? (raw as SchedaId) : "segnali";
}
