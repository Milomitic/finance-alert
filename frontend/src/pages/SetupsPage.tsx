import { ChevronDown, Hourglass, Target, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { SetupConditionGroup } from "@/components/setups/SetupConditionGroup";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { SetupDetailDialog } from "@/components/setups/SetupDetailDialog";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import SetupDetectorStats from "@/components/setups/SetupDetectorStats";
import { SetupOutcomeList } from "@/components/setups/SetupOutcomeList";
import { useAlert } from "@/hooks/useAlerts";
import { SETUP_PER_PAGINA, useSetups, type Setup, type SetupStats } from "@/hooks/useSetups";
import { detectorLabel, groupByCondition, type SetupSortKey } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";
import { MetricStrip, type MetricTileProps } from "@/components/ui/metric-tile";

/* ─── Setups — cosa si sta formando, PRIMA del segnale ─────────────────────
 *
 * Design constraint that drives everything here: this page must not read like
 * the Segnali page. A setup is a wait, not a call. So:
 *
 *   - no Probabilità anywhere, because setups have none;
 *   - `convenience` is labelled "priorità" and explained as ordering, never
 *     shown as a percentage next to a price;
 *   - the biggest text on each row is "cosa manca" — the thing you act on;
 *   - the wait is stated in days, because lead time is the whole product.
 *
 * If this page ever starts looking like a list of predictions, the honesty
 * the backend was built around has leaked away at the last step.
 */

/** The feature's own report card. Shown up front on purpose: setups make no
 *  market claim, so the only honest thing to advertise is whether they do
 *  what they say — convert, and with how much warning. */
/** Below this many RESOLVED setups the conversion rate is shown as a raw
 *  fraction rather than a percentage — see the tile comment. */
const MIN_RATE_N = 20;

/* ─── Due viste, nell'URL ──────────────────────────────────────────────────
 *
 * FA-066 aveva spostato le misure in una terza vista, «Misurazione». Il
 * 2026-09-16 l'utente le ha volute di nuovo SOPRA la lista, con le metriche
 * che contano in evidenza: quattro tessere principali (tasso, efficacia,
 * rendimento, anticipo), le altre compatte, e la tabella per tipo di setup
 * chiusa di default. Un vecchio link a ?vista=misurazione apre la lista, che
 * ora le contiene.
 *
 * Nell'URL, come Diagnostica: il dettaglio titolo deve poter mandare qui una
 * lista gia' filtrata (`?ticker=`), e un link a una vista resta condivisibile. */
const VISTE = [
  { id: "formazione", label: "In formazione" },
  { id: "esiti", label: "Esiti" },
] as const;

type VistaId = (typeof VISTE)[number]["id"];

/** La vista chiesta dall'URL. Un valore sconosciuto — un segnalibro vecchio,
 *  un refuso — apre la lista invece di una pagina vuota. */
function vistaDa(raw: string | null): VistaId {
  return VISTE.some((v) => v.id === raw) ? (raw as VistaId) : "formazione";
}

function StatsStrip({ stats }: { stats: SetupStats }) {
  // Derived, not read from `stats.closed`: the same number arriving twice
  // can disagree, and the rate below is judged against it.
  const resolved = stats.converted + stats.expired;
  const judged = stats.converted_positive + stats.converted_negative;

  const tiles: {
    label: string;
    value: string;
    /** Cifra o intervallo che accompagna il valore: resta SEMPRE a schermo.
     *  Bande di confidenza, minimi/massimi, "non concludente" — nasconderli
     *  dietro un tocco significherebbe mostrare un tasso senza il campione
     *  che lo regge, che e' esattamente cio' che questo repo non fa. */
    hint?: string;
    /** Spiegazione in prosa: non e' un dato, si legge una volta, e su un
     *  telefono costava due righe per piastrella. Va nel popup. */
    note?: string;
    tone?: "ok" | "bad" | null;
    /** In evidenza: le metriche che rispondono a «la funzione funziona?». */
    primary?: boolean;
  }[] = [
    {
      label: "In formazione",
      value: String(stats.active),
      // ⚠️ Il terzo termine compare solo se c'è: su un catalogo di soli
      // setup direzionali una coda «· 0 senza direzione» sarebbe rumore, ma
      // ometterlo quando ESISTE lascerebbe un totale che non torna.
      hint:
        `${stats.active_bull} rialzisti · ${stats.active_bear} ribassisti` +
        (stats.active_undetermined
          ? ` · ${stats.active_undetermined} senza direzione`
          : ""),
    },
    {
      label: "Esiti",
      value: String(resolved),
      // I ritirati completano il conto: convertiti + scaduti + ritirati sono
      // tutti i setup chiusi, cioe' il totale della vista Esiti.
      hint:
        `${stats.converted} convertiti · ${stats.expired} scaduti` +
        (stats.decayed ? ` · ${stats.decayed} ritirati (fuori dal tasso)` : ""),
    },
    {
      label: "Tasso conversione",
      primary: true,
      // Three states, not two.
      //
      // null means "nothing has resolved yet" — rendering it as 0% would read
      // as "setups never work", which is a different claim entirely.
      //
      // A resolved count below MIN_RATE_N gets the raw FRACTION as the
      // headline instead of a percentage. Same information, minus a claim the
      // sample cannot carry: at 6-out-of-6 the Wilson 95% lower bound is ~61%,
      // so "100%" in 2xl bold is compatible with a true rate near a coin flip.
      value:
        stats.conversion_rate === null
          ? "—"
          : resolved < MIN_RATE_N
            ? `${stats.converted}/${resolved}`
            : `${Math.round(stats.conversion_rate * 100)}%`,
      hint:
        stats.conversion_rate === null
          ? "nessuno ancora risolto"
          : resolved < MIN_RATE_N
            ? `troppo pochi per un tasso (servono ${MIN_RATE_N})`
            : `${stats.converted} su ${resolved}`,
    },
    {
      // The question the page could not answer: a setup converted — and then?
      // Counts, never a percentage. The sample is small, the windows overlap,
      // and a rate here would claim more than the measurement supports.
      label: "Convertiti: esito",
      value: judged === 0 ? "—" : `${stats.converted_positive} / ${stats.converted_negative}`,
      hint:
        judged === 0
          ? "nessun esito ancora maturato"
          : `positivi / negativi rispetto alla mediana dell'universo${
              stats.converted_pending > 0 ? ` · ${stats.converted_pending} in attesa` : ""
            }`,
      tone:
        judged === 0
          ? null
          : stats.converted_positive > stats.converted_negative
            ? "ok"
            : stats.converted_negative > stats.converted_positive
              ? "bad"
              : null,
    },
    {
      // The rate the counts above imply, put where a person compares it: 50 is
      // what a setup with no skill scores. The interval comes with it, sized
      // on non-overlapping windows rather than rows, because setups firing
      // days apart share most of their forward window and a row-count band
      // would look far narrower than the evidence allows.
      label: "Efficacia",
      primary: true,
      value:
        stats.converted_hit_rate === null
          ? "—"
          : `${Math.round(stats.converted_hit_rate)}%`,
      hint:
        stats.converted_hit_rate === null
          ? "serve almeno un esito maturo"
          : `${stats.converted_ci_low?.toFixed(0)}–${stats.converted_ci_high?.toFixed(0)}% su ${
              stats.converted_effective_n
            } finestre indipendenti${stats.converted_low_confidence ? " · non concludente" : ""}`,
      tone:
        stats.converted_hit_rate === null ||
        (stats.converted_ci_low !== null &&
          stats.converted_ci_high !== null &&
          stats.converted_ci_low <= 50 &&
          stats.converted_ci_high >= 50)
          ? // A band straddling 50 has said nothing, so it gets no colour.
            null
          : stats.converted_hit_rate > 50
            ? "ok"
            : "bad",
    },
    {
      // What the setup was WORTH, not just whether it was right. Median, not
      // mean: forward returns are right-skewed and one large winner would
      // describe a typical setup that does not exist. The absolute return sits
      // in the hint beside it on purpose — when the two diverge, the gap IS
      // the market drift the setup collected for free.
      label: "Rendimento mediano",
      primary: true,
      value:
        stats.median_excess_pct === null
          ? "—"
          : `${stats.median_excess_pct > 0 ? "+" : ""}${stats.median_excess_pct.toFixed(1)}%`,
      hint:
        stats.median_excess_pct === null
          ? "eccesso sulla mediana dell'universo"
          : `market-neutral · assoluto ${
              stats.median_return_pct === null
                ? "n/d"
                : `${stats.median_return_pct > 0 ? "+" : ""}${stats.median_return_pct.toFixed(1)}%`
            }`,
      tone:
        stats.median_excess_pct === null
          ? null
          : stats.median_excess_pct > 0
            ? "ok"
            : stats.median_excess_pct < 0
              ? "bad"
              : null,
    },
    {
      label: "Anticipo mediano",
      primary: true,
      value: stats.median_lead_days === null ? "—" : `${stats.median_lead_days}g`,
      hint:
        stats.lead_days_min === null
          ? "giorni di preavviso reali"
          : `da ${stats.lead_days_min}g a ${stats.lead_days_max}g · media ${stats.avg_lead_days}g`,
    },
    {
      label: "Setup registrati",
      value: String(stats.total),
      hint:
        stats.active_shortlisted != null
          ? `${stats.active_shortlisted} attivi mostrati in lista ora`
          : undefined,
      note: "Tutti i setup registrati nel database, attivi e chiusi. Ogni misura di questa pagina li considera tutti, non solo quelli in lista.",
    },
  ];

  // Le principali prima, nell'ordine in cui compaiono; le altre compatte sotto.
  const ordinate: MetricTileProps[] = [
    ...tiles.filter((x) => x.primary),
    ...tiles.filter((x) => !x.primary),
  ];
  return <MetricStrip tiles={ordinate} />;
}

/** La tabella per tipo di setup, chiusa di default: e' il dettaglio, e aperta
 *  spingerebbe la lista sotto la piega. Montata solo quando aperta. */
function DettaglioPerTipo({ rows }: { rows: SetupStats["by_detector"] }) {
  const [aperto, setAperto] = useState(false);
  if (!rows || rows.length === 0) return null;
  return (
    <div>
      <button
        type="button"
        aria-expanded={aperto}
        onClick={() => setAperto((a) => !a)}
        className="inline-flex min-h-[36px] items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", aperto && "rotate-180")} aria-hidden />
        {aperto ? "Nascondi" : "Mostra"} le misure per tipo di setup
      </button>
      {aperto && <SetupDetectorStats rows={rows} />}
    </div>
  );
}

