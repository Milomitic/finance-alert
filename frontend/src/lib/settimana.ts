/* ─── I tuoi titoli e i nomi dei giorni ──────────────────────────────────
 *
 * Qui stava `settimana()`, la scheda «Questa settimana» (FA-088) e poi la
 * colonna dell'agenda nel jumbotron. Dal 2026-10-12 l'agenda e' una griglia di
 * quattro giorni lavorativi e la costruisce `agendaGiorni.ts`; restano qui la
 * rilevanza di un titolo seguito e l'etichetta di un giorno, che usano anche
 * altri.
 */

/** Perche' un titolo e' «tuo»: una posizione aperta o un preferito. */
export type Rilevanza = "posizione" | "preferito";

/** «Oggi», «Domani», o il giorno della settimana col numero: «mer 30». */
export function etichettaGiorno(giorno: string, distanza: number): string {
  if (distanza === 0) return "Oggi";
  if (distanza === 1) return "Domani";
  return new Date(`${giorno}T12:00:00Z`).toLocaleDateString("it-IT", {
    weekday: "short", day: "numeric", timeZone: "UTC",
  });
}
