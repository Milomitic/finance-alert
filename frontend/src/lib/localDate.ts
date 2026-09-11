/* ─── Il giorno che l'utente sta guardando ────────────────────────────────
 *
 * `Date.prototype.toISOString()` converte in UTC prima di formattare, quindi
 * `toISOString().slice(0, 10)` NON e «la data di questo oggetto»: e la data
 * che quell'istante ha a Greenwich. Le due differiscono per una finestra di
 * ore larga quanto lo scostamento del fuso, e in direzioni opposte ai due
 * lati del meridiano:
 *
 *   Roma (UTC+2)      12 set 00:30 locale  ->  UTC dice 11 set   (indietro)
 *   New York (UTC-4)  10 set 21:00 locale  ->  UTC dice 11 set   (avanti)
 *
 * ⚠️ A ovest la finestra sbagliata e la SERA, cioe l'orario in cui un
 * calendario si guarda davvero. E a mezzogiorno i due coincidono ovunque,
 * che e precisamente il motivo per cui il difetto sopravvive a una prova
 * manuale fatta in orario di lavoro.
 *
 * Usare questa funzione dove si intende il giorno di CALENDARIO dell'utente.
 * NON usarla per confrontare una data di SEDUTA che arriva dal backend —
 * `as_of_date` nasce dalla barra OHLCV e vive nel fuso del mercato, non in
 * quello di chi guarda: li il riferimento giusto e una domanda aperta, non
 * questa risposta.
 */
export function toLocalIsoDate(d: Date): string {
  const mese = String(d.getMonth() + 1).padStart(2, "0");
  const giorno = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mese}-${giorno}`;
}
