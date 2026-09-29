/** «Dalle 14:10», «Da ieri alle 18:40», «Da lun 28 set alle 09:05»: da quando
 *  conta la riga «Dall'ultima visita» del cruscotto. Giorni e ore LOCALI da
 *  entrambe le parti, quindi il confronto regge in ogni fuso. */
export function etichettaDal(dal: string, adesso: Date = new Date()): string {
  const d = new Date(dal);
  const ora = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === adesso.toDateString()) return `Dalle ${ora}`;
  const ieri = new Date(adesso);
  ieri.setDate(adesso.getDate() - 1);
  if (d.toDateString() === ieri.toDateString()) return `Da ieri alle ${ora}`;
  const giorno = d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" });
  return `Da ${giorno} alle ${ora}`;
}

/** «1 segnale nuovo» / «3 segnali nuovi». */
export function contati(n: number, uno: string, molti: string): string {
  return `${n} ${n === 1 ? uno : molti}`;
}
