import { Target } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { PlanOutcomeSummary } from "@/api/planOutcomes";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { SignalOutcomeList } from "@/components/alert/SignalOutcomeList";
import { SetupsView } from "@/components/setups/SetupsView";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { MetricStrip, type MetricTileProps } from "@/components/ui/metric-tile";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useAlert } from "@/hooks/useAlerts";
import { ESITI_PER_PAGINA, usePlanOutcomes } from "@/hooks/usePlanOutcomes";
import { ESITO_META, formatR } from "@/lib/planOutcome";
import { detectorLabel } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

/* ─── Esiti: che cosa si e' chiuso ────────────────────────────────────────
 *
 * La scheda raccoglie i due modi in cui un'attesa finisce, che prima stavano
 * in due destinazioni diverse:
 *
 *   Segnali   il piano ha toccato prima il target o lo stop? (plan_outcomes)
 *   Setup     il segnale atteso e' poi scattato?             (setup chiusi)
 *
 * ⚠️ Restano due liste e non una. Un setup convertito e un piano andato a
 * target sono eventi di ANELLI diversi della stessa catena — setup → segnale →
 * posizione — e impilarli in un unico elenco produrrebbe un conteggio che non
 * misura niente, perche' lo stesso episodio comparirebbe due volte.
 */

const SOTTOVISTE = [
  { id: "segnali", label: "Segnali" },
  { id: "setup", label: "Setup" },
] as const;

type SottoVista = (typeof SOTTOVISTE)[number]["id"];

/** Sotto questo numero di piani risolti la quota di target esce come FRAZIONE
 *  invece che come percentuale. Stessa soglia della pagina dei setup: «100%»
 *  su sei episodi e' compatibile con un tasso vero vicino al lancio di una
 *  moneta, e in grassetto non lo sembra. */
const MIN_TASSO_N = 20;

const GARE = ["tp1", "stop", "ambigua", "scaduto"] as const;

function sottovistaDa(raw: string | null): SottoVista {
  return SOTTOVISTE.some((v) => v.id === raw) ? (raw as SottoVista) : "segnali";
}

const TONO_DA_URL = { rialzisti: "bull", ribassisti: "bear" } as const;

function tonoDa(raw: string | null): "bull" | "bear" | undefined {
  return raw && raw in TONO_DA_URL ? TONO_DA_URL[raw as keyof typeof TONO_DA_URL] : undefined;
}

