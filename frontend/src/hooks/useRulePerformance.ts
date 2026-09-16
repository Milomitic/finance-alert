import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/* Calibrazione realizzata, dal replay di ohlcv_daily.
 *
 * `useRulePerformance` viveva qui e alimentava la tabella di efficacia in
 * Impostazioni. E' stata rimossa: riportava il solo hit ASSOLUTO su finestre
 * 1/5/20 giorni, cioe' beta incluso, e trattava ogni riga come
 * un'osservazione indipendente. Quella tabella ora legge il magazzino degli
 * esiti — vedi components/settings/SignalEffectiveness.tsx.
 */

export interface CalibrationBucket {
  label: string;
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
  median_pct: number | null;
}

export interface CalibrationSeedCell {
  count: number;
  hit_rate: number | null;
  mean_pct: number | null;
}
export interface CalibrationSeed {
  window: number;
  by_horizon: Record<string, CalibrationSeedCell>;
  by_confidence: Record<string, CalibrationSeedCell>;
  by_confidence_horizon: Record<string, CalibrationSeedCell>;
  by_nature: Record<string, CalibrationSeedCell>;
}
export interface Calibration {
  /** null = tutto il magazzino degli esiti. */
  days: number | null;
  /** Orizzonte effettivo: uno di quelli del magazzino (5, 21, 63). */
  window: number;
  /** Tutti gli esiti maturati a quell'orizzonte: la popolazione. I bucket
   *  possono sommare a meno (un esito senza Forza resta un esito). */
  total: number;
  by_confidence: CalibrationBucket[];
  by_nature: CalibrationBucket[];
  by_horizon: CalibrationBucket[];
  /** Backtest-derived reference (populates the panel immediately while live
   *  calibration matures). Null if the seed file is absent. */
  backtest_seed: CalibrationSeed | null;
}

export interface CalibrationCurve {
  window?: number;
  by_horizon?: Record<string, CalibrationSeedCell>;
  by_confidence?: Record<string, CalibrationSeedCell>;
  by_confidence_horizon?: Record<string, CalibrationSeedCell>;
  by_nature?: Record<string, CalibrationSeedCell>;
}

/** Hit market-neutral + rendimento per fascia di Forza, natura e orizzonte,
 *  letti da TUTTO il magazzino degli esiti (nessun filtro sugli archiviati). */
export function useCalibration(horizon = 21) {
  return useQuery({
    queryKey: ["calibration", horizon],
    queryFn: ({ signal }) =>
      api<Calibration>(`/api/rule-performance/calibration?window=${horizon}`, { signal }),
    staleTime: 5 * 60 * 1000,
  });
}
