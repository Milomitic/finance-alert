import { ChevronLeft, ChevronRight, History, TrendingDown, TrendingUp } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { alerts as alertsApi } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog, type AlertChartLink } from "@/components/AlertDetailDialog";
import { AlertsTable } from "@/components/AlertsTable";
import { CardErrorOverlay } from "@/components/stock/CardErrorOverlay";
import { CardRefreshButton } from "@/components/stock/CardRefreshButton";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useScanStock } from "@/hooks/useAlertMutations";
import { getAlertMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/** Righe al massimo nella lista: i recenti si fermano qui, lo storico pagina
 *  di tanti. Una scheda compatta, su richiesta — il resto e' nello storico. */
const PER_PAGINA = 10;
/** Righe visibili senza scorrere. Le altre fino a PER_PAGINA si scorrono. */
const RIGHE_VISIBILI = 5;

interface Props {
  alerts: Alert[];
  /** Ticker — needed to run the per-stock signal scan + invalidate the detail
   *  query so the freshly-generated signals appear. */
  ticker: string;
  /** Il grafico della pagina, quando c'e' (FA-066). Il dialogo del segnale lo
   *  riceve per offrire «Mostra sul grafico»: sulle pagine senza grafico il
   *  bottone non esiste, invece di esistere e non fare niente. */
  chart?: AlertChartLink;
}

/* ─── Aggregate stats (header strip) ────────────────────────────────────── */

interface AlertStats {
  total: number;
  bullish: number;
  bearish: number;
  last30d: number;
}

function computeStats(alerts: Alert[]): AlertStats {
  const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
  let bullish = 0;
  let bearish = 0;
  let last30d = 0;
  for (const a of alerts) {
    if (new Date(a.triggered_at).getTime() >= cutoff) last30d++;
    // Effective tone: handles both rule-based alerts (kind tone) and
    // price-target alerts (direction tone) so the aggregate counts
    // include price targets that fired.
    const tone = getAlertMeta(a).tone;
    if (tone === "bullish") bullish++;
    else if (tone === "bearish") bearish++;
  }
  return { total: alerts.length, bullish, bearish, last30d };
}

/* ─── Card root ─────────────────────────────────────────────────────────── *
 *
 * Per user feedback, this card now renders the canonical AlertsTable
 * (in `embedded` mode) instead of a custom button-card-per-alert
 * layout. That gives the stock-detail page the same column structure,
 * date columns, kind/tone chips, archive flag, and price formatting
 * as the alerts page — identical info, identical visuals.
 *
 * Embedded-mode adjustments (see AlertsTable):
 *   - No checkbox column (no bulk archive on a per-stock view).
 *   - No search input in the Ticker column header (one stock = one
 *     possible value).
 *   - Ticker + Nome columns dropped — they'd just repeat the same
 *     value on every row.
 *
 * The aggregate stats strip (bull/bear/30d counts) stays at the top
 * since it's distinct context that the alerts page doesn't show.
 */
export function StockAlertsHistoryCard({ alerts, ticker, chart }: Props) {
  const [open, setOpen] = useState<Alert | null>(null);
  /* ─── Recenti / Storico completo ──────────────────────────────────────
   *
   * I RECENTI sono i non archiviati, che arrivano gia' col payload del
   * dettaglio. E' una scelta di prodotto: la scheda non ha una colonna
   * Archivio, e mescolare le due meta' senza distinguerle sarebbe peggio.
   *
   * ⚠️ Ma i recenti NON bastano, ed e' il difetto che questa scheda chiude
   * (FA-054): in produzione 5.312 dei 5.313 esiti maturati stanno su alert
   * ARCHIVIATI, perche' archiviazione e maturazione seguono entrambe l'ETA'.
   * La colonna Esito di questa scheda mostrava quindi UN esito su 5.313.
   *
   * Lo storico completo non e' una rotta nuova: e' `/api/alerts`, che gia'
   * pagina, gia' ordina e gia' porta gli esiti. */
  const [scheda, setScheda] = useState<"recenti" | "completo">("recenti");
  const [offset, setOffset] = useState(0);
  const storico = useQuery({
    queryKey: ["alert-storico", ticker, offset],
    queryFn: ({ signal }) =>
      alertsApi.list(
        { ticker, include_archived: true, limit: PER_PAGINA, offset },
        signal,
      ),
    enabled: scheda === "completo",
    staleTime: 60_000,
  });
  // Per-stock signal scan: runs the engine over this ticker's stored OHLCV and
  // persists new signal alerts. Quali query invalida lo dice `useScanStock`:
  // prima invalidava solo il dettaglio, e lo storico completo di questa stessa
  // card restava vecchio (FA-072).
  const scan = useScanStock(ticker);

  // Sort by triggered_at desc — backend should already order, but defensive.
  const sorted = useMemo(
    () =>
      [...alerts].sort(
        (a, b) =>
          new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime(),
      ),
    [alerts],
  );
  const stats = useMemo(() => computeStats(sorted), [sorted]);
  const recenti = useMemo(() => sorted.slice(0, PER_PAGINA), [sorted]);
  const completo = scheda === "completo";
  const righe = completo ? (storico.data?.items ?? []) : recenti;
  // ⚠️ Il titolo e la striscia contano TUTTI i recenti, la lista ne mostra
  // al massimo dieci: senza questa riga «Segnali (14)» sopra dieci righe
  // sembrerebbe un conteggio sbagliato.
  const nascosti = completo ? 0 : sorted.length - recenti.length;

  /* ─── Cinque righe a vista, le altre si scorrono ────────────────────────
   *
   * L'altezza si MISURA sulla quinta riga invece di scriverla in rem: la
   * radice qui e' 17px, le righe prendono l'altezza del chip piu' alto e i
   * bordi collassano, quindi un numero scritto a mano sbaglierebbe di qualche
   * pixel e mostrerebbe mezza sesta riga.
   *
   * Scrive lo stile sul nodo, senza stato: niente render in piu' e niente
   * `set-state-in-effect`, che e' nel cancello. Senza array di dipendenze di
   * proposito — il corpo si smonta durante il caricamento e su un errore di
   * scan, e rimontato con le STESSE righe un effetto legato a `righe` non
   * ripartirebbe, lasciando la lista senza tetto.
   *
   * Dove non c'e' layout (jsdom) le misure valgono zero, e allora il tetto non
   * si mette: un `maxHeight: 0px` renderebbe la lista invisibile. */
  const corpo = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = corpo.current;
    if (!el) return;
    const tr = el.querySelectorAll("tbody tr");
    if (tr.length <= RIGHE_VISIBILI) {
      el.style.maxHeight = "";
      return;
    }
    const alto =
      tr[RIGHE_VISIBILI - 1].getBoundingClientRect().bottom -
      el.getBoundingClientRect().top +
      el.scrollTop;
    el.style.maxHeight = alto > 0 ? `${Math.ceil(alto)}px` : "";
  });
  const totale = completo ? (storico.data?.total ?? 0) : stats.total;
  const primaDellaPagina = offset + 1;
  const ultimaDellaPagina = offset + righe.length;

  // No-op handlers for the bulk-action props — embedded mode hides
  // the checkbox column, so these are never invoked in practice.
  const noopSelect = () => {};

  return (
    <>
      {/* Card cascades flex-col so the body section can flex-1 +
          overflow-y-auto. Without `h-full overflow-hidden flex
          flex-col` here, the parent grid's stretch doesn't make the
          inner table region scrollable — the cap was a `max-h-[460px]`
          that ignored the actual row height. Now: card matches
          sibling height, table region scrolls if rows exceed it. */}
      <Card className="h-full overflow-hidden flex flex-col">
        <CardContent className="p-4 flex-1 min-h-0 flex flex-col">
          {/* Header strip: title + aggregate stats (bull/bear/last30d) */}
          {/* ⚠️ Il nome della scheda e' la sua IDENTITA' e non cambia con la
              vista: farlo variare rende irriconoscibile il riquadro — la stessa
              regola per cui, quando lo spazio manca, e' la decorazione a cedere
              e non l'etichetta. Il CONTEGGIO invece appartiene alla vista,
              quindi quello segue. (Il gate e2e localizza la scheda per questo
              testo, e aveva ragione a rompersi.)
              «Segnali» e non piu' «Segnali storici per questo ticker», su
              richiesta: il nome corto lascia ai controlli la STESSA riga del
              titolo invece di mandarli a capo. Il `flex-wrap` di SectionTitle
              resta come ripiego dove la scheda e' stretta. */}
          <SectionTitle
            icon={History}
            label={`Segnali (${totale})`}
            className="mb-3 shrink-0"
            right={
              <div className="flex items-center gap-2 flex-wrap text-[0.7647rem]">
                {/* ⚠️ NON e' un gruppo di tab, ed e' stato un errore renderlo
                    tale. `TabsTrigger` di Radix emette `aria-controls` verso il
                    `TabsContent` corrispondente; qui il contenuto e' un fratello
                    piu' in basso, quindi il riferimento puntava al NULLA e il
                    gate UI l'ha letto come `aria-valid-attr-value: 0 -> 1`.
                    Un'ARIA che nomina un id inesistente e' peggio di nessuna
                    ARIA: gli assistivi annunciano una relazione che non c'e'.

                    Due bottoni con `aria-pressed` sono la forma corretta di un
                    controllo segmentato, e non promettono un pannello. */}
                <div
                  role="group"
                  aria-label="Vista dei segnali"
                  className="inline-flex h-6 items-center rounded-lg bg-muted p-0.5"
                >
                  {([
                    ["recenti", "Recenti", "I segnali non archiviati di questo titolo"],
                    ["completo", "Storico", "Tutti i segnali, archiviati compresi — e' dove stanno gli esiti maturati"],
                  ] as const).map(([valore, etichetta, spiegazione]) => (
                    <button
                      key={valore}
                      type="button"
                      aria-pressed={scheda === valore}
                      title={spiegazione}
                      onClick={() => {
                        setScheda(valore);
                        // L'offset si azzera cambiando vista. In render, non in
                        // un effect: `react-hooks/set-state-in-effect` e' gated.
                        setOffset(0);
                      }}
                      className={cn(
                        "h-5 rounded px-1.5 text-[0.6765rem] transition-colors",
                        scheda === valore
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {etichetta}
                    </button>
                  ))}
                </div>
                {/* ⚠️ La striscia NON compare sullo storico. E' calcolata sulle
                    righe CARICATE: su una pagina da 25 accanto a un totale di
                    400 direbbe "rialzisti 12" intendendo un'altra cosa. Stessa
                    regola per cui un tasso sotto i 20 campioni mostra la
                    frazione grezza invece di una percentuale. */}
                {!completo && stats.total > 0 && (
                  <>
                  {stats.last30d > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/70"
                      title="Segnali generati negli ultimi 30 giorni"
                    >
                      <span className="text-muted-foreground">30d:</span>
                      <span className="font-bold tabular-nums">{stats.last30d}</span>
                    </span>
                  )}
                  {stats.bullish > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200"
                      title="Segnali con tono bullish (RSI oversold, golden cross, breakout, ecc.)"
                    >
                      <TrendingUp className="h-3 w-3" />
                      <span className="font-bold tabular-nums">{stats.bullish}</span>
                    </span>
                  )}
                  {stats.bearish > 0 && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200"
                      title="Segnali con tono bearish (RSI overbought, death cross, ecc.)"
                    >
                      <TrendingDown className="h-3 w-3" />
                      <span className="font-bold tabular-nums">{stats.bearish}</span>
                    </span>
                  )}
                  </>
                )}
                {/* FA-066: i setup di questo titolo stanno su /setups, filtrati.
                    Un collegamento e non una seconda lista: la scheda setup
                    rimossa dal dettaglio titolo non torna. */}
                <Link
                  to={`/setups?ticker=${encodeURIComponent(ticker)}`}
                  className="text-muted-foreground hover:text-foreground hover:underline underline-offset-2"
                >
                  Setup del titolo
                </Link>
                <CardRefreshButton
                  onClick={() => scan.mutate()}
                  busy={scan.isPending}
                  title="Processa i segnali per questo ticker"
                />
              </div>
            }
          />

          {scan.error ? (
            <div className="flex-1 min-h-0 flex items-center justify-center">
              <CardErrorOverlay
                error={scan.error}
                onRetry={() => scan.mutate()}
                retrying={scan.isPending}
              />
            </div>
          ) : completo && storico.isPending ? (
            <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
              Carico lo storico…
            </div>
          ) : righe.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-center text-sm text-muted-foreground">
              <div>
                Nessun segnale mai generato per questo ticker.
                <div className="text-xs mt-1 opacity-75">
                  Quando una regola si attiva sui dati di questo titolo,
                  il segnale comparirà qui in cima.
                </div>
              </div>
            </div>
          ) : (
            // Body grows to fill the row height set by the company-
            // profile sibling and scrolls internally when the row
            // count exceeds it. No more hardcoded max-h.
            <div ref={corpo} className="flex-1 min-h-0 overflow-y-auto -mx-4 px-4">
              <AlertsTable
                embedded
                alerts={righe}
                selectedIds={new Set()}
                onSelect={noopSelect}
                onSelectAll={noopSelect}
                onRowClick={setOpen}
                q=""
                onQueryChange={noopSelect}
              />
            </div>
          )}
          {nascosti > 0 && !scan.error && (
            <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 pt-2 text-[0.7647rem] text-muted-foreground">
              <span className="tabular-nums">
                Ultimi {recenti.length} di {sorted.length}
              </span>
              <button
                type="button"
                className="rounded px-2 py-1 hover:bg-muted hover:text-foreground"
                onClick={() => {
                  setScheda("completo");
                  setOffset(0);
                }}
              >
                Apri lo storico
              </button>
            </div>
          )}
          {completo && totale > PER_PAGINA && (
            <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 pt-2 text-[0.7647rem] text-muted-foreground">
              <span className="tabular-nums">
                {primaDellaPagina}–{ultimaDellaPagina} di {totale}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="inline-flex items-center gap-0.5 rounded px-2 py-1 hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
                  onClick={() => setOffset((o) => Math.max(0, o - PER_PAGINA))}
                  disabled={offset === 0 || storico.isFetching}
                >
                  <ChevronLeft className="h-3 w-3" aria-hidden />
                  Precedenti
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-0.5 rounded px-2 py-1 hover:bg-muted disabled:opacity-40 disabled:hover:bg-transparent"
                  onClick={() => setOffset((o) => o + PER_PAGINA)}
                  disabled={!storico.data?.has_more || storico.isFetching}
                >
                  Successivi
                  <ChevronRight className="h-3 w-3" aria-hidden />
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} chart={chart} />
    </>
  );
}
