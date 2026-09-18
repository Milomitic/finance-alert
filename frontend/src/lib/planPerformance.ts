import type { PlanPerfRow } from "@/api/platformHealth";

/** Il colore di un'attesa in R.
 *
 * ⚠️ Si colora SOLO dove l'intervallo scavalca lo zero davvero, mai sulla
 * stima puntuale. È la lezione che questo progetto ha già scritto una volta:
 * il cubo dei detector colorava sul punto (>=55 verde) mentre l'API gli
 * passava le finestre indipendenti e un verdetto costruiti apposta per
 * impedirlo, e ogni detector che dipingeva di verde era in realtà «non
 * concludente».
 *
 * `emerald`/`rose` e non `green`/`red`: qui è una DIREZIONE (si guadagna o si
 * perde), non un guasto.
 */
export function verdictTone(verdict: PlanPerfRow["verdict"]): string {
  if (verdict === "positive") return "text-emerald-800 dark:text-emerald-400";
  if (verdict === "negative") return "text-rose-700 dark:text-rose-400";
  return "text-muted-foreground";
}

/** La riga sotto l'attesa: l'intervallo, o perché non c'è.
 *
 * ⚠️ Mai una stringa vuota. Uno spazio bianco sotto un numero si legge come
 * «il numero è solido»; «non concludente» dice la cosa vera, ed è la risposta
 * che il magazzino dà quasi sempre finché il tempo non passa. */
export function expectancyInterval(row: PlanPerfRow): string {
  if (!row.expectancy_ci) return "non concludente";
  const [basso, alto] = row.expectancy_ci;
  return `${basso.toFixed(2)} … ${alto.toFixed(2)}`;
}

/** `+0.25R` / `-1.00R`: il segno è sempre esplicito, perché un'attesa senza
 *  segno si legge come un valore assoluto. */
export function expectancyLabel(row: PlanPerfRow): string {
  return `${row.expectancy_r >= 0 ? "+" : ""}${row.expectancy_r.toFixed(2)}R`;
}
