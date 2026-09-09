import { Hourglass, Target } from "lucide-react";
import { useMemo, useState } from "react";

import { SetupConditionGroup } from "@/components/setups/SetupConditionGroup";
import { SetupDetailDialog } from "@/components/setups/SetupDetailDialog";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import SetupDetectorStats from "@/components/setups/SetupDetectorStats";
import { SetupOutcomeList } from "@/components/setups/SetupOutcomeList";
import { useSetups, type Setup, type SetupStats } from "@/hooks/useSetups";
import { detectorCounts, detectorLabel, groupByCondition, type SetupSortKey } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

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

function StatsStrip({ stats }: { stats: SetupStats }) {
  // Derived, not read from `stats.closed`: the same number arriving twice
  // can disagree, and the rate below is judged against it.
  const resolved = stats.converted + stats.expired;
  const judged = stats.converted_positive + stats.converted_negative;

  const tiles: {
    label: string;
    value: string;
    hint?: string;
    tone?: "ok" | "bad" | null;
  }[] = [
    {
      label: "In formazione",
      value: String(stats.active),
      hint: `${stats.active_bull} rialzisti · ${stats.active_bear} ribassisti`,
    },
    {
      label: "Esiti",
      value: String(resolved),
      hint: `${stats.converted} convertiti · ${stats.expired} scaduti`,
    },
    {
      label: "Tasso conversione",
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
      value: stats.median_lead_days === null ? "—" : `${stats.median_lead_days}g`,
      hint:
        stats.lead_days_min === null
          ? "giorni di preavviso reali"
          : `da ${stats.lead_days_min}g a ${stats.lead_days_max}g · media ${stats.avg_lead_days}g`,
    },
    {
      label: "Totale in lista",
      value: String(stats.total),
      // Non è la tabella intera. `conversion_stats` conta solo i setup
      // effettivamente SURFACED: uno che l'utente non ha mai visto non gli ha
      // promesso niente, quindi contarne l'esito misurerebbe qualcosa che la
      // funzione non ha mai offerto. In produzione sono 71 su ~1.800 righe.
      hint: "setup effettivamente mostrati in lista, non l'intera tabella",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 [&>*]:min-w-0">
      {tiles.map((t) => (
        <Card key={t.label}>
          <CardContent className="p-3">
            <div className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-mono truncate">
              {t.label}
            </div>
            <div
              className={cn(
                "text-2xl font-bold tabular-nums leading-tight mt-0.5",
                t.tone === "ok" && "text-emerald-800 dark:text-emerald-400",
                t.tone === "bad" && "text-rose-700 dark:text-rose-400",
              )}
            >
              {t.value}
            </div>
            {t.hint && <div className="text-xs text-muted-foreground mt-0.5">{t.hint}</div>}
          </CardContent>
        </Card>
      ))}
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
  const [view, setView] = useState<"active" | "closed">("active");
  const q = useSetups(tone, undefined, view);

  const all = useMemo(() => q.data?.setups ?? [], [q.data?.setups]);
  const detectors = useMemo(() => detectorCounts(all), [all]);
  const groups = useMemo(
    () => groupByCondition(detector ? all.filter((s) => s.detector === detector) : all, sort),
    [all, detector, sort],
  );

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

      {q.data && <StatsStrip stats={q.data.stats} />}

      {/* Above the tables on BOTH tabs, deliberately. The strip says whether
          the feature works; this says which setup families do, and that is the
          question a person carries into either list. It is the same data on
          both, because a family's record does not change depending on which
          tab you are reading. */}
      {q.data && <SetupDetectorStats rows={q.data.stats.by_detector} />}

      {/* Three controls became eight. The page had exactly one axis — tone —
          which meant no way to ask "show me only the squeezes" or "who has
          been waiting longest", on the longest page in the app. */}
      <div className="flex flex-wrap items-center gap-2">
        {([undefined, "bull", "bear"] as const).map((t) => (
          <button
            key={t ?? "all"}
            type="button"
            onClick={() => setTone(t)}
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
              onClick={() => setDetector(null)}
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
                onClick={() => setDetector(d)}
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
            onChange={(e) => setSort(e.target.value as SetupSortKey)}
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
            label={
              view === "closed"
                ? `Esiti — ${all.length} setup chiusi`
                : groups.length > 0
                  ? `Setup attivi — ${groups.reduce((n, g) => n + g.setups.length, 0)} in ${groups.length} condizioni`
                  : "Setup attivi"
            }
          />
          <div className="inline-flex rounded-md border overflow-hidden text-xs font-semibold">
            {(["active", "closed"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-pressed={view === v}
                className={cn(
                  "px-3 py-1.5 transition-colors",
                  view === v ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/40",
                )}
              >
                {v === "active" ? "In formazione" : "Esiti"}
              </button>
            ))}
          </div>
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
          <SetupOutcomeList setups={all} />
        ) : (
          <div className="space-y-3">
            {groups.map((g) => (
              <SetupConditionGroup key={g.key} group={g} onOpen={setOpenSetup} />
            ))}
          </div>
        )}
      </div>
      <SetupDetailDialog setup={openSetup} onClose={() => setOpenSetup(null)} />
    </div>
  );
}
