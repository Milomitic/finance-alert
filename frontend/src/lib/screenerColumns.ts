/* Definizione delle colonne dello screener. Dato, non componente */

export const SCREENER_COLS = [
  { id: "exchange",       label: "Exchange" },
  { id: "settore",        label: "Settore" },
  { id: "industry",       label: "Industry" },
  { id: "prezzo",         label: "Prezzo" },
  { id: "market_cap",     label: "Mkt Cap" },
  { id: "delta_pct",      label: "Δ%" },
  { id: "rsi",            label: "RSI" },
  { id: "vol_ratio",      label: "Vol×" },
  { id: "volume",         label: "Volume" },
  { id: "pct_from_high",  label: "% da max 52w" },
  { id: "vs_ema200",      label: "vs EMA200" },
  { id: "score",          label: "Score" },
  { id: "profitability",  label: "Profittabilità" },
  { id: "sustainability", label: "Sostenibilità" },
  { id: "growth",         label: "Crescita" },
  { id: "value",          label: "Valore" },
  { id: "sentiment",      label: "Sentiment" },
  { id: "tech_composite",  label: "Tecnico" },
  { id: "divario",         label: "Divario" },
  { id: "tech_trend",      label: "T-Trend" },
  { id: "tech_momentum",   label: "T-Mom" },
  { id: "tech_structure",  label: "T-Strut" },
  { id: "tech_volume",     label: "T-Vol" },
  { id: "tech_rel_strength", label: "T-RS" },
  { id: "risk",           label: "Risk" },
] as const;

/** Le colonne nascoste di default (C-27): 24 colonne erano ~2.800px su uno
 *  schermo da 1440, e il ticker usciva scorrendo. Restano dieci: settore,
 *  prezzo, capitalizzazione, variazione, RSI, volume relativo, le due lenti,
 *  il divario e il rischio. Le altre si accendono dal menu Colonne. */
export const SCREENER_NASCOSTE_DI_DEFAULT = [
  "exchange", "industry", "volume", "pct_from_high", "vs_ema200",
  "profitability", "sustainability", "growth", "value", "sentiment",
  "tech_trend", "tech_momentum", "tech_structure", "tech_volume", "tech_rel_strength",
] as const;
