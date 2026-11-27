import type { Caso } from "@/api/studio";

/* ─── I casi di uno studio in CSV (FA-193) ───────────────────────────────
 *
 * Per Excel in italiano: separatore «;», virgola decimale, e il BOM UTF-8 in
 * testa (senza, Excel legge le lettere accentate come due caratteri).
 * Percentuali come numeri («−4,12»), non come testo con il «%»: chi apre il
 * file vuole poterci fare i conti. */

const BOM = "﻿";

function cella(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "";
  return (v * 100).toFixed(2).replace(".", ",");
}

export function csvDeiCasi(casi: readonly Caso[], conMossa: boolean): string {
  const intestazione = ["data", ...(conMossa ? ["mossa_pct"] : []), "esito_pct", "episodio", "primo_giorno_episodio"];
  const righe = casi.map((c) => [
    c.data,
    ...(conMossa ? [cella(c.mossa)] : []),
    cella(c.esito),
    String(c.episodio),
    c.primo ? "si" : "no",
  ].join(";"));
  return BOM + [intestazione.join(";"), ...righe].join("\r\n") + "\r\n";
}

/** Il nome del file: simbolo e modello, senza caratteri che un disco rifiuta. */
export function nomeFileCasi(simbolo: string, modello: string): string {
  return `studio-${simbolo}-${modello}.csv`.replace(/[^A-Za-z0-9._-]/g, "_");
}
