/* Filtri screener azzerati — il valore di partenza e quello del reset */

import type { FiltersState } from "@/components/stocks/StockFiltersCard";

/** The all-clear filter state. Single source of truth for "no filters":
 *  used by the Reset button AND as the base when applying a saved preset,
 *  so presets saved before new filter fields were added stay valid. */
export const EMPTY_FILTERS: FiltersState = {
  indexCodes: [], sectors: [], industries: [], exchanges: [], countries: [],
  riskTiers: [], excludeEtf: false, datiCompleti: false, minScore: null, scoreMax: null,
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

/** Quanti filtri sono attivi, per area e in totale.
 *
 *  Un proprietario solo: la scheda dei filtri lo usa per i distintivi delle
 *  aree, e su telefono lo legge anche il pulsante «Filtri (N)» che apre il
 *  pannello (C-31). Due conteggi scritti a mano divergerebbero al primo
 *  filtro nuovo, e il pulsante direbbe un numero diverso dalla scheda. */
export function conteggiFiltri(state: FiltersState): {
  mercato: number;
  fondamentali: number;
  tecnici: number;
  prezzoVolume: number;
  /** I cinque pilastri, conteggio a parte dentro i fondamentali. */
  pilastri: number;
  totale: number;
} {
  const pilastri =
    (state.profitabilityMin != null ? 1 : 0) +
    (state.sustainabilityMin != null ? 1 : 0) +
    (state.growthMin != null ? 1 : 0) +
    (state.valueMin != null ? 1 : 0) +
    (state.sentimentMin != null ? 1 : 0);
  const mercato =
    state.indexCodes.length + state.sectors.length + state.industries.length +
    state.exchanges.length + state.countries.length +
    (state.excludeEtf ? 1 : 0);
  const fondamentali =
    (state.minScore != null ? 1 : 0) +
    (state.scoreMax != null ? 1 : 0) +
    state.riskTiers.length +
    pilastri +
    (state.marketCapMin != null ? 1 : 0) +
    (state.marketCapMax != null ? 1 : 0) +
    (state.datiCompleti ? 1 : 0);
  const tecnici =
    (state.techMin != null ? 1 : 0) +
    state.postures.length +
    (state.rsiMin != null ? 1 : 0) +
    (state.rsiMax != null ? 1 : 0) +
    (state.aboveEma50 ? 1 : 0) +
    (state.aboveEma200 ? 1 : 0) +
    (state.near52wHigh ? 1 : 0) +
    (state.near52wLow ? 1 : 0) +
    (state.signalsWithinDays != null ? 1 : 0);
  const prezzoVolume =
    (state.priceMin != null ? 1 : 0) +
    (state.priceMax != null ? 1 : 0) +
    (state.changeMin != null ? 1 : 0) +
    (state.changeMax != null ? 1 : 0) +
    (state.volSpike ? 1 : 0) +
    (state.volRatioMin != null ? 1 : 0) +
    (state.volumeMin != null ? 1 : 0);
  return { mercato, fondamentali, tecnici, prezzoVolume, pilastri, totale: mercato + fondamentali + tecnici + prezzoVolume };
}
