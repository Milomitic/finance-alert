/** Quali schede hanno senso nella pagina di uno strumento.
 *
 * Fondamentali, target degli analisti e insider descrivono un'AZIENDA. Un ETF
 * su un indice o un settore non ha bilanci, consenso o insider propri: le
 * schede restavano vuote o mostravano i dati del gestore. Le news invece hanno
 * senso dove il prezzo segue un bene e non un paniere di aziende — crypto e
 * materie prime — e restano anche per gli ETF che li replicano.
 *
 * Le pagine di indici, crypto e materie prime (`/markets/:symbol`) non hanno
 * mai avuto fondamentali o analisti; crypto e materie prime ora hanno le news.
 *
 * ⚠️ L'elenco degli ETF su materie prime e crypto e' scritto a mano: il
 * catalogo distingue solo "equity" da "etf". Oggi ne contiene uno, USO; gli
 * altri sono i piu' scambiati, perche' un ETF nuovo cada nel posto giusto.
 */
export interface SchedeStrumento {
  fondamentali: boolean;
  news: boolean;
  analisti: boolean;
}

const ETF_SU_BENI = new Set([
  // materie prime
  "USO", "UCO", "SCO", "BNO", "UNG", "BOIL", "KOLD", "GLD", "IAU", "GLDM",
  "SLV", "SIVR", "PPLT", "PALL", "CPER", "DBA", "DBC", "PDBC", "GSG", "DBO",
  // crypto
  "IBIT", "FBTC", "GBTC", "ARKB", "BITB", "BITO", "BITX", "ETHA", "ETHE", "FETH",
]);

export function schedeDelTitolo(
  ticker: string,
  instrumentType: string | null | undefined,
): SchedeStrumento {
  if (instrumentType !== "etf") return { fondamentali: true, news: true, analisti: true };
  return { fondamentali: false, news: ETF_SU_BENI.has(ticker.toUpperCase()), analisti: false };
}

/** Le pagine dei mercati: le news solo dove il prezzo e' quello di un bene. */
export function newsDelMercato(category: "index" | "commodity" | "crypto"): boolean {
  return category !== "index";
}
