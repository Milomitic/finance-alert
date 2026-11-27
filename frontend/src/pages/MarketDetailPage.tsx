import {
  ArrowLeft,
  Bitcoin,
  CircleDot,
  Coins,
  Droplet,
  Flame,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { FlashValue } from "@/components/ui/FlashValue";
import { MarketChart } from "@/components/market/MarketChart";
import { MacdPanel } from "@/components/stock/MacdPanel";
import { RsiPanel } from "@/components/stock/RsiPanel";
import { HeaderSparkline } from "@/components/stock/StockHeader";
import { NewsCard } from "@/components/stock/NewsCard";
import { TechnicalKpiCard } from "@/components/stock/TechnicalKpiCard";
import { RangeSelector } from "@/components/stock/RangeSelector";
import { PulsanteStrumenti } from "@/components/stock/PulsanteStrumenti";
import {
  IndicatorToggles,
  type IndicatorKey,
  type IndicatorStyle,
} from "@/components/stock/IndicatorToggles";
import { DEFAULT_INDICATOR_STATE } from "@/lib/indicatorState";
import { useChartSync } from "@/hooks/useChartSync";
import { useMarketDetail } from "@/hooks/useMarketDetail";
import { useStatisticheMercato } from "@/hooks/useMercati";
import { StatisticheMercato } from "@/components/markets/StatisticheMercato";
import { CalendarioRendimenti } from "@/components/stats/CalendarioRendimenti";
import { newsDelMercato } from "@/lib/schedeStrumento";
import { cn } from "@/lib/utils";
import { useTitoloScheda } from "@/hooks/useTitoloScheda";
import { percentuale } from "@/lib/numeri";
import { nomeCategoria, prezzoMercato } from "@/lib/prezzoMercato";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { QueryError } from "@/components/ui/query-error";

/* ─── Per-symbol icon overrides ──────────────────────────────────────────
 *
 * Mirrors the LiveAssetsPanel mapping so the detail page header uses
 * the exact same brand glyph (Bitcoin orange, Gold amber Coins, Oil
 * slate Droplet, etc.) the user clicked from. Indices use their
 * country flag instead — no icon override needed.
 */
type IconRender = {
  Component: React.ComponentType<{ className?: string }>;
  color: string;
};

const SYMBOL_ICON: Record<string, IconRender> = {
  "GC=F": { Component: Coins, color: "text-amber-500" },
  "SI=F": { Component: Coins, color: "text-zinc-400 dark:text-zinc-300" },
  "CL=F": { Component: Droplet, color: "text-slate-700 dark:text-slate-200" },
  "NG=F": { Component: Flame, color: "text-orange-500" },
  "BTC-USD": { Component: Bitcoin, color: "text-orange-500" },
  "ETH-USD": { Component: EthereumIcon, color: "text-indigo-500 dark:text-indigo-400" },
};

const CATEGORY_FALLBACK_ICON: Record<string, LucideIcon> = {
  index: Globe,
  commodity: CircleDot,
  crypto: Bitcoin,
};

function EthereumIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 256 416" className={className} fill="currentColor" aria-hidden>
      <path d="M127.961 0L125.166 9.5v275.668l2.795 2.79 127.962-75.638z" opacity="0.8" />
      <path d="M127.962 0L0 212.32l127.962 75.639V154.158z" />
      <path d="M127.961 312.187l-1.575 1.92v98.199l1.575 4.6L256 236.587z" opacity="0.8" />
      <path d="M127.962 416.905v-104.72L0 236.587z" />
      <path d="M127.961 287.958l127.96-75.637-127.96-58.162z" opacity="0.5" />
      <path d="M0 212.32l127.96 75.638V154.159z" opacity="0.65" />
    </svg>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────
 *
 * `/markets/:symbol` route — drilldown for non-stock instruments
 * (indices, commodities, crypto) listed in the dashboard's
 * LiveAssetsPanel. Renders header (icon + name + live price + Δ%) +
 * range selector + candlestick chart + KPI strip (52w high/low, etc.).
 *
 * Doesn't show fundamentals / alerts / insiders / analysts — those don't
 * make sense for ETH or WTI crude. News do for crypto and commodities (not
 * for indices), see `lib/schedeStrumento`.
 */
export default function MarketDetailPage() {
  const { symbol = "" } = useParams<{ symbol: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  // v2: default to "1d" timeframe (was "1y" range key — semantically
  // similar at the daily-resolution level, but the new vocabulary is
  // timeframe-based: 30m/1h/1d/1w/1m/all instead of 1m/3m/.../all
  // ranges. See `services/timeframe_service`.
  const range = searchParams.get("range") ?? "1d";
  const decoded = decodeURIComponent(symbol);
  const q = useMarketDetail(decoded, range);
  const statistiche = useStatisticheMercato(decoded);
  useTitoloScheda(q.data?.name ?? decoded);

  // Same convention as StockDetailPage: indicator visibility/style is
  // user-controllable via IndicatorToggles, and the price/RSI/MACD
  // charts share a chart-sync registrar so pan/zoom on any one
  // propagates to the others.
  const [strumentiAperti, setStrumentiAperti] = useState(false);
  const [indicators, setIndicators] = useState(DEFAULT_INDICATOR_STATE);
  const onIndicatorChange = (key: IndicatorKey, next: IndicatorStyle) =>
    setIndicators((prev) => ({ ...prev, [key]: next }));
  const registerChart = useChartSync();

  if (q.isError || (!q.isLoading && !q.data)) {
    return (
      <Card>
        <CardContent className="p-6">
          <QueryError message={`di ${decoded}: verifica che sia fra gli strumenti di mercato seguiti`}
            errore={q.error} onRetry={() => q.refetch()} isRetrying={q.isFetching} />
        </CardContent>
      </Card>
    );
  }

  if (q.isLoading || !q.data) {
    // Header KPI strip + chart, mirroring the loaded layout. Was two
    // generic `animate-pulse` boxes — same dimensions, but the header
    // strip now hints at the real "Symbol · Price · Change%" content.
    return (
      <div className="space-y-3">
        <CardSkeleton rows={3} className="h-[120px]" />
        <CardSkeleton label="GRAFICO" rows={10} strongHeader className="h-[460px]" />
      </div>
    );
  }

  const d = q.data;
  // Quote takes precedence for "live" price; falls back to last_close
  // when the quote service couldn't produce one (rate limit, error).
  const livePrice = d.quote?.price ?? d.last_close;
  const changePct = d.quote?.change_pct ?? d.change_pct;
  const isLive =
    d.quote?.market_state === "OPEN" && d.quote?.error == null;
  // FA-180: a cash chiuso prezzo e variazione sono del future, come in home.
  const sulFuture = d.using_futures === true && d.quote?.price != null;
  const symbolIcon = SYMBOL_ICON[d.symbol];
  const FallbackIcon = CATEGORY_FALLBACK_ICON[d.category] ?? Globe;
  // Crypto/commodity have no meaningful volume from yfinance for
  // `=F` futures — show volume only when at least one bar reports it.
  const hasVolume = d.bars.some((b) => (b.volume ?? 0) > 0);

  // V3.5 alignment with stock-detail StockHeader: derive subtle tone
  // from the day's change for the card's bg + left stripe + arrow,
  // and feed the candlestick history into the area-gradient sparkline.
  const tone =
    changePct == null
      ? { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" }
      : changePct > 0
        ? { bg: "bg-emerald-50/50 dark:bg-emerald-950/15", stripe: "bg-emerald-500", text: TESTO_SU, arrow: "▲" }
        : changePct < 0
          ? { bg: "bg-rose-50/50 dark:bg-rose-950/15", stripe: "bg-rose-500", text: TESTO_GIU, arrow: "▼" }
          : { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" };
  const headerCloses = d.bars
    .map((b) => b.close)
    .filter((c) => Number.isFinite(c));
  const headerSparkUp = (changePct ?? 0) >= 0;

  return (
    <div className="space-y-3">
      <h1 className="sr-only">{q.data?.name ?? decoded}</h1>
      {/* Il ritorno al contesto di provenienza.
          Modello copiato da `SectorDetailPage` e `InstitutionalDetailPage`,
          che lo avevano gia: un `<Link>` verso la pagina padre invece di un
          `navigate(-1)`, perche dice DOVE porta ed e l'unico dei due che
          funziona su un caricamento diretto, dove la storia del browser e
          vuota — cioe' esattamente quando si apre un link ricevuto. */}
      <Link
        to="/markets"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
      >
        <ArrowLeft className="h-4 w-4" />
        Mercati
      </Link>
      {/* Header — full StockHeader-style hero with gradient sparkline +
          prev close + tone-tinted bg + left accent stripe. Same visual
          language as /stocks/:ticker so the user feels at home no matter
          which detail page they land on. */}
      <Card className={cn("relative overflow-hidden border-border/60", tone.bg)}>
        <HeaderSparkline closes={headerCloses} up={headerSparkUp} />
        <div className={cn("absolute left-0 top-0 bottom-0 w-1.5 z-10", tone.stripe)} aria-hidden />
        {/* FA-183: su telefono identita' e prezzo uno SOTTO l'altro. Affiancati
            a 375 px il simbolo e il prezzo si toccavano e il nome diventava
            «S&P …». */}
        <CardContent className="relative z-10 p-4 pl-6 sm:p-5 sm:pl-7 flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
          <div className="flex-1 min-w-0 flex items-start gap-4">
          <span className="shrink-0 inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-white dark:bg-zinc-900 border border-border/60 shadow-sm">
            {symbolIcon ? (
              <symbolIcon.Component className={cn("h-8 w-8", symbolIcon.color)} />
            ) : (
              <FallbackIcon className="h-8 w-8 text-muted-foreground" />
            )}
          </span>
          <div className="min-w-0">
            <div className="text-2xl sm:text-3xl font-bold tracking-tight leading-tight break-words">
              {d.name}
            </div>
            <div className="mt-0.5 font-mono text-sm text-muted-foreground">{d.symbol}</div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              {/* Category tag now hosts the country flag (when known) so
                  the listing geography is anchored to the asset class
                  chip — same pattern as the stock-detail exchange tag. */}
              <span className="inline-flex items-center gap-1.5 rounded-md bg-muted/70 dark:bg-muted/40 px-2.5 py-1 text-sm font-medium">
                {d.flag && (
                  <img
                    src={`/flags/${d.flag}.svg`}
                    alt={d.flag}
                    width={18}
                    height={12}
                    style={{ width: "18px", height: "12px", objectFit: "cover" }}
                    className="rounded-sm shadow-sm"
                    aria-hidden
                  />
                )}
                {nomeCategoria(d.category)}
              </span>
              {d.quote?.currency && (
                <span className="text-sm text-muted-foreground">{d.quote.currency}</span>
              )}
            </div>
          </div>
          </div>
          <div className="tabular-nums shrink-0 flex flex-col gap-1 items-start sm:items-end sm:text-right">
            <div className="flex items-center gap-1.5 text-sm uppercase tracking-wide">
              {isLive ? (
                <span
                  className="inline-flex items-center gap-1 text-emerald-800 dark:text-emerald-300 font-semibold"
                  title="Borsa aperta: il prezzo si aggiorna in seduta"
                >
                  <span className="relative inline-flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  In seduta
                </span>
              ) : sulFuture ? (
                <span
                  className="inline-flex items-center gap-1 text-sky-800 dark:text-sky-300 font-semibold"
                  title={`Borsa chiusa: prezzo e variazione del future ${d.quote_symbol ?? ""}, che tratta anche fuori orario, sul suo regolamento precedente. Lo stesso numero della home. Il grafico resta l'indice.`}
                >
                  Future {d.quote_symbol}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-muted-foreground font-semibold">
                  Ultima chiusura
                </span>
              )}
            </div>
            <FlashValue
              value={livePrice}
              format={(v) => prezzoMercato(v, d.category)}
              className="text-4xl sm:text-5xl font-bold leading-none"
            />
            {changePct != null && (
              <div
                className={cn(
                  "inline-flex items-baseline gap-1.5 text-2xl font-bold mt-1",
                  tone.text,
                )}
              >
                <span className="text-lg">{tone.arrow}</span>
                <span>{percentuale(changePct)}</span>
              </div>
            )}
            {/* Prev close caption when live — same UX as stock detail. */}
            {(isLive || sulFuture) && d.quote?.prev_close != null && (
              <div
                className="text-[0.7059rem] uppercase tracking-wider text-muted-foreground mt-0.5"
                title="Chiusura della sessione precedente"
              >
                Chiusura prec.{" "}
                <span className="text-foreground/80 font-semibold tabular-nums">
                  {prezzoMercato(d.quote.prev_close, d.category)}
                </span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Chart (left) + sidebar (right). Same 1fr+480px split as
          /stocks/:ticker so the visual rhythm aligns. */}
      <div className="grid lg:grid-cols-[1fr_480px] gap-3 [&>*]:min-w-0">
      <Card>
        <CardContent className="p-4">
          {/* Su telefono gli indicatori stanno dietro «Strumenti», chiusi di
              default (richiesta del 2026-11-22), come nella scheda titolo. */}
          <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
            <RangeSelector
              value={range}
              onChange={(r) => setSearchParams({ range: r })}
            />
            <PulsanteStrumenti aperto={strumentiAperti} onCambia={() => setStrumentiAperti((o) => !o)} />
            <div className={cn(strumentiAperti ? "flex w-full" : "hidden", "sm:flex sm:w-auto items-center gap-2 flex-wrap")}>
              <span className="hidden md:block text-[0.7059rem] uppercase tracking-wider font-semibold text-muted-foreground shrink-0">
                Indicatori
              </span>
              <IndicatorToggles
                state={indicators}
                onChange={onIndicatorChange}
              />
            </div>
          </div>
          {d.bars.length < 2 ? (
            <div className="h-[460px] flex items-center justify-center text-sm text-muted-foreground border border-border/50 rounded-md">
              Dati insufficienti per il chart
            </div>
          ) : (
            <div className="h-[460px]">
              {/* `key={range}` forces a clean remount on range switch */}
              <MarketChart
                key={range}
                bars={d.bars}
                indicators={d.indicators}
                styles={{
                  ema20: indicators.ema20,
                  ema50: indicators.ema50,
                  ema200: indicators.ema200,
                  bb: indicators.bb,
                }}
                showVolume={hasVolume}
                timeframe={range}
                onReady={registerChart}
              />
            </div>
          )}

          {/* RSI subpanel — same convention as StockDetailPage. */}
          {indicators.rsi.visible && d.indicators.rsi14.length > 0 && (
            <div className="mt-3 h-[200px]">
              <RsiPanel
                key={range}
                rsi14={d.indicators.rsi14}
                color={indicators.rsi.color}
                width={indicators.rsi.width}
                onReady={registerChart}
              />
            </div>
          )}

          {/* MACD subpanel — togglable. */}
          {indicators.macd.visible && d.indicators.macd_line.length > 0 && (
            <div className="mt-3 h-[220px]">
              <MacdPanel
                key={range}
                line={d.indicators.macd_line}
                signal={d.indicators.macd_signal}
                hist={d.indicators.macd_hist}
                color={indicators.macd.color}
                width={indicators.macd.width}
                onReady={registerChart}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sidebar: technical KPI matrix + KPI summary + meta info.
          V3.5 alignment with stock-detail layout: the cross-timeframe
          matrix lives in TechnicalKpiCard (same component used by
          StockDetailPage) instead of the deprecated -3..+3 strip. */}
      <div className="space-y-3">
        <TechnicalKpiCard ticker={d.symbol} kind="market" />
        {/* FA-185: le statistiche al posto dei «KPI di prezzo» (massimi e
            minimi senza la distanza) e del riquadro «Meta». Altezza riservata:
            arrivano dopo il dettaglio, e il gate CLS misura lo spostamento. */}
        <Card>
          <CardContent className="p-4 min-h-[268px]">
            {statistiche.data ? (
              <StatisticheMercato s={statistiche.data} />
            ) : statistiche.isError ? (
              <p className="text-sm text-muted-foreground">Statistiche non disponibili.</p>
            ) : (
              <div className="h-[236px] animate-pulse rounded bg-muted/40" aria-hidden />
            )}
          </CardContent>
        </Card>
      </div>
      </div>

      {/* FA-185: il calendario dei rendimenti, anni per mesi. */}
      {statistiche.isLoading ? (
        <div className="h-[420px] animate-pulse rounded-lg bg-muted/30" aria-hidden />
      ) : statistiche.data && statistiche.data.calendario.anni.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <CalendarioRendimenti calendario={statistiche.data.calendario} />
          </CardContent>
        </Card>
      )}

      {/* News: per crypto e materie prime il prezzo segue un bene, e le
          notizie su quel bene sono il contesto che il grafico non da'.
          Altezza fissa: NewsCard riempie il contenitore e scorre dentro. */}
      {newsDelMercato(d.category) && (
        <div className="h-[420px]">
          <NewsCard ticker={d.symbol} />
        </div>
      )}
    </div>
  );
}


/** Format a market price by category. Indices and commodities at 2dp;
 *  crypto at variable precision (BTC at 0dp, low-cap cryptos at 4dp). */
