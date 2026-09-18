import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/* ─── Setups — what is FORMING, ahead of the signal ────────────────────
 *
 * A setup is a detector's conditions converging before its trigger fires:
 * "oversold, at support, hasn't turned yet". That is a fact about today, not
 * a forecast, which is why the payload carries no probability — see
 * `convenience` below.
 *
 * `staleTime: 5min`: setups are recomputed by the nightly scan, so polling
 * harder than the thing that produces them just burns requests.
 */

export interface Setup {
  id: number;
  ticker: string;
  name: string | null;
  currency?: string | null;
  detector: string;
  tone: string;
  /** 0..1 — share of the detector's gate chain already satisfied. A property
   *  of the DETECTOR: identical for every setup of the same detector at the
   *  same stage, so it cannot rank two of them against each other. */
  proximity: number;
  /** Distance from price to the trigger level, in ATR units — the per-SETUP
   *  counterpart to `proximity`. Near 0 means one normal session's move would
   *  fire it. Null when the trigger is not a price crossing (squeeze waits on
   *  volatility) or when the row predates the field. */
  distance_atr: number | null;
  /**
   * 0..100 ATTENTION score used for ordering. NOT a probability: setups make
   * no forecast and none of the engine's calibration applies to them. Never
   * render this next to, or in the style of, a signal's Probabilità.
   */
  convenience: number;
  /** What still has to happen for the signal to fire — the actionable part. */
  missing: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  annotations: {
    levels?: { label: string; price: number; kind: string }[];
    evaluation?: { bar_date: string; close: number; currency: string | null };
  } | null;
  /** Measured 0..1 factors behind the setup — evidence for the wait. */
  factors?: Record<string, number> | null;
  /** "active" | "converted" | "expired". Closed setups are kept, never
   *  deleted: an expired one is half of the conversion rate, and dropping
   *  them would leave only the successes on record. */
  status?: SetupStatus;
  resolved_at?: string | null;
  /** Perché l'episodio si è chiuso senza convertire: "stale" (le condizioni
   *  si sono sfaldate) | "aged" (tetto d'attesa) | "decayed" (sceso sotto la
   *  soglia di attenzione).
   *
   *  ⚠️ NULL su ogni episodio chiuso prima che la colonna esistesse, ed è il
   *  caso dominante: misurati in produzione il 2026-09-14, 322 scaduti senza
   *  ragione contro UNO con la ragione. Va reso come «non registrata», mai
   *  riempito con un'ipotesi. */
  closed_reason?: string | null;
  /** Days between first sighting and the signal firing — the warning this
   *  setup actually gave. Only set on converted rows. */
  lead_days?: number | null;
  converted_alert_id?: number | null;
  /** L'EVENTO che ha convertito il setup, fissato alla conversione: il
   *  segnale puntato sopra puo' aver cambiato data dopo. Null sugli storici
   *  dove non fu registrato e sui riconciliati. */
  converted_signal_date?: string | null;
  converted_price?: number | null;
  /** "live" | "legacy" | "reconciled". */
  conversion_source?: string | null;
  /** Giorni fra la barra d'apertura e la barra dell'evento. */
  bar_lead_days?: number | null;
  /** Esito dell'evento, dalla sua barra. `hit` null con la data valorizzata =
   *  nessun riferimento dell'universo quel giorno, non un insuccesso. */
  outcome_signal_date?: string | null;
  outcome_horizon_days?: number | null;
  outcome_mkt_neutral_hit?: number | null;
  outcome_mkt_neutral_excess_pct?: number | null;
  /** L'ultimo giorno in cui il setup puo ancora essere pendente.
   *
   *  ⚠️ E il TETTO da `first_seen_at`, non la scadenza scorrevole da
   *  `last_seen_at`: quella si sposta in avanti a ogni scansione finche le
   *  condizioni tengono, quindi e permanentemente a dieci giorni da oggi e
   *  non dice quando il setup si risolve. Misurato in produzione l'11
   *  settembre 2026 su 60 righe: scorrevole p50 9g e max 10g, tetto p50 14g
   *  e max 27g. Il proprietario della regola e `setup_service.pending_until`.
   *
   *  E un limite superiore, non una previsione: il setup puo convertire o
   *  decadere prima. */
  pending_until?: string | null;
  /** Prossima trimestrale del ticker, SOLO da cache: la lista non puo
   *  innescare una chiamata yfinance. Null = SCONOSCIUTO, che non e «nessuna
   *  trimestrale» — la stessa distinzione fra `—` e `0` applicata ai numeri.
   *
   *  Viaggia grezza, senza un booleano «dentro la finestra»: i consumatori
   *  hanno finestre diverse e la regola vive in `lib/earningsProximity.ts`. */
  next_earnings_date?: string | null;
}

export type SetupStatus = "active" | "converted" | "expired";
/** What the list is asking for. "closed" is both outcomes together, because
 *  the honest reading of the feature is the ratio between them. */
export type SetupStatusFilter = SetupStatus | "closed";