export default function SetupsPage() {
  const [tone, setTone] = useState<"bull" | "bear" | undefined>(undefined);
  const [detector, setDetector] = useState<string | null>(null);
  const [sort, setSort] = useState<SetupSortKey>("convenience");
  // The setup whose detail panel is open. Named `openSetup`, not `open`:
  // a bare `open` resolves to `window.open` when the declaration is missing,
  // and TypeScript then reports a type error somewhere else entirely.
  const [openSetup, setOpenSetup] = useState<Setup | null>(null);
  // "In formazione" vs "Esiti". The closed rows are the only record of
  // whether the feature works — conversion rate and lead time both come from
  // them — and until now the page could not show a single one.
  const [params, setParams] = useSearchParams();
  const vista = vistaDa(params.get("vista"));
  const ticker = params.get("ticker")?.trim().toUpperCase() || undefined;
  const view: "active" | "closed" = vista === "esiti" ? "closed" : "active";
  // Il segnale in cui un setup e scattato. Per id, non per ricerca nella lista
  // alert: quella e paginata, e un setto convertito ad agosto non e in nessuna
  // pagina che si stia guardando.
  const [signalId, setSignalId] = useState<number | null>(null);
  const signal = useAlert(signalId);
  // ⚠️ La pagina corrente. Ogni controllo che cambia il PERIMETRO la riporta a
  // zero (vedi `cambia`): restare alla pagina 4 dopo aver cambiato filtro
  // mostrerebbe una fetta di mezzo di una popolazione diversa, senza che niente
  // lo dica.
  const [offset, setOffset] = useState(0);
  const q = useSetups(tone, ticker, view, { detector, sort, offset });

  const all = useMemo(() => q.data?.setups ?? [], [q.data?.setups]);
  // ⚠️ I conteggi vengono dal SERVER e descrivono la popolazione. Prima erano
  // `detectorCounts(all)`, cioe' un conteggio delle righe RICEVUTE: un numero
  // che cambia con la dimensione della pagina non e' un conteggio, e un
  // detector i cui setup cadevano tutti oltre la cinquantesima riga non aveva
  // nemmeno un chip da premere.
  const detectors = useMemo(() => {
    const c = q.data?.counts_by_detector ?? {};
    return Object.entries(c)
      .map(([d, count]) => ({ detector: d, count }))
      .sort((a, b) => b.count - a.count || a.detector.localeCompare(b.detector));
  }, [q.data?.counts_by_detector]);
  // Il filtro detector e l'ordinamento sono gia' stati applicati dal server:
  // qui resta solo il RAGGRUPPAMENTO per condizione, che e' una scelta di
  // presentazione e non un perimetro.
  const groups = useMemo(() => groupByCondition(all, sort), [all, sort]);
  const totale = q.data?.total ?? all.length;
  const perCondizione = q.data?.counts_by_condition;
  const nCondizioni = perCondizione ? Object.keys(perCondizione).length : groups.length;
  /** Cambia un controllo che ridefinisce il perimetro, e torna alla prima
   *  pagina. In render, non in un effect: `set-state-in-effect` e' gated. */
  const cambia = <T,>(set: (v: T) => void) => (v: T) => { set(v); setOffset(0); };
  /** Lo stesso, per cio' che vive nell'URL. `replace`: cambiare vista non e'
   *  navigare, e «indietro» deve uscire dalla pagina. */
  const cambiaUrl = (chiave: "vista" | "ticker", valore: string | null) => {
    const p = new URLSearchParams(params);
    if (valore === null || (chiave === "vista" && valore === "formazione")) p.delete(chiave);
    else p.set(chiave, valore);
    setParams(p, { replace: true });
    setOffset(0);
  };

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-3">
          <Hourglass className="h-7 w-7 text-muted-foreground" aria-hidden />
          In formazione
        </h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Condizioni che stanno convergendo, <strong>prima</strong> che il segnale scatti —
          così hai il tempo di preparare una posizione. Non sono previsioni: descrivono
          lo stato di oggi e dicono cosa manca perché il segnale si attivi.
        </p>
      </div>

      {/* Bottoni con `aria-pressed`, non tab: non c'e' un tabpanel da
          promettere (CLAUDE.md, «Recenti / Storico»). */}
      <div className="flex flex-wrap items-center gap-2">
        <div
          role="group"
          aria-label="Vista"
          className="inline-flex rounded-md border overflow-hidden text-xs font-semibold"
        >
          {VISTE.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={vista === v.id}
              onClick={() => cambiaUrl("vista", v.id)}
              className={cn(
                "min-h-[36px] px-3 transition-colors",
                vista === v.id
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/40",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
        {ticker && (
          <button
            type="button"
            onClick={() => cambiaUrl("ticker", null)}
            aria-label={`Solo ${ticker}, togli il filtro`}
            className="inline-flex min-h-[36px] items-center gap-1 rounded-md border px-3 text-xs font-semibold hover:bg-accent"
          >
            Solo {ticker}
            <X className="h-3 w-3" aria-hidden />
          </button>
        )}
      </div>

      {/* Le misure SOPRA la lista (richiesta dell'utente, 2026-09-16), con le
          metriche principali in evidenza. `conversion_stats` non guarda i
          filtri della lista: le misure sono di tutti i setup del database, e
          la pagina lo dice. In errore non si ripete il messaggio: la lista
          sotto mostra gia' il suo. */}
      {q.isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} rows={2} className="h-[96px]" />
          ))}
        </div>
      ) : q.data ? (
        <section aria-label="Misure dei setup" className="space-y-2">
          <StatsStrip stats={q.data.stats} />
          <p className="text-xs text-muted-foreground">
            Le misure contano <strong>tutti i setup registrati nel database</strong>{" "}
            ({q.data.stats.total.toLocaleString("it-IT")}), attivi e chiusi, compresi
            quelli fuori dalla lista e dalla pagina corrente
            {ticker ? <>, non solo <strong>{ticker}</strong></> : null}.
          </p>
          <DettaglioPerTipo rows={q.data.stats.by_detector} />
        </section>
      ) : null}

      {/* Three controls became eight. The page had exactly one axis — tone —
          which meant no way to ask "show me only the squeezes" or "who has
          been waiting longest", on the longest page in the app. */}
      <div className="flex flex-wrap items-center gap-2">
        {([undefined, "bull", "bear"] as const).map((t) => (
          <button
            key={t ?? "all"}
            type="button"
            onClick={() => cambia(setTone)(t)}
            className={cn(
              "min-h-[36px] px-3 rounded-md border text-xs font-semibold transition-colors",
              tone === t ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            {t === undefined ? "Tutti" : t === "bull" ? "Rialzisti" : "Ribassisti"}
          </button>
        ))}

        {detectors.length > 1 && (
          <>
            <span className="h-5 w-px bg-border mx-1" aria-hidden />
            <button
              type="button"
              onClick={() => cambia(setDetector)(null)}
              className={cn(
                "min-h-[36px] px-3 rounded-md border text-xs font-semibold transition-colors",
                detector === null ? "bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
            >
              Ogni condizione
            </button>
            {detectors.map(({ detector: d, count }) => (
              <button
                key={d}
                type="button"
                onClick={() => cambia(setDetector)(d)}
                className={cn(
                  "min-h-[36px] px-3 rounded-md border text-xs font-semibold transition-colors",
                  detector === d ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                )}
              >
                {detectorLabel(d)}{" "}
                <span className="tabular-nums opacity-70">{count}</span>
              </button>
            ))}
          </>
        )}

        <span className="h-5 w-px bg-border mx-1" aria-hidden />
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          Ordina
          <select
            value={sort}
            onChange={(e) => cambia(setSort)(e.target.value as SetupSortKey)}
            className="min-h-[36px] rounded-md border bg-background px-2 text-xs font-semibold"
          >
            <option value="convenience">Priorità</option>
            <option value="distance">Più vicini all'innesco</option>
            <option value="waiting">Attesa più lunga</option>
            <option value="ticker">Titolo (A-Z)</option>
          </select>
        </label>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between gap-3 flex-wrap">
          <SectionTitle
            icon={Target}
            /* Il numero nel titolo e' la POPOLAZIONE filtrata dal server,
               mai le righe in pagina: diceva "50 setup chiusi" perche' 50
               erano le righe rese, su 795. */
            label={
              view === "closed"
                ? `Esiti — ${totale.toLocaleString("it-IT")} setup chiusi`
                : totale > 0
                  ? `Setup attivi — ${totale.toLocaleString("it-IT")} in ${nCondizioni} condizioni`
                  : "Setup attivi"
            }
          />
        </div>
        {q.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <CardSkeleton key={i} rows={2} className="h-[110px]" />
            ))}
          </div>
        ) : q.isError ? (
          <QueryError message="dei setup" onRetry={q.refetch} isRetrying={q.isFetching} />
        ) : view === "active" && (!q.data || q.data.setups.length === 0) ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Nessun setup in formazione al momento. Vengono ricalcolati a ogni scan —
              se hai appena aggiunto la funzione, i primi compaiono dopo la prossima
              scansione notturna.
            </CardContent>
          </Card>
        ) : view === "closed" ? (
          <SetupOutcomeList
            setups={all}
            onOpenSignal={setSignalId}
            pendingAlertId={signal.isFetching ? signalId : null}
          />
        ) : (
          <div className="space-y-3">
            {groups.map((g) => (
              <SetupConditionGroup
                key={g.key}
                group={g}
                onOpen={setOpenSetup}
                populationCount={perCondizione?.[g.key]}
              />
            ))}
          </div>
        )}
        {!q.isLoading && !q.isError && totale > SETUP_PER_PAGINA && (
          /* ⚠️ Senza questa riga una lista troncata e' indistinguibile da una
             completa: in produzione 1.415 setup attivi dietro una risposta da
             50, e niente che lo dicesse. Il totale e' quello FILTRATO, cioe'
             la popolazione fra cui si sta guardando. */
          <div className="flex flex-wrap items-center justify-between gap-2 pt-3 text-xs text-muted-foreground">
            <span className="tabular-nums">
              {offset + 1}–{offset + all.length} di {totale}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="min-h-[36px] rounded-md border px-3 font-semibold hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
                onClick={() => setOffset((o) => Math.max(0, o - SETUP_PER_PAGINA))}
                disabled={offset === 0 || q.isFetching}
              >
                Precedenti
              </button>
              <button
                type="button"
                className="min-h-[36px] rounded-md border px-3 font-semibold hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
                onClick={() => setOffset((o) => o + SETUP_PER_PAGINA)}
                disabled={!q.data?.has_more || q.isFetching}
              >
                Successivi
              </button>
            </div>
          </div>
        )}
      </div>
      <SetupDetailDialog setup={openSetup} onClose={() => setOpenSetup(null)} />
      {/* Il terzo anello: setup → segnale → posizione. Lo stesso dialogo che
          la pagina Segnali e la pagina Posizioni aprono, e che contiene
          `TrackTradeForm`, cioe il modo in cui un segnale diventa posizione. */}
      <AlertDetailDialog
        alert={signal.data ?? null}
        onClose={() => setSignalId(null)}
      />
    </div>
  );
}
