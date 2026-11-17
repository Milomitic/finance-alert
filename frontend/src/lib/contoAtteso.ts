/** Se l'ultima volta il conto eToro c'era (A-05).
 *
 *  La dashboard aspettava la risposta del conto prima di disegnare qualunque
 *  cosa: per ~15 secondi undici schede grigie, anche se mercato e segnali
 *  erano pronti in pochi millisecondi. Ora il resto esce subito, e il conto
 *  tiene il suo posto solo se si sa che arrivera': lo dice l'ultima risposta,
 *  ricordata qui. Senza ricordo (prima visita, CI) non si riserva niente,
 *  quindi un conto non configurato non lascia un buco che poi si chiude. */

const CHIAVE = "dashboard.conto.atteso";

export function contoAtteso(): boolean {
  try {
    return localStorage.getItem(CHIAVE) === "1";
  } catch {
    return false;
  }
}

export function ricordaConto(presente: boolean): void {
  try {
    localStorage.setItem(CHIAVE, presente ? "1" : "0");
  } catch {
    /* nessun ricordo: alla prossima apertura il posto non si riserva */
  }
}
