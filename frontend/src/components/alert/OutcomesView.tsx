import { Layers, Target, X, Zap } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { PlanOutcomeSummary } from "@/api/planOutcomes";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { SignalOutcomeList } from "@/components/alert/SignalOutcomeList";
import { SetupsView } from "@/components/setups/SetupsView";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { ColumnVisibilityButton } from "@/components/ui/column-visibility-menu";
import { MetricStrip, type MetricTileProps } from "@/components/ui/metric-tile";
import { SchedePagina } from "@/components/ui/schede-pagina";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useAlert } from "@/hooks/useAlerts";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { ESITI_PER_PAGINA, usePlanOutcomes } from "@/hooks/usePlanOutcomes";
import {
  COLONNE_ESITI_NASCONDIBILI, ordineDa, versoIniziale, type OrdineEsiti,
} from "@/lib/colonneEsiti";
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
  { id: "segnali", label: "Segnali", icon: Zap },
  { id: "setup", label: "Setup", icon: Layers },
] as const;

type SottoVista = (typeof SOTTOVISTE)[number]["id"];

/** Sotto questo numero di piani risolti la quota di target esce come FRAZIONE
 *  invece che come percentuale. Stessa soglia della pagina dei setup: «100%»
 *  su sei episodi e' compatibile con un tasso vero vicino al lancio di una
 *  moneta, e in grassetto non lo sembra. */
const MIN_TASSO_N = 20;

const GARE = ["tp1", "stop", "ambigua", "scaduto"] as const;

const VERSI = [
  { id: null, label: "Tutti" },
  { id: "rialzisti", label: "Rialzisti" },
  { id: "ribassisti", label: "Ribassisti" },
] as const;

function sottovistaDa(raw: string | null): SottoVista {
  return SOTTOVISTE.some((v) => v.id === raw) ? (raw as SottoVista) : "segnali";
}

const TONO_DA_URL = { rialzisti: "bull", ribassisti: "bear" } as const;

function tonoDa(raw: string | null): "bull" | "bear" | undefined {
  return raw && raw in TONO_DA_URL ? TONO_DA_URL[raw as keyof typeof TONO_DA_URL] : undefined;
}

/* ─── I controlli ─────────────────────────────────────────────────────────
 *
 * ⚠️ Gruppi con un'ETICHETTA, non una fila di pastiglie tutte uguali. La
 * prima versione metteva «Ogni esito», quattro esiti, un separatore, «Ogni
 * condizione» e QUATTORDICI condizioni su una riga sola che andava a capo tre
 * volte: nessuna delle due dimensioni si leggeva come una dimensione, e
 * «Target» accanto a «Divergenza RSI» sembrava lo stesso tipo di scelta.
 *
 * ⚠️ E le condizioni stanno in un `<select>`, non in pastiglie: sono quante
 * ne emette il motore, quindi il loro numero non e' una costante di
 * progetto. Un select si dimensiona sull'opzione PIU' LUNGA e ignora il
 * genitore finche' non gli si mette `min-w-0 max-w-full` — gia' pagato su
 * questo repo. */

