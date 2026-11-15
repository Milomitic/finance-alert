import type { Misura } from "@/api/studio";

/* Formati e lettura dei parametri della pagina Studio (FA-157). */

export type Modello = "dopo_movimento" | "stagionalita" | "evento";

export const MODELLI: { id: Modello; label: string }[] = [
  { id: "dopo_movimento", label: "Dopo un movimento" },
  { id: "stagionalita", label: "Stagionalità" },
  { id: "evento", label: "Attorno a un evento" },
];

export type ParametriStudio = {
  simbolo: string;
  modello: Modello;
  sedute: number;
  soglia: number;
  orizzonte: number;
  tipo: "trimestrali" | "macro";
  serie: string;
};

function num(v: string | null, def: number, lo: number, hi: number): number {
  const n = Number(v);
  return v != null && v !== "" && Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : def;
}

/** I parametri dall'URL, con valori ammessi dal server: un link vecchio o
 *  scritto a mano non deve produrre una richiesta che risponde 422. */
export function parametriDaUrl(sp: URLSearchParams): ParametriStudio {
  const m = sp.get("modello");
  const soglia = num(sp.get("soglia"), -10, -90, 500);
  return {
    simbolo: (sp.get("simbolo") ?? "").trim().toUpperCase(),
    modello: MODELLI.some((x) => x.id === m) ? (m as Modello) : "dopo_movimento",
    sedute: Math.round(num(sp.get("sedute"), 5, 1, 63)),
    soglia: soglia === 0 ? -10 : soglia,
    orizzonte: Math.round(num(sp.get("orizzonte"), 21, 1, 252)),
    tipo: sp.get("tipo") === "macro" ? "macro" : "trimestrali",
    serie: (sp.get("serie") ?? "").trim().toUpperCase(),
  };
}

export function pct(v: number | null | undefined, cifre = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const p = v * 100;
  return `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p).toFixed(cifre).replace(".", ",")}%`;
}

/** «da −1,2% a +3,4%», o la frase che dice perche' manca. */
export function intervallo(m: Misura): string {
  if (!m.intervallo) return m.finestre < 2 ? "meno di due finestre indipendenti: non stimabile" : "—";
  return `da ${pct(m.intervallo[0])} a ${pct(m.intervallo[1])}`;
}