export interface SetupStats {
  /** Quale popolazione descrivono questi numeri: "all" = tutti i setup
   *  registrati nel database (decisione dell'utente, 2026-09-16). Prima era
   *  la sola shortlist, e la pagina diceva "nessun esito maturato" mentre fra
   *  tutti i convertiti gli esiti maturati erano 83. */
  scope?: string;
  active: number;
  /** Quanti degli attivi sono nella lista in questo momento. */
  active_shortlisted?: number;
  /** Chiusi per decadimento: fuori dal tasso di conversione, ma esiti. */
  decayed?: number;
  /** Chiusi da una conversione di verso OPPOSTO (setup rialzista chiuso da un
   *  segnale ribassista): fuori dal tasso, come i ritirati. */
  mislinked?: number;
  /** TUTTI gli episodi chiusi, qualunque la ragione: il totale della vista
   *  Esiti. ⚠️ Diverso da `closed`, che e' il denominatore del tasso. */
  closed_total?: number;
  /** Ritirati + collegamenti errati: chiusi, ma fuori dal tasso. */
  excluded_from_rate?: number;
  /** Chiusure storiche senza ragione registrata: nel tasso, lacuna visibile. */
  closed_without_reason?: number;
  /** Convertiti il cui esito non potra' MAI essere misurato (riconciliati, o
   *  storici il cui alert ha spostato la data oltre la conversione). Distinti
   *  da `converted_pending`, che un esito lo avranno. */
  converted_outcome_unavailable?: number;
  /** Anticipo sul MERCATO: barra d'apertura -> barra dell'evento, solo dove
   *  l'evento e' registrato. `median_lead_days` e' l'attesa fino alla
   *  RILEVAZIONE, cioe' l'orologio della scansione. */
  median_bar_lead_days?: number | null;
  bar_lead_days_n?: number;
  converted: number;
  expired: number;
  /** null = nothing has resolved yet. NOT the same as 0 — do not render it as 0%. */
  conversion_rate: number | null;
  /** Il termine di paragone del tasso: quota di titoli QUALSIASI su cui lo
   *  stesso segnale, negli stessi versi, scatta in una finestra da 28 giorni,
   *  pesata sui tipi di setup chiusi. `base_lift` = conversione / base. Null
   *  finche' non c'e' una finestra completa. */
  base_rate_pct?: number | null;
  base_lift?: number | null;
  base_windows?: number;
  base_window_days?: number;
  avg_lead_days: number | null;

  /** The two tabs, each with its own total. `total` is everything the feature
   *  has ever tracked: active + closed. */
  closed: number;
  total: number;
  /** ⚠️ Le tre voci SOMMANO ad `active`. Finché i toni erano due la terza
   *  non esisteva e la somma tornava per caso; da quando `squeeze_expansion`
   *  dichiara di non conoscere il verso, mostrare solo rialzisti e ribassisti
   *  lascerebbe un resto senza nome sotto un totale che non torna. */
  active_bull: number;
  active_bear: number;
  active_undetermined?: number;

  /** Did a converted setup go on to be RIGHT? Followed through the alert it
   *  became into the outcome warehouse, and labeled MARKET-NEUTRAL — beating
   *  the universe median in its own direction — never absolute, which would
   *  book the market's drift as the setup's merit.
   *
   *  `pending` is converted-but-unjudged: the horizon has not elapsed, or the
   *  trigger date had no universe benchmark. Neither is a loss, and folding
   *  them into `negative` would invent one. */
  converted_positive: number;
  converted_negative: number;
  converted_pending: number;

  /** The median and the range beside the mean: one number cannot say whether
   *  the warning was reliably a week or anywhere from a day to a month. */
  median_lead_days: number | null;
  lead_days_min: number | null;
  lead_days_max: number | null;

  /** How many converted setups have a market-neutral verdict, and the rate
   *  that follows from them. `converted_hit_rate` is a percentage to compare
   *  against 50, which is what a zero-skill setup scores. */
  converted_judged: number;
  converted_hit_rate: number | null;
  /** ⚠️ NOT the row count. Setups firing days apart share most of their
   *  forward window, so the honest denominator is the number of
   *  non-overlapping horizon-length windows. The point estimate uses every
   *  row; only the INTERVAL is charged the overlap. */
  converted_effective_n: number;
  converted_horizon_days: number | null;
  converted_ci_low: number | null;
  converted_ci_high: number | null;
  /** Thin evidence is flagged, never hidden: a rate the reader can distrust
   *  beats a blank they cannot interrogate. */
  converted_low_confidence: boolean;

  /** What a converted setup was WORTH, in percent.
   *
   *  Both series on purpose. `excess` is market-neutral and is the honest one;
   *  `return` is what the stock actually did. CLAUDE.md's worked example is a
   *  detector reading 54.0 absolute against 50.5 market-neutral, where most of
   *  the apparent edge was simply being long — one number alone lets that
   *  hide. The MEDIAN leads because forward returns are right-skewed. */
  median_excess_pct: number | null;
  mean_excess_pct: number | null;
  median_return_pct: number | null;
  mean_return_pct: number | null;

