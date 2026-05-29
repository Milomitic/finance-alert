import { Link } from "react-router-dom";

import type { OhlcvBar, Stock, StockKpis } from "@/api/types";
import { MarketStateBadge } from "@/components/dashboard/MarketStateBadge";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { useLiveQuote } from "@/hooks/useLiveQuote";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

interface Props {
  stock: Stock;
  kpis: StockKpis;
  /** Optional OHLCV history — drawn as a faded sparkline background. */
  ohlcv?: OhlcvBar[];
}

/**
 * Faded sparkline background. Renders absolute inset-0 behind the header
 * content so the page hero feels like a "ticker tape" — the price-trend
 * shape is always visible at a glance, but never competes with the foreground
 * text. Color follows the day's % change (green up / red down).
 */
export function HeaderSparkline({ closes, up }: { closes: number[]; up: boolean }) {
  if (closes.length < 2) return null;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 100;
  const H = 30;
  const points = closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  // Fill area under the line for stronger background presence
  const areaPath = `M0,${H} L${points} L${W},${H} Z`;
  const stroke = up ? "#16a34a" : "#dc2626";
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        {/* V3.3 area gradient: la zona sopra la linea resta totalmente
            trasparente (non disegnata); la zona sotto la linea (il
            "fill di integrale") parte dalla linea con opacità medio-
            alta e dissolve verso il basso del grafico. Effetto
            classico delle dashboard finanziarie tipo Robinhood/eToro:
            la linea ha una scia colorata che si fonde col background. */}
        <linearGradient id="hdr-spark-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.40} />
          <stop offset="60%" stopColor={stroke} stopOpacity={0.12} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
        <linearGradient id="hdr-spark-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0.85} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#hdr-spark-area)" />
      <polyline
        points={points}
        fill="none"
        stroke="url(#hdr-spark-line)"
        strokeWidth={1.2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function StockHeader({ stock, kpis, ohlcv }: Props) {
  const flag = getStockFlagCode(stock.country, stock.ticker);

  // Live quote — polls every 15s. Falls back to the kpis snapshot (last
  // close from the daily scan) when the live fetch hasn't returned yet,
  // when it errored (e.g. yfinance breaker open), or when the live price
  // isn't available (e.g. delisted ticker).
  const live = useLiveQuote(stock.ticker);
  const liveOk = live.data && live.data.price != null && live.data.error == null;
  const isMarketOpen = liveOk && live.data!.market_state === "OPEN";
  // US pre-market: the live price is a pre-open quote and `change_pct` is the
  // pre-open move vs yesterday's close. Without flagging this, the price block
  // would read "Ultima chiusura" over a live pre-market figure — exactly the
  // ambiguity the PRE badge resolves on the dashboard cards.
  const isPremarket = liveOk && live.data!.market_state === "PRE";
  const displayPrice = liveOk ? live.data!.price! : kpis.last_close;
  const change = liveOk ? (live.data!.change_pct ?? null) : kpis.change_pct;
  const changeAbs = liveOk ? live.data!.change_abs : null;
  const liveAge = liveOk ? Date.now() / 1000 - live.data!.fetched_at : null;

  // Tone: stripe on left + text accent. Card background stays neutral
  // (`bg-card`) so only the SVG sparkline's area gradient colors the
  // pixels UNDER the chart line — the area ABOVE the line (where the
  // ticker / name / price text sits) stays clean white. The previous
  // `bg-emerald-50/50` tint covered the whole card uniformly,
  // contradicting the gradient's "fade only beneath the line" intent.
  const tone =
    change == null
      ? { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" }
      : change > 0
        ? { bg: "bg-card", stripe: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300", arrow: "▲" }
        : change < 0
          ? { bg: "bg-card", stripe: "bg-rose-500", text: "text-rose-700 dark:text-rose-300", arrow: "▼" }
          : { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" };

  const closes = (ohlcv ?? []).map((b) => b.close).filter((c) => Number.isFinite(c));
  const sparkUp = (change ?? 0) >= 0;

  return (
    <Card className={cn("relative overflow-hidden border-border/60", tone.bg)}>
      {/* Sparkline behind everything */}
      <HeaderSparkline closes={closes} up={sparkUp} />
      <div className={cn("absolute left-0 top-0 bottom-0 w-1.5 z-10", tone.stripe)} aria-hidden />
      {/* Smaller padding now that the KPI strip is gone */}
      <CardContent className="relative z-10 p-5 pl-7">
        <div className="flex items-center gap-6 flex-wrap">
          {/* Logo (V3.3: flag spostata dentro il tag exchange) */}
          <div className="flex flex-col items-center gap-2 shrink-0">
            <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-border/60 p-2 shadow-sm">
              <StockLogo ticker={stock.ticker} size="md" />
            </div>
          </div>

          {/* Identity */}
          <div className="min-w-0">
            <div className="flex flex-col gap-1">
              <span className="text-3xl sm:text-4xl font-bold tracking-tight tabular-nums leading-none">
                {stock.ticker}
              </span>
              <span className="text-xl text-foreground/80 font-medium truncate" title={stock.name}>
                {stock.name}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              {/* Exchange / indice di riferimento — cliccabile: porta allo
                  screener filtrato per questa borsa. La bandiera del paese
                  vive dentro il tag (il listing è proprietà dell'exchange). */}
              <Link
                to={`/stocks?exchange=${encodeURIComponent(stock.exchange)}`}
                title={`Vedi i titoli su ${stock.exchange}`}
                className="inline-flex items-center gap-1.5 rounded-md bg-muted/70 dark:bg-muted/40 hover:bg-muted px-2.5 py-1 text-sm font-medium transition-colors"
              >
                {flag && (
                  <img
                    src={`/flags/${flag}.svg`}
                    alt={stock.country ?? ""}
                    width={18}
                    height={12}
                    style={{ width: "18px", height: "12px", objectFit: "cover" }}
                    className="rounded-sm shadow-sm"
                    aria-hidden
                  />
                )}
                {stock.exchange}
              </Link>
              {/* Settore — cliccabile: porta alla pagina di dettaglio settore. */}
              {stock.sector && (
                <Link
                  to={`/sectors/${encodeURIComponent(stock.sector)}`}
                  title={`Vedi il settore ${stock.sector}`}
                  className="inline-flex items-center rounded-md bg-muted/70 dark:bg-muted/40 hover:bg-muted px-2.5 py-1 text-sm font-medium transition-colors"
                >
                  {stock.sector}
                </Link>
              )}
            </div>
          </div>

          {/* Price block — moved next to the identity (left-aligned), both
              vertically centered via the row's items-center. Extra left margin
              gives a bit more breathing room between the name and the price. */}
          <div className="text-left tabular-nums shrink-0 flex flex-col gap-1 items-start sm:ml-12">
            {displayPrice != null && (
              <>
                <div className="flex items-center gap-1.5 text-sm uppercase tracking-wide">
                  {isMarketOpen ? (
                    <MarketStateBadge
                      phase="open"
                      size="md"
                      title={
                        liveAge != null
                          ? `Mercato aperto · prezzo aggiornato ${Math.round(liveAge)}s fa (cache 10s + polling 15s)`
                          : "Prezzo live"
                      }
                    />
                  ) : isPremarket ? (
                    <MarketStateBadge
                      phase="pre"
                      size="md"
                      title={
                        liveAge != null
                          ? `Pre-market USA · la variazione è il movimento pre-apertura vs chiusura di ieri · aggiornato ${Math.round(liveAge)}s fa`
                          : "Pre-market USA — la variazione mostrata è il movimento pre-apertura rispetto alla chiusura di ieri"
                      }
                    />
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-muted-foreground font-semibold"
                      title={
                        liveOk
                          ? "Mercato chiuso — il prezzo mostrato è l'ultima chiusura"
                          : "Live quote non disponibile — mostra l'ultima chiusura giornaliera"
                      }
                    >
                      Ultima chiusura
                    </span>
                  )}
                </div>
                <FlashValue value={displayPrice} format={(v) => `$${v.toFixed(2)}`} className="text-5xl font-bold leading-none" />
              </>
            )}
            {change != null && (
              <div className={cn("inline-flex items-baseline gap-1.5 text-2xl font-bold mt-1", tone.text)}>
                <span className="text-lg">{tone.arrow}</span>
                {changeAbs != null && (
                  <span className="text-base font-semibold opacity-80">
                    {changeAbs >= 0 ? "+" : ""}{changeAbs.toFixed(2)}
                  </span>
                )}
                <span>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span>
              </div>
            )}
            {/* V3.3: quando il mercato è aperto (o in pre-market) e il
                prezzo "live" differisce dalla chiusura precedente, mostra
                la previous close come contesto. La variazione % è già
                coperta sopra; questa caption fornisce il prezzo di
                riferimento da cui si calcola il movimento. In pre-market
                è la base del movimento pre-apertura; intraday è il prezzo
                di partenza della giornata. Nascosto a mercato chiuso (in
                quel caso il prezzo mostrato È già la chiusura). */}
            {(isMarketOpen || isPremarket) && live.data?.prev_close != null && (
              <div
                className="text-[11px] uppercase tracking-wider text-muted-foreground/80 mt-0.5"
                title={
                  isPremarket
                    ? "Chiusura di ieri — riferimento da cui si calcola il movimento pre-apertura"
                    : "Chiusura della sessione di trading precedente — riferimento da cui calcolare la variazione intraday"
                }
              >
                Prev close:{" "}
                <span className="text-foreground/80 font-semibold tabular-nums">
                  ${live.data.prev_close.toFixed(2)}
                </span>
              </div>
            )}
          </div>
        </div>

      </CardContent>
    </Card>
  );
}
