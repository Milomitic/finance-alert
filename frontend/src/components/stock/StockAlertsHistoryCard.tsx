import { ChevronLeft, ChevronRight, History, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { alerts as alertsApi } from "@/api/alerts";
import type { Alert } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { AlertsTable } from "@/components/AlertsTable";
import { CardErrorOverlay } from "@/components/stock/CardErrorOverlay";
import { CardRefreshButton } from "@/components/stock/CardRefreshButton";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useScanStock } from "@/hooks/useAlertMutations";
import { getAlertMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/** Righe per pagina sullo storico completo. */
const PER_PAGINA = 25;

interface Props {
  alerts: Alert[];
  /** Ticker — needed to run the per-stock signal scan + invalidate the detail
   *  query so the freshly-generated signals appear. */
  ticker: string;
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
export function StockAlertsHistoryCard({ alerts, ticker }: Props) {
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
  const completo = scheda === "completo";
  const righe = completo ? (storico.data?.items ?? []) : sorted;
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
              testo, e aveva ragione a rompersi.) */}
          <SectionTitle
            icon={History}
            label={`Segnali storici per questo ticker (${totale})`}
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
            <div className="flex-1 min-h-0 overflow-y-auto -mx-4 px-4">
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
      <AlertDetailDialog alert={open} onClose={() => setOpen(null)} />
    </>
  );
}
