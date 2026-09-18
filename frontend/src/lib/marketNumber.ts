/* ─── I numeri di mercato, in una lingua sola ─────────────────────────────── *
 *
 * ⚠️ Il difetto che questo modulo chiude: nella riga di contesto del cruscotto
 * comparivano affiancati «NIKKEI 65.620» e «ARGENTO 67.63». Lo stesso punto,
 * a due centimetri di distanza, separava le migliaia nel primo e i decimali
 * nel secondo — perche' il formattatore usava `toLocaleString("it-IT")` sopra
 * mille e `toFixed()` sotto. Non e' un vezzo tipografico: 67.63 letto
 * all'italiana e' sessantasettemilaseicentotrenta.
 *
 * E' la stessa famiglia dei difetti di UNITA' che questo progetto registra
 * (un valore gia' in migliaia stampato «159.1K», punti percentuali scambiati
 * per percentuali): il numero e' giusto, e' la sua lettura a essere sbagliata.
 *
 * Qui i livelli di mercato parlano italiano e basta. I prezzi dei TITOLI
 * restano dove sono, con il simbolo di valuta davanti — `lib/money.ts` e' il
 * proprietario di quelli, e un livello di indice non e' denaro.
 */

/** Cifre decimali sensate per la SCALA del valore. Un indice a cinque cifre
 *  non ha bisogno dei centesimi; il gas naturale a 2,86 ne ha bisogno eccome,
 *  e una cripto sotto l'unita' di piu'. */
function decimali(abs: number): number {
  if (abs >= 1000) return 0;
  if (abs >= 1) return 2;
  return 4;
}

/** Un livello di mercato: indice, materia prima, cripto. Sempre it-IT, quindi
 *  il punto separa SEMPRE le migliaia e la virgola SEMPRE i decimali. */
export function formatLivello(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  const d = decimali(Math.abs(v));
  /* ⚠️ `useGrouping: "always"` non e' pedanteria, ed e' stato un test a
   * scoprirlo: l'italiano raggruppa le migliaia col criterio «min2», quindi
   * `Intl` lascia 7730 SENZA separatore e scrive 65.620 con. Tipograficamente
   * e' corretto; su una riga dove i due stanno affiancati sembra invece che il
   * formato cambi da un titolo all'altro. Su un motore che non conosce
   * l'opzione (Safari 16 e precedenti) si torna al comportamento di prima:
   * corretto, solo meno uniforme. */
  return v.toLocaleString("it-IT", {
    minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: "always",
  });
}

/** Una variazione percentuale, col segno sempre esplicito: «+0,21%».
 *  Il segno davanti serve anche quando il colore lo dice gia' — il colore non
 *  esiste per chi legge in scala di grigi o con uno screen reader. */
export function formatVariazione(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  const corpo = Math.abs(v).toLocaleString("it-IT", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  /* ⚠️ Il segno si prende dal VALORE, non dalla stringa formattata: -0,004
   * arrotonda a «0,00» e scriverlo «-0,00» e' un ribasso che non c'e'. Sotto
   * mezzo centesimo di punto il segno sparisce insieme alla cifra. */
  const arrotondato = Number(v.toFixed(2));
  const segno = arrotondato > 0 ? "+" : arrotondato < 0 ? "−" : "";
  return `${segno}${corpo}%`;
}

/** La posizione di un valore dentro un intervallo, 0..1. Null quando
 *  l'intervallo non esiste o e' degenere — un marcatore a meta' su un
 *  intervallo nullo direbbe «a meta' strada» di niente. */
export function posizioneNelRange(
  valore: number | null | undefined,
  minimo: number | null | undefined,
  massimo: number | null | undefined,
): number | null {
  if (valore == null || minimo == null || massimo == null) return null;
  if (!Number.isFinite(valore) || !Number.isFinite(minimo) || !Number.isFinite(massimo)) return null;
  if (massimo <= minimo) return null;
  return Math.min(1, Math.max(0, (valore - minimo) / (massimo - minimo)));
}
