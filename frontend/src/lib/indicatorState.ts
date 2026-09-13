/* Stato iniziale degli indicatori del grafico */

import type { IndicatorState } from "@/components/stock/IndicatorToggles";

// Default-on indicators: all three EMAs + Bollinger as overlays; RSI + MACD
// as separate panels. EMA20 enabled by default (was off): users want a
// short-term trend reference alongside the mid- and long-term ones, and
// the now-relocated indicator badges (right price scale instead of inline)
// mean an extra line doesn't visually crowd the candles.
export const DEFAULT_INDICATOR_STATE: IndicatorState = {
  ema20:  { visible: true,  color: "#a855f7", width: 1 },
  ema50:  { visible: true,  color: "#3b82f6", width: 1 },
  ema200: { visible: true,  color: "#f59e0b", width: 1 },
  bb:     { visible: true,  color: "#0ea5e9", width: 1 },
  rsi:    { visible: true,  color: "#7c3aed", width: 1 },
  macd:   { visible: true,  color: "#ef4444", width: 1 },
};