function Segmentato<T extends string | null>({
  etichetta, voci, valore, onCambia,
}: {
  etichetta: string;
  voci: readonly { id: T; label: string }[];
  valore: T;
  onCambia: (v: T) => void;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="shrink-0 text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground">
        {etichetta}
      </span>
      {/* Bottoni con `aria-pressed`, non `role="tab"`: non c'e' un tabpanel da
          promettere, e un `aria-controls` verso un id che non esiste fa
          annunciare agli assistivi una relazione inventata. */}
      <div
        role="group"
        aria-label={etichetta}
        className="inline-flex overflow-hidden rounded-md border text-xs font-semibold"
      >
        {voci.map((v) => (
          <button
            key={v.id ?? "tutti"}
            type="button"
            aria-pressed={valore === v.id}
            onClick={() => onCambia(v.id)}
            className={cn(
              "min-h-[36px] whitespace-nowrap px-2.5 transition-colors",
              valore === v.id
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:bg-accent/40",
            )}
          >
            {v.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Perché una parte dell'elenco non entra nelle misure. Detto a schermo e non
 *  solo nel codice: una media che esclude righe visibili senza dirlo sembra
 *  sbagliata a chi le conta. */
function NotaAperti({ n }: { n: number }) {
  return (
    <>
      {" "}
      {n === 1 ? "Un altro piano è" : `Altri ${n.toLocaleString("it-IT")} piani sono`} ancora
      in corso e restano fuori finché il loro orizzonte non è trascorso: fino ad allora
      contengono solo le uscite rapide, cioè soprattutto gli stop, e porterebbero la media
      sotto il vero.
    </>
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
    : null;
  const detector = params.get("condizione") || null;
  const versoUrl = params.get("tono");
  const verso = VERSI.some((v) => v.id === versoUrl) ? (versoUrl as string | null) : null;
  const tone = tonoDa(verso);
  const ticker = params.get("ticker")?.trim().toUpperCase() || undefined;
  const paginaUrl = Number(params.get("pagina"));
  const offset =
    Number.isInteger(paginaUrl) && paginaUrl > 1 ? (paginaUrl - 1) * ESITI_PER_PAGINA : 0;
  const [signalId, setSignalId] = useState<number | null>(null);
  const signal = useAlert(signalId);
  // L'ordinamento vive nell'URL come i filtri, cosi' un link lo porta con se'.
  // Assente = la chiusura piu' recente prima, cioe' l'ordine del server.
  const ordina = ordineDa(params.get("ordina"));
  const direzione: "asc" | "desc" = params.get("direzione") === "asc" ? "asc" : "desc";
  // Le colonne visibili: stesso meccanismo della tabella Segnali, chiave sua.
  const colonne = useColumnVisibility("esiti", COLONNE_ESITI_NASCONDIBILI);

  const q = usePlanOutcomes(
    {
      esito: gara ?? undefined, detector: detector ?? undefined, tone, ticker,
      limit: ESITI_PER_PAGINA, offset,
      sort_by: ordina ?? undefined, sort_dir: ordina ? direzione : undefined,
    },
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
  /** Stessa colonna: si inverte il verso. Colonna nuova: parole dall'A,
   *  numeri e date dal piu' grande. Torna alla prima pagina, come un filtro:
   *  la quarta pagina di un altro ordine e' un'altra fetta. */
  const ordinaPer = (col: OrdineEsiti) => {
    const verso =
      ordina === col ? (direzione === "desc" ? "asc" : "desc") : versoIniziale(col);
    cambiaPerimetro({ ordina: col, direzione: verso });
  };

  const righe = q.data?.items ?? [];
  const totale = q.data?.total ?? 0;
  /** ⚠️ Righe dell'elenco a finestra ancora aperta: restano nella lista (quello
   *  stop è stato colpito davvero) ma fuori dalle misure, perché fra i segnali
   *  recenti ci sono solo le uscite veloci — cioè soprattutto gli stop — e
   *  contarli insieme agli altri peggiorava la media. */
  const apertiEsclusi = q.data?.open_excluded ?? 0;
  const detectors = Object.entries(q.data?.counts_by_detector ?? {})
    .map(([d, n]) => ({ detector: d, count: n, label: detectorLabel(d) }))
    .sort((a, b) => a.label.localeCompare(b.label));
  const filtriAttivi = !!gara || !!detector || !!verso || !!ticker;
  /** ⚠️ La somma dei conteggi, non `totale`: quello e' gia' ristretto dalla
   *  condizione scelta, quindi «Tutte (12)» annuncerebbe dodici righe mentre
   *  toglierlo ne mostra trecento. I conteggi arrivano dal server misurati
   *  PRIMA del filtro per condizione, apposta. */
  const totaleCondizioni = detectors.reduce((s, d) => s + d.count, 0);

  return (
    <div className="max-w-5xl space-y-4">
      {/* Il selettore DENTRO la scheda Esiti: stesso componente delle schede
          della pagina, nella taglia compatta, cosi' si legge come un livello
          sotto e non come una seconda fila di schede. */}
      <SchedePagina
        dimensione="compatta"
        voci={SOTTOVISTE}
        attiva={sotto}
        onCambia={(id) => cambiaPerimetro({ esiti: id === "segnali" ? null : id })}
        etichetta="Quali esiti"
      />

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
                Le misure contano i <strong>piani a finestra chiusa</strong> che passano i
                filtri attivi ({q.data.summary.n.toLocaleString("it-IT")}), non le righe di
                questa pagina.
                {apertiEsclusi > 0 && <NotaAperti n={apertiEsclusi} />}
              </p>
            </section>
          ) : apertiEsclusi > 0 ? (
            <p className="text-xs text-muted-foreground">
              Nessun piano a finestra chiusa fra quelli filtrati: le misure compaiono quando
              trascorre il primo orizzonte.
              <NotaAperti n={apertiEsclusi} />
            </p>
          ) : null}

          {/* I controlli, per dimensione. Vedi la nota sopra `Segmentato`. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Segmentato
              etichetta="Esito"
              valore={gara}
              onCambia={(v) => cambiaPerimetro({ gara: v })}
              voci={[
                { id: null, label: "Tutti" },
                ...GARE.map((g) => ({ id: g as string, label: ESITO_META[g].label })),
              ]}
            />

            <Segmentato
              etichetta="Verso"
              valore={verso}
              onCambia={(v) => cambiaPerimetro({ tono: v })}
              voci={VERSI}
            />

            {detectors.length > 1 && (
              <label className="flex min-w-0 items-center gap-2">
                <span className="shrink-0 text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground">
                  Condizione
                </span>
                <select
                  value={detector ?? ""}
                  onChange={(e) => cambiaPerimetro({ condizione: e.target.value || null })}
                  className="min-h-[36px] min-w-0 max-w-full rounded-md border bg-background px-2 text-xs font-semibold"
                >
                  <option value="">Tutte ({totaleCondizioni.toLocaleString("it-IT")})</option>
                  {detectors.map(({ detector: d, count, label }) => (
                    <option key={d} value={d}>
                      {label} ({count})
                    </option>
                  ))}
                </select>
              </label>
            )}

            {ticker && (
              <button
                type="button"
                onClick={() => cambiaPerimetro({ ticker: null })}
                aria-label={`Solo ${ticker}, togli il filtro`}
                className="inline-flex min-h-[36px] items-center gap-1 rounded-md border px-3 text-xs font-semibold hover:bg-accent"
              >
                Solo {ticker}
                <X className="h-3 w-3" aria-hidden />
              </button>
            )}

            {filtriAttivi && (
              <button
                type="button"
                onClick={() =>
                  cambiaPerimetro({ gara: null, tono: null, condizione: null, ticker: null })
                }
                className="min-h-[36px] text-xs font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Azzera i filtri
              </button>
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
                right={
                  <ColumnVisibilityButton
                    columns={COLONNE_ESITI_NASCONDIBILI}
                    isVisible={colonne.isVisible}
                    toggle={colonne.toggle}
                  />
                }
              />
            </div>
            {q.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <CardSkeleton key={i} rows={1} className="h-[34px]" />
                ))}
              </div>
            ) : q.isError ? (
              <QueryError
                message="degli esiti di piano"
                onRetry={q.refetch}
                isRetrying={q.isFetching}
              />
            ) : (
              <SignalOutcomeList
                righe={righe}
                onApriSegnale={setSignalId}
                ordine={
                  ordina
                    ? { colonna: ordina, verso: direzione }
                    : { colonna: "resolved_date", verso: "desc" }
                }
                onOrdina={ordinaPer}
                colonne={colonne}
              />
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
