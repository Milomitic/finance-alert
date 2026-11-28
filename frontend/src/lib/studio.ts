import type { Misura } from "@/api/studio";

/* Formati e lettura dei parametri della pagina Studio (FA-157). */

export type Modello = "dopo_movimento" | "stagionalita" | "evento" | "primo_passaggio" | "cali";

export const MODELLI: { id: Modello; label: string }[] = [
  { id: "dopo_movimento", label: "Dopo un movimento" },
  { id: "stagionalita", label: "Stagionalità" },
  { id: "evento", label: "Attorno a un evento" },
  { id: "primo_passaggio", label: "Toccare prima" },
  { id: "cali", label: "Cali e recuperi" },
];

/** FA-197: i riferimenti per «al netto di». */
export const RIFERIMENTI: { id: string; label: string }[] = [
  { id: "^GSPC", label: "S&P 500" },
  { id: "^IXIC", label: "Nasdaq" },
  { id: "^STOXX50E", label: "Euro Stoxx 50" },
  { id: "FTSEMIB.MI", label: "FTSE MIB" },
  { id: "^N225", label: "Nikkei 225" },
];

/** Le domande che accettano «al netto di». */
export const CON_NETTO: readonly Modello[] = ["dopo_movimento", "stagionalita", "evento"];

export type ParametriStudio = {
  simbolo: string;
  modello: Modello;
  sedute: number;
  soglia: number;
  orizzonte: number;
  tipo: "trimestrali" | "macro";
  serie: string;
  /** FA-196 */
  lato: "long" | "short";
  target: number;
  stop: number;
  /** FA-197: il simbolo di riferimento, "" = nessuno. */
  netto: string;
  /** FA-198 */
  sogliaCali: number;
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
    lato: sp.get("lato") === "short" ? "short" : "long",
    target: num(sp.get("target"), 8, 0.5, 200),
    stop: num(sp.get("stop"), 5, 0.5, 90),
    netto: (sp.get("netto") ?? "").trim().toUpperCase(),
    sogliaCali: num(sp.get("soglia_cali"), 10, 2, 90),
  };
}

/** L'URL di uno studio dai suoi parametri: solo quelli che la domanda usa. */
export function urlDaParametri(p: ParametriStudio): URLSearchParams {
  const n = new URLSearchParams();
  n.set("simbolo", p.simbolo.trim().toUpperCase());
  n.set("modello", p.modello);
  if (p.modello === "dopo_movimento") {
    n.set("sedute", String(p.sedute));
    n.set("soglia", String(p.soglia));
    n.set("orizzonte", String(p.orizzonte));
  }
  if (p.modello === "evento") {
    n.set("tipo", p.tipo);
    n.set("orizzonte", String(Math.min(p.orizzonte, 10)));
    if (p.tipo === "macro") n.set("serie", p.serie.trim().toUpperCase());
  }
  if (p.modello === "primo_passaggio") {
    n.set("lato", p.lato);
    n.set("target", String(p.target));
    n.set("stop", String(p.stop));
    n.set("orizzonte", String(p.orizzonte));
  }
  if (p.modello === "cali") n.set("soglia_cali", String(p.sogliaCali));
  if (CON_NETTO.includes(p.modello) && p.netto) n.set("netto", p.netto);
  return n;
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

/** FA-192: dove cade `v` sull'asse dell'istogramma, da 0 (bordo sinistro
 *  della prima fascia) a 1 (bordo destro dell'ultima), interpolando dentro la
 *  fascia che lo contiene. Fuori dall'asse: null — una linea dello zero non si
 *  disegna se lo zero non c'e'. */
export function posizioneSulleFasce(
  v: number | null | undefined,
  fasce: readonly { da: number; a: number }[],
): number | null {
  if (v == null || !Number.isFinite(v) || fasce.length === 0) return null;
  const n = fasce.length;
  for (let i = 0; i < n; i++) {
    const f = fasce[i];
    const ultima = i === n - 1;
    if (v >= f.da && (v < f.a || (ultima && v <= f.a))) {
      const dentro = f.a > f.da ? (v - f.da) / (f.a - f.da) : 0.5;
      return (i + dentro) / n;
    }
  }
  return null;
}

/** La soglia di un movimento nella frase: «−10%» e «+5%», col meno tipografico. */
export function sogliaInFrase(soglia: number): string {
  const corpo = Math.abs(soglia).toLocaleString("it-IT", { maximumFractionDigits: 2 });
  return `${soglia < 0 ? "−" : "+"}${corpo}%`;
}

/** FA-199 (F15): tre domande pronte su un simbolo, con l'URL dello Studio. */
export function domandePronte(simbolo: string, tipo: "titolo" | "mercato"): { testo: string; url: string }[] {
  const url = (p: Record<string, string>) => `/studio?${new URLSearchParams({ simbolo, ...p }).toString()}`;
  return [
    { testo: "Dopo un calo del 5% in 5 sedute, cosa è successo nel mese dopo?",
      url: url({ modello: "dopo_movimento", soglia: "-5", sedute: "5", orizzonte: "21" }) },
    { testo: "In quali mesi è andato meglio, e con quale regolarità?", url: url({ modello: "stagionalita" }) },
    tipo === "titolo"
      ? { testo: "Cosa fa attorno alle trimestrali?", url: url({ modello: "evento", tipo: "trimestrali", orizzonte: "5" }) }
      : { testo: "Cosa fa attorno ai dati sull'inflazione USA?",
          url: url({ modello: "evento", tipo: "macro", serie: "CPIAUCSL", orizzonte: "5" }) },
  ];
}
