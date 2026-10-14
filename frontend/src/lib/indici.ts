import type { IndexOption } from "@/api/types";

/* Il nome breve di un indice, per le etichette (richiesta dell'utente,
 * 2026-10-14). La sigla «NDX» accanto alla borsa «NASDAQ» si leggeva come una
 * ripetizione; il nome del catalogo invece porta precisazioni («FTSE 100
 * (London)», «Nikkei 225 (top constituents)») che allargano troppo la riga.
 * Il nome completo resta nel tooltip. */
const BREVI: Record<string, string> = {
  CSI300: "CSI 300",
  DJI: "Dow Jones",
  EUSTX50: "Euro Stoxx 50",
  FTSE100: "FTSE 100",
  FTSEMIB: "FTSE MIB",
  HSI30: "Hang Seng",
  KOSPI20: "KOSPI",
  N225: "Nikkei 225",
  NDX: "Nasdaq 100",
  SP500: "S&P 500",
};

/** Un indice nuovo, senza voce qui, prende il nome del catalogo senza la
 *  parentesi finale: mai la sigla, che e' cio' che creava l'equivoco. */
export function nomeBreveIndice(idx: IndexOption): string {
  return BREVI[idx.code] ?? (idx.name.replace(/\s*\([^)]*\)\s*$/, "").trim() || idx.code);
}
