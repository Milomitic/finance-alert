/** Come si scrive e si colora la variazione di un indicatore macro.
 *
 *  ⚠️ L'unita' la decide il backend (`unita_variazione`): "%" su un indice o un
 *  livello, "pp" su un tasso. Un tasso che passa da 3,75 a 4,00 e' salito di
 *  0,25 punti, non del 6,7%.
 *
 *  ⚠️ Il colore di una variazione macro e' il suo ESITO contro la stima, non il
 *  segno (2026-10-11): un'inflazione al +0,2% contro un +0,4% atteso e' una
 *  sorpresa al ribasso anche se e' positiva. `tonoEsito` legge l'esito che il
 *  backend calcola per ciascuna misura; senza stima la variazione resta
 *  neutra. Il colore del segno (`tonoVariazione`) resta per i RENDIMENTI di
 *  mercato, dove la direzione e' l'informazione. */

/** Una cifra decimale sulle percentuali; sui punti fino a due, senza zeri
 *  inutili — un taglio dei tassi di 0,25 punti non diventa «0,3 pp». */
export function formatVariazioneMacro(v: number | null | undefined, unita: string, decimali = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const corpo = unita === "pp" ? String(Number(Math.abs(v).toFixed(2))) : Math.abs(v).toFixed(decimali);
  // Il segno segue il numero SCRITTO: +0,04% si legge «0.0%», non «+0.0%».
  const zero = Number(corpo) === 0;
  const segno = zero ? "" : v > 0 ? "+" : "−";
  return unita === "pp" ? `${segno}${corpo} pp` : `${segno}${corpo}%`;
}

export const TONO_VARIAZIONE = {
  su: "text-emerald-800 dark:text-emerald-400",
  giu: "text-rose-600 dark:text-rose-400",
  fermo: "text-muted-foreground",
} as const;

export function tonoVariazione(v: number | null | undefined): string {
  if (v == null || v === 0) return TONO_VARIAZIONE.fermo;
  return v > 0 ? TONO_VARIAZIONE.su : TONO_VARIAZIONE.giu;
}

/** L'esito di una variazione contro la stima della sua misura, dal backend
 *  (`macro_consenso_service.esiti`): verde sopra, rosso sotto, nessun colore
 *  in linea o senza stima. */
export function tonoEsito(esito: string | null | undefined): string {
  return esito === "sopra" ? TONO_VARIAZIONE.su : esito === "sotto" ? TONO_VARIAZIONE.giu : "";
}

/** Il riempimento di una barra del grafico per esito; grigio senza stima. */
export function coloreEsito(esito: string | null | undefined): string {
  return esito === "sopra" ? "rgb(16 185 129)" : esito === "sotto" ? "rgb(244 63 94)" : "rgb(148 163 184)";
}

/** Il dato contro la stima del SUO rilascio: verde sopra, rosso sotto. */
export function tonoControStima(v: number | null | undefined, stima: number | null | undefined): string {
  if (v == null || stima == null) return "";
  return v > stima ? TONO_VARIAZIONE.su : v < stima ? TONO_VARIAZIONE.giu : TONO_VARIAZIONE.fermo;
}

/** Come leggere una correlazione a parole, per |r|. Soglie convenzionali, dette
 *  a schermo: «debole» sotto 0,3, «moderata» fino a 0,6, «forte» sopra. */
export function forzaCorrelazione(r: number): string {
  const a = Math.abs(r);
  const verso = r >= 0 ? "positiva" : "negativa";
  if (a < 0.1) return "praticamente nulla";
  if (a < 0.3) return `debole ${verso}`;
  if (a < 0.6) return `moderata ${verso}`;
  return `forte ${verso}`;
}
