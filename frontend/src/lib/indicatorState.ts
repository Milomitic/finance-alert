/* Stato iniziale degli indicatori del grafico */

import type { IndicatorState } from "@/components/stock/IndicatorToggles";
import { SERIE } from "@/lib/coloriGrafico";

// Default-on indicators: all three EMAs + Bollinger as overlays; RSI + MACD
// as separate panels. EMA20 enabled by default (was off): users want a
// short-term trend reference alongside the mid- and long-term ones, and
// the now-relocated indicator badges (right price scale instead of inline)
// mean an extra line doesn't visually crowd the candles.
export const DEFAULT_INDICATOR_STATE: IndicatorState = {
  ema20:  { visible: true,  color: SERIE.ema20, width: 1 },
  ema50:  { visible: true,  color: SERIE.ema50, width: 1 },
  ema200: { visible: true,  color: SERIE.ema200, width: 1 },
  bb:     { visible: true,  color: SERIE.bb, width: 1 },
  rsi:    { visible: true,  color: SERIE.rsi, width: 1 },
  macd:   { visible: true,  color: SERIE.macd, width: 1 },
};