  by_detector: SetupDetectorStat[];
}

/** One setup family's report card. Every rate travels with the denominator
 *  that produced it: 50% on two resolved setups means nothing, and a tooltip
 *  is not where that belongs. */
export interface SetupDetectorStat {
  detector: string;
  converted: number;
  expired: number;
  resolved: number;
  conversion_rate: number | null;
  /** Quanto spesso lo stesso segnale scatta su un titolo qualsiasi in 28
   *  giorni, e quante volte piu' spesso dopo un setup di questo tipo. */
  base_rate_pct?: number | null;
  lift?: number | null;
  judged: number;
  positive: number;
  negative: number;
  hit_rate: number | null;
  effective_n: number;
  horizon_days: number | null;
  ci_low: number | null;
  ci_high: number | null;
  low_confidence: boolean;
  median_excess_pct: number | null;
}

export interface SetupsResponse {
  setups: Setup[];
  /** Righe che soddisfano i filtri, NON quelle rese. */
  total: number;
  has_more: boolean;
  /** Setup per detector nella POPOLAZIONE, ignorando il filtro detector: i
   *  chip devono restare tutti visibili dopo che se ne preme uno. */
  counts_by_detector: Record<string, number>;
  /** Setup per CONDIZIONE (chiave di `conditionKey`) nella popolazione
   *  filtrata: il numero che ogni gruppo mostra, invece delle righe in pagina. */
  counts_by_condition?: Record<string, number>;
  stats: SetupStats;
}

/** Righe per pagina. In produzione i setup attivi sono 1.415 dietro una
 *  risposta da 50: senza paginazione la lista non e' corta, e' TRONCATA. */
export const SETUP_PER_PAGINA = 50;

export function useSetups(
  tone?: "bull" | "bear",
  ticker?: string,
  status: SetupStatusFilter = "active",
  opts: { detector?: string | null; sort?: string; offset?: number } = {},
) {
  const { detector = null, sort, offset = 0 } = opts;
  return useQuery({
    queryKey: ["setups", tone ?? "all", ticker ?? "*", status,
               detector ?? "*", sort ?? "-", offset],
    queryFn: ({ signal }) => {
      const p = new URLSearchParams();
      if (tone) p.set("tone", tone);
      if (status !== "active") p.set("status", status);
      // Per-ticker asks the backend for THIS stock's setups, shortlisted or
      // not — see the API note. The global list stays capped.
      if (ticker) p.set("ticker", ticker);
      // ⚠️ Detector e ordinamento vanno al SERVER, non applicati alla pagina
      // ricevuta: filtrare lato client rende irraggiungibile un detector i cui
      // setup cadono tutti oltre la cinquantesima riga, e ordinare lato client
      // riordina cinquanta righe su millequattrocento.
      if (detector) p.set("detector", detector);
      if (sort) p.set("sort", sort);
      if (offset) p.set("offset", String(offset));
      p.set("limit", String(SETUP_PER_PAGINA));
      const qs = p.toString();
      return api<SetupsResponse>(`/api/setups${qs ? `?${qs}` : ""}`, { signal });
    },
    staleTime: 5 * 60 * 1000,
  });
}

/** Days a CLOSED setup spent waiting, first sighting to resolution. The live
 *  counterpart is `waitingDays`, which measures against now instead. */
export function resolvedAfterDays(setup: Setup): number | null {
  if (!setup.first_seen_at || !setup.resolved_at) return null;
  const a = new Date(setup.first_seen_at).getTime();
  const b = new Date(setup.resolved_at).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.max(0, Math.floor((b - a) / 86_400_000));
}

/** Days a setup has been waiting — the lead time it is currently offering. */
export function waitingDays(setup: Setup): number | null {
  if (!setup.first_seen_at) return null;
  const started = new Date(setup.first_seen_at).getTime();
  if (Number.isNaN(started)) return null;
  return Math.max(0, Math.floor((Date.now() - started) / 86_400_000));
}

/** Days since a scan last saw this setup's conditions hold (FA-066: «ultima
 *  osservazione» in front of the list).
 *
 *  ⚠️ Different from `waitingDays`, and the difference is the point: the wait
 *  says how much warning the setup is offering, this says whether anyone has
 *  LOOKED since. A setup not re-observed for a week is a claim about the past
 *  that the list presents as a fact about today. */
export function lastSeenDaysAgo(setup: Setup): number | null {
  if (!setup.last_seen_at) return null;
  const seen = new Date(setup.last_seen_at).getTime();
  if (Number.isNaN(seen)) return null;
  return Math.max(0, Math.floor((Date.now() - seen) / 86_400_000));
}

/** From here «visto Ng fa» is news rather than the scan's cadence. Four, as the
 *  «in ritardo» chip on alerts, and for the same measured reason: at one, a
 *  nightly scan across a weekend lit every row on Monday morning. */
export const LAST_SEEN_STALE_DAYS = 4;
