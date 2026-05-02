/**
 * Centralized explanations for acronyms / shorthand used in the dashboard.
 * Used as `title={ACRONYM_HELP.X}` for native HTML hover tooltips.
 */
export const ACRONYM_HELP = {
  SMA200: "% di stock con prezzo sopra la media mobile semplice a 200 giorni — segnale di trend rialzista a lungo termine",
  SMA50: "% di stock con prezzo sopra la media mobile semplice a 50 giorni — segnale di trend rialzista a medio termine",
  RSI_OVERSOLD: "Numero di stock in zona oversold (Relative Strength Index 14 periodi sotto 30) — possibile rimbalzo",
  RSI_OVERBOUGHT: "Numero di stock in zona overbought (Relative Strength Index 14 periodi sopra 70) — possibile correzione",
  AD_RATIO: "Rapporto Advancers / Decliners — stock in salita oggi vs in discesa",
  AVG_CHANGE: "Variazione percentuale media giornaliera (oggi vs chiusura precedente)",
  NEW_52W_HIGH: "Numero di stock che oggi raggiungono un nuovo massimo a 52 settimane",
  NEW_52W_LOW: "Numero di stock che oggi raggiungono un nuovo minimo a 52 settimane",
  VOL_SPIKE: "Numero di stock con volume oggi maggiore di 2× la media a 20 giorni — possibile catalyst",
  N_STOCKS: "Numero di stock monitorati nell'indice",
  UNIVERSE: "Numero totale di stock monitorati su tutti gli indici (e quanti hanno dati OHLCV sufficienti)",
  HI_LO_5PCT: "Numero di stock entro il 5% del massimo o minimo a 52 settimane",
  MOOD_BULLISH: "Bullish: oltre il 60% dei titoli sopra SMA200 e advancers > decliners",
  MOOD_BEARISH: "Bearish: massimo il 40% dei titoli sopra SMA200 e decliners > advancers",
  MOOD_NEUTRAL: "Neutral: regime intermedio — né nettamente rialzista né ribassista",
} as const;
