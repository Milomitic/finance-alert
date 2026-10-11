/** Come si scrive e si colora la variazione di un indicatore macro.
 *
 *  ⚠️ L'unita' la decide il backend (`unita_variazione`): "%" su un indice o un
 *  livello, "pp" su un tasso. Un tasso che passa da 3,75 a 4,00 e' salito di
 *  0,25 punti, non del 6,7%.
 *
 *  Il colore e' la DIREZIONE (rosa/smeraldo, la regola di CLAUDE.md), non un
 *  giudizio: un'inflazione che sale e' smeraldo come un PIL che sale. */

export function formatVariazioneMacro(v: number | null | undefined, unita: string, decimali = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const segno = v > 0 ? "+" : v < 0 ? "−" : "";
  const corpo = Math.abs(v).toFixed(decimali);
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
