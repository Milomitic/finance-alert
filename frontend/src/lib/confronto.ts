import { PERIODI_CONFRONTO, type PeriodoConfronto } from "@/hooks/useMercati";

/* Lo stato del confronto fra mercati nell'URL (FA-187): un link riapre lo
 * stesso grafico. `?confronta=^GSPC,GC=F&periodo=ytd`. */

export const MAX_CONFRONTO = 6;
export const PREDEFINITI = ["^GSPC", "^STOXX50E", "FTSEMIB.MI", "GC=F", "BTC-USD"];

/** I simboli dall'URL: senza doppioni, al massimo sei, maiuscoli. Assente il
 *  parametro: i predefiniti. Presente ma vuoto: nessuno (l'utente li ha tolti). */
export function simboliDaUrl(sp: URLSearchParams): string[] {
  const v = sp.get("confronta");
  if (v == null) return PREDEFINITI;
  return [...new Set(v.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean))].slice(0, MAX_CONFRONTO);
}

export function periodoDaUrl(sp: URLSearchParams): PeriodoConfronto {
  const p = sp.get("periodo");
  return (PERIODI_CONFRONTO as readonly string[]).includes(p ?? "") ? (p as PeriodoConfronto) : "ytd";
}

/** L'URL con lo stato nuovo, conservando gli altri parametri. */
export function conConfronto(sp: URLSearchParams, simboli: string[], periodo: PeriodoConfronto): URLSearchParams {
  const n = new URLSearchParams(sp);
  n.set("confronta", simboli.join(","));
  n.set("periodo", periodo);
  return n;
}

export const ETICHETTA_PERIODO: Record<PeriodoConfronto, string> = {
  "1m": "1M", "3m": "3M", "6m": "6M", ytd: "YTD", "1a": "1A", "3a": "3A", "5a": "5A", "10a": "10A",
};
