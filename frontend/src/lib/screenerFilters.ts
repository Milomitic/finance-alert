/* Filtri screener azzerati — il valore di partenza e quello del reset */

import type { FiltersState } from "@/components/stocks/StockFiltersCard";

/** The all-clear filter state. Single source of truth for "no filters":
 *  used by the Reset button AND as the base when applying a saved preset,
 *  so presets saved before new filter fields were added stay valid. */
export const EMPTY_FILTERS: FiltersState = {
  indexCodes: [], sectors: [], industries: [], exchanges: [], countries: [],
  riskTiers: [], excludeEtf: false, minScore: null, scoreMax: null,
  profitabilityMin: null, sustainabilityMin: null, growthMin: null,
  valueMin: null, sentimentMin: null,
  techMin: null, postures: [],
  marketCapMin: null, marketCapMax: null,
  rsiMin: null, rsiMax: null,
  aboveEma50: false, aboveEma200: false, near52wHigh: false, near52wLow: false,
  signalsWithinDays: null,
  priceMin: null, priceMax: null, changeMin: null, changeMax: null,
  volSpike: false, volRatioMin: null, volumeMin: null,
};
