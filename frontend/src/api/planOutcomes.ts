import { api } from "./client";

/* ─── Il magazzino degli esiti di PIANO ───────────────────────────────────
 *
 * ⚠️ Non e' la colonna «Esito» della tabella dei segnali, e confonderle
 * produce due numeri diversi sullo stesso schermo:
 *
 *   signal_outcomes   la DIREZIONE ha pagato a orizzonte fisso? (quella colonna)
 *   plan_outcomes     il PIANO si sarebbe chiuso in guadagno?   (questo)
 *
 * Un segnale puo' prendere il target in tre sedute e finire l'orizzonte sotto
 * il prezzo d'ingresso: primo «azzeccato», secondo «mancato». Sono due
 * domande, non due misure della stessa. */

export interface PlanOutcomeRow {
  alert_id: number;
  ticker: string;
  name: string | null;
  detector: string;
  tone: string;
  signal_date: string;
  /** La barra da cui parte la gara: la PRIMA emissione dell'alert. Puo'
   *  seguire `signal_date` di qualche seduta — e' la cadenza della scansione. */
  entry_date: string;
  entry: number;
  stop: number;
  tp1: number;
  tp2: number | null;
  /** La distanza di rischio in prezzo: 1R. */
  r: number;
  horizon_days: number;
  /** tp1 | stop | ambigua | scaduto */
  esito: string;
  resolved_date: string;
  bars_to_outcome: number;
  r_multiple: number;
  mae_r: number;
  mfe_r: number;
  tp2_reached: boolean;
  /** Primo tocco di ogni gamba NELL'ORIZZONTE, anche dopo la chiusura. */
  stop_hit_date: string | null;
  tp1_hit_date: string | null;
  tp2_hit_date: string | null;
}

export interface PlanOutcomeSummary {
  n: number;
  effective_n: number;
  horizon_days: number;
  expectancy_r: number;
  expectancy_ci: number[] | null;
  verdict: string;
  win_rate: number;
  esiti: Record<string, number>;
  stop_too_tight: number;
  mae_r_on_wins: number | null;
  mfe_r_on_losses: number | null;
  median_bars: number | null;
  low_confidence: boolean;
}

export interface PlanOutcomeList {
  items: PlanOutcomeRow[];
  total: number;
  has_more: boolean;
  counts_by_detector: Record<string, number>;
  /** `null` quando il filtro non seleziona niente: zero righe non hanno
   *  un'attesa, e 0,00 R sarebbe un'affermazione invece di un'assenza. */
  summary: PlanOutcomeSummary | null;
}

export interface PlanOutcomeParams {
  esito?: string;
  detector?: string;
  tone?: string;
  ticker?: string;
  limit?: number;
  offset?: number;
  /** Una chiave di `ORDINAMENTI_ESITI` (backend) / `OrdineEsiti` (qui). */
  sort_by?: string;
  sort_dir?: "asc" | "desc";
}

export const planOutcomes = {
  list(p: PlanOutcomeParams, signal?: AbortSignal): Promise<PlanOutcomeList> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(p)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const coda = qs.toString();
    return api<PlanOutcomeList>(`/api/alerts/plan-outcomes${coda ? `?${coda}` : ""}`, { signal });
  },
};
