import { numero } from "@/lib/numeri";

/* ─── Il prezzo di un mercato, in un formato solo (FA-183) ────────────────
 *
 * La pagina di dettaglio aveva un suo formato: `toFixed` (punto decimale)
 * sotto 1.000 e nessun decimale sopra, quindi «7297» per 7.297,49 e «47.59»
 * per 47,59. Qui la regola: due decimali con le migliaia raggruppate per
 * indici, materie prime e valute; le cripto oltre 10.000 senza decimali
 * (BTC a 63.570), sotto 1 con quattro (una valuta a 0,0068 ha bisogno delle
 * cifre). */

export function prezzoMercato(v: number | null | undefined, categoria?: string): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (categoria === "crypto" && abs >= 10_000) return numero(v, 0, true);
  // FA-190: un cambio vive sulla quarta cifra (euro/dollaro 1,0936).
  if (categoria === "fx" && abs < 10) return numero(v, 4, true);
  if (abs > 0 && abs < 1) return numero(v, 4, true);
  return numero(v, 2, true);
}

/** L'etichetta italiana della categoria di un mercato. */
export function nomeCategoria(categoria: string | undefined): string {
  switch (categoria) {
    case "index": return "Indice";
    case "commodity": return "Materia prima";
    case "crypto": return "Cripto";
    case "fx": return "Valuta";
    case "tassi": return "Tasso";
    default: return categoria ?? "";
  }
}
