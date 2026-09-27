/** Le voci di CONTESTO del paniere live della home: tutto `LIVE_ASSET_DEFINITIONS`
 *  (`backend/app/api/market.py`) tranne le tre americane e il VIX, che hanno
 *  un posto loro nel jumbotron.
 *
 *  Serve a una cosa sola: disegnare la riga «Indici · Materie prime · Cripto»
 *  PRIMA che arrivino le quotazioni (FA-106). Senza, la riga nasceva vuota e
 *  cresceva di ~245px quando la chiamata rispondeva — in produzione dopo 1,7 s
 *  di media — spingendo giu' tutto il resto: CLS 0,22 su un telefono. Con le
 *  voci gia' a schermo arrivano solo i valori, e la riga ha subito la sua forma.
 *
 *  ⚠️ E' un GEMELLO dell'elenco del backend, e un gemello invecchia in
 *  silenzio: `backend/tests/test_paniere_live_gemello.py` lo confronta con
 *  l'originale — simboli, categorie, bandiere — e diventa rosso se divergono.
 */
export const PANIERE_CONTESTO: readonly {
  symbol: string;
  category: "index" | "commodity" | "crypto";
  flag: string | null;
}[] = [
  { symbol: "^N225", category: "index", flag: "jp" },
  { symbol: "^STOXX50E", category: "index", flag: "eu" },
  { symbol: "FTSEMIB.MI", category: "index", flag: "it" },
  { symbol: "^HSI", category: "index", flag: "hk" },
  { symbol: "000300.SS", category: "index", flag: "cn" },
  { symbol: "GC=F", category: "commodity", flag: null },
  { symbol: "SI=F", category: "commodity", flag: null },
  { symbol: "CL=F", category: "commodity", flag: null },
  { symbol: "NG=F", category: "commodity", flag: null },
  { symbol: "BTC-USD", category: "crypto", flag: null },
  { symbol: "ETH-USD", category: "crypto", flag: null },
];