function Chip({
  attivo, onClick, children,
}: {
  attivo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={attivo}
      onClick={onClick}
      className={cn(
        "min-h-[36px] rounded-md border px-3 text-xs font-semibold transition-colors",
        attivo ? "bg-primary text-primary-foreground" : "hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

/** Le misure della popolazione filtrata.
 *
 *  ⚠️ L'intestazione e' l'ATTESA IN R, non la quota di target, e non e' una
 *  scelta estetica: i target stanno a R:R fino a 4,0, quindi un tasso letto da
 *  solo sembrerebbe pessimo mentre il sistema guadagna — un 35% a 4:1 batte un
 *  60% a 1:1. La quota resta a schermo, accanto e non al posto. */
function Misure({ s }: { s: PlanOutcomeSummary }) {
  const vinte = s.esiti.tp1 ?? 0;
  const intervallo = s.expectancy_ci;
  const tessere: MetricTileProps[] = [
    {
      label: "Attesa per segnale",
      primary: true,
      value: formatR(s.expectancy_r),
      hint:
        intervallo === null
          ? `${s.n} piani · troppo poche finestre indipendenti per un intervallo`
          : `IC ${formatR(intervallo[0])}–${formatR(intervallo[1])} su ${s.effective_n} ` +
            `${s.effective_n === 1 ? "finestra indipendente" : "finestre indipendenti"}` +
            (s.verdict === "inconclusive" ? " · non concludente" : ""),
      note:
        "Il guadagno medio in multipli di R, dove R è la distanza dello stop. È l'unico numero che aggrega onestamente: una quota di target del 35% con target a 4:1 batte un 60% a 1:1. " +
        "L'intervallo è largo quanto le finestre INDIPENDENTI giustificano: due segnali a tre giorni di distanza, etichettati a ventuno sedute, condividono quasi tutta la finestra e non sono due estrazioni.",
      // Il colore solo quando l'intervallo esclude lo zero: una banda che lo
      // contiene non ha detto niente, e non riceve colore.
      tone: s.verdict === "positive" ? "ok" : s.verdict === "negative" ? "bad" : null,
    },
    {
      label: "Piani risolti",
      primary: true,
      value: String(s.n),
      hint:
        `${vinte} target · ${s.esiti.stop ?? 0} stop` +
        (s.esiti.ambigua ? ` · ${s.esiti.ambigua} stessa barra` : "") +
        (s.esiti.scaduto ? ` · ${s.esiti.scaduto} scaduti` : ""),
      note:
        "Un piano si risolve quando il prezzo tocca lo stop o il primo target, oppure quando l'orizzonte del segnale è trascorso senza che accada né l'uno né l'altro. " +
        "«Stessa barra» sono i giorni in cui entrambi sono stati toccati: il dato giornaliero non dice quale sia venuto prima, quindi si assegna lo stop e la categoria resta separata.",
    },
    {
      label: "Chiusi al target",
      primary: true,
      // Sotto la soglia la frazione, non la percentuale: stessa regola del
      // tasso di conversione dei setup.
      value:
        s.n < MIN_TASSO_N ? `${vinte}/${s.n}` : `${Math.round(s.win_rate)}%`,
      hint:
        s.n < MIN_TASSO_N
          ? `troppo pochi per un tasso (servono ${MIN_TASSO_N})`
          : `${vinte} su ${s.n} piani risolti`,
      note: "Quota dei piani che hanno toccato il target prima dello stop. ⚠️ Da sola non dice se il sistema guadagna: va letta accanto all'attesa in R.",
    },
    {
      label: "Stop troppo stretto",
      primary: true,
      value: String(s.stop_too_tight),
      hint: `su ${s.n} piani risolti`,
      note:
        "Quante volte lo stop è stato colpito PRIMA di un target che poi è arrivato lo stesso. Non è «entrambi toccati»: l'ordine è tutta la diagnosi, e dice che il verso era giusto mentre la distanza dello stop no. " +
        "È il numero che nessun'altra misura di questa app sa dare, e la ragione per cui le date delle gambe vengono registrate anche dopo la chiusura.",
    },
    {
      label: "Escursione avversa sui vinti",
      value: s.mae_r_on_wins === null ? "—" : formatR(s.mae_r_on_wins),
      hint: "mediana · quanto sono andati contro prima di pagare",
      note: "Se i piani vinti vanno poco contro, lo stop può stringersi. È un ingresso continuo, quindi con molta più informazione per osservazione di un sì/no.",
    },
    {
      label: "Escursione a favore sui persi",
      value: s.mfe_r_on_losses === null ? "—" : formatR(s.mfe_r_on_losses),
      hint: "mediana · quanto c'era sul tavolo",
      note: "Quanto erano andati a favore i piani poi chiusi in perdita. Un valore alto dice che qualcosa c'era, e che il target o la gestione non l'hanno raccolto.",
    },
    {
      label: "Sedute fino all'esito",
      value: s.median_bars === null ? "—" : `${s.median_bars.toFixed(0)}`,
      hint: `mediana · orizzonte massimo ${s.horizon_days}g`,
      note: "Quanto dura un piano prima di risolversi. L'orizzonte è il tetto: oltre non si guarda, perché un tocco alla trentesima seduta di un segnale etichettato a ventuno appartiene a un'altra domanda.",
    },
  ];
  return <MetricStrip tiles={tessere} />;
}

export function OutcomesView() {
  const [params, setParams] = useSearchParams();
  const sotto = sottovistaDa(params.get("esiti"));
  const gara = GARE.includes(params.get("gara") as (typeof GARE)[number])
    ? (params.get("gara") as string)
    : undefined;
  const detector = params.get("condizione") || undefined;
  const tone = tonoDa(params.get("tono"));
  const ticker = params.get("ticker")?.trim().toUpperCase() || undefined;
  const paginaUrl = Number(params.get("pagina"));
  const offset =
    Number.isInteger(paginaUrl) && paginaUrl > 1 ? (paginaUrl - 1) * ESITI_PER_PAGINA : 0;
  const [signalId, setSignalId] = useState<number | null>(null);
  const signal = useAlert(signalId);

  const q = usePlanOutcomes(
    { esito: gara, detector, tone, ticker, limit: ESITI_PER_PAGINA, offset },
    sotto === "segnali",
  );

  const scrivi = (cambi: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(cambi)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    setParams(p, { replace: true });
  };
  /** Un controllo che ridefinisce il PERIMETRO torna alla prima pagina:
   *  restare alla quarta dopo aver cambiato filtro mostrerebbe una fetta di
   *  mezzo di una popolazione diversa, senza che niente lo dica. */
  const cambiaPerimetro = (cambi: Record<string, string | null>) =>
    scrivi({ ...cambi, pagina: null });

  const righe = q.data?.items ?? [];
  const totale = q.data?.total ?? 0;
  const detectors = Object.entries(q.data?.counts_by_detector ?? {})
    .map(([d, n]) => ({ detector: d, count: n }))
    .sort((a, b) => b.count - a.count || a.detector.localeCompare(b.detector));

  return (
    <div className="max-w-5xl space-y-4">
      {/* Bottoni con `aria-pressed`, non tab: non c'e' un tabpanel da
          promettere, e un `aria-controls` verso un id che non esiste fa
          annunciare agli assistivi una relazione inesistente. */}
      <div className="flex flex-wrap items-center gap-2">
        <div
          role="group"
          aria-label="Quali esiti"
          className="inline-flex overflow-hidden rounded-md border text-xs font-semibold"
        >
          {SOTTOVISTE.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={sotto === v.id}
              onClick={() => cambiaPerimetro({ esiti: v.id === "segnali" ? null : v.id })}
              className={cn(
                "min-h-[36px] px-3 transition-colors",
                sotto === v.id
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/40",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {sotto === "setup" ? (
        <SetupsView vista="esiti" />
      ) : (
        <>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Per ogni segnale con un piano, quale fra <strong>stop</strong> e{" "}
            <strong>target</strong> è stato toccato per primo — e quando sono state toccate le
            altre gambe, anche dopo la chiusura. È una domanda diversa dalla colonna «Esito»
            della lista dei segnali, che dice se la direzione ha pagato a orizzonte fisso: un
            piano può prendere il target in tre sedute e finire l'orizzonte sotto il prezzo
            d'ingresso.
          </p>

          {q.isLoading ? (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <CardSkeleton key={i} rows={2} className="h-[96px]" />
              ))}
            </div>
          ) : q.data?.summary ? (
            <section aria-label="Misure dei piani risolti" className="space-y-2">
              <Misure s={q.data.summary} />
              <p className="text-xs text-muted-foreground">
                Le misure contano <strong>tutti i piani risolti</strong> che passano i filtri
                attivi ({totale.toLocaleString("it-IT")}), non le righe di questa pagina.
              </p>
            </section>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Chip attivo={!gara} onClick={() => cambiaPerimetro({ gara: null })}>
              Ogni esito
            </Chip>
            {GARE.map((g) => (
              <Chip key={g} attivo={gara === g} onClick={() => cambiaPerimetro({ gara: g })}>
                {ESITO_META[g].label}
              </Chip>
            ))}
            {detectors.length > 1 && (
              <>
                <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                <Chip
                  attivo={!detector}
                  onClick={() => cambiaPerimetro({ condizione: null })}
                >
                  Ogni condizione
                </Chip>
                {detectors.map(({ detector: d, count }) => (
                  <Chip
                    key={d}
                    attivo={detector === d}
                    onClick={() => cambiaPerimetro({ condizione: d })}
                  >
                    {detectorLabel(d)} <span className="tabular-nums opacity-70">{count}</span>
                  </Chip>
                ))}
              </>
            )}
          </div>

          <div>
            <div className="mb-3">
              <SectionTitle
                icon={Target}
                /* Il numero e' la POPOLAZIONE filtrata dal server, mai le
                   righe in pagina: questa app ha gia' stampato «50 setup
                   chiusi» sopra una lista di 795. */
                label={`Piani risolti — ${totale.toLocaleString("it-IT")}`}
              />
            </div>
            {q.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <CardSkeleton key={i} rows={2} className="h-[86px]" />
                ))}
              </div>
            ) : q.isError ? (
              <QueryError
                message="degli esiti di piano"
                onRetry={q.refetch}
                isRetrying={q.isFetching}
              />
            ) : (
              <SignalOutcomeList righe={righe} onApriSegnale={setSignalId} />
            )}

            {!q.isLoading && !q.isError && totale > ESITI_PER_PAGINA && (
              /* Senza questa riga una lista troncata e' indistinguibile da una
                 completa. */
              <div className="flex flex-wrap items-center justify-between gap-2 pt-3 text-xs text-muted-foreground">
                <span className="tabular-nums">
                  {offset + 1}–{offset + righe.length} di {totale}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="min-h-[36px] rounded-md border px-3 font-semibold hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
                    onClick={() =>
                      scrivi({
                        pagina:
                          offset - ESITI_PER_PAGINA > 0
                            ? String(Math.floor((offset - ESITI_PER_PAGINA) / ESITI_PER_PAGINA) + 1)
                            : null,
                      })
                    }
                    disabled={offset === 0 || q.isFetching}
                  >
                    Precedenti
                  </button>
                  <button
                    type="button"
                    className="min-h-[36px] rounded-md border px-3 font-semibold hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent"
                    onClick={() =>
                      scrivi({
                        pagina: String(Math.floor((offset + ESITI_PER_PAGINA) / ESITI_PER_PAGINA) + 1),
                      })
                    }
                    disabled={!q.data?.has_more || q.isFetching}
                  >
                    Successivi
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Il terzo anello della catena: da un esito si torna al segnale, e
              dal segnale alla posizione. */}
          <AlertDetailDialog alert={signal.data ?? null} onClose={() => setSignalId(null)} />
        </>
      )}
    </div>
  );
}
