import type { CalendarEvent } from "@/api/types";

/** Il calendario ridotto ai tuoi titoli: le trimestrali dei preferiti e delle
 *  posizioni aperte, e TUTTI gli eventi macro.
 *
 *  ⚠️ I macro restano: non sono di un titolo, e toglierli trasformerebbe
 *  «i miei titoli» in «solo trimestrali», che e' gia' un altro filtro della
 *  stessa barra. Chi li vuole via usa «Solo earnings». */
export function soloDeiMieiTitoli(
  eventi: readonly CalendarEvent[],
  titoli: ReadonlyMap<string, unknown>,
): CalendarEvent[] {
  return eventi.filter((e) => e.kind !== "earnings" || titoli.has(e.ticker));
}
