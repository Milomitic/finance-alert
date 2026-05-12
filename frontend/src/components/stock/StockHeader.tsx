import { Radio } from "lucide-react";

import type { OhlcvBar, Stock, StockKpis } from "@/api/types";
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
        <div className="flex items-start gap-6 flex-wrap">
          {/* Logo (V3.3: flag spostata dentro il tag exchange) */}
          <div className="flex flex-col items-center gap-2 shrink-0">
            <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-border/60 p-2 shadow-sm">
              <StockLogo ticker={stock.ticker} size="md" />
            </div>
          </div>

          {/* Identity */}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="text-4xl sm:text-5xl font-bold tracking-tight tabular-nums leading-none">
                {stock.ticker}
              </span>
              <span className="text-xl text-foreground/80 font-medium truncate" title={stock.name}>
                {stock.name}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              {/* V3.3: bandiera del paese ora dentro il tag exchange.
                  Compatto verticalmente (non più riga sotto il logo) e
                  semanticamente corretto: la bandiera identifica il
                  listing, che è proprietà dell'exchange. */}
              <span className="inline-flex items-center gap-1.5 rounded-md bg-muted/70 dark:bg-muted/40 px-2.5 py-1 text-sm font-medium">
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
              </span>
              {stock.sector && (
                <span className="inline-flex items-center rounded-md bg-muted/70 dark:bg-muted/40 px-2.5 py-1 text-sm font-medium">
                  {stock.sector}
                </span>
              )}
              {stock.industry && (
                <span className="text-sm text-muted-foreground truncate max-w-[420px]">
                  {stock.industry}
                </span>
              )}
            </div>
          </div>

          {/* Price block */}
          <div className="text-right tabular-nums shrink-0 flex flex-col gap-1 items-end">
            {displayPrice != null && (
              <>
                <div className="flex items-center gap-1.5 text-sm uppercase tracking-wide">
                  {isMarketOpen ? (
                    <span
                      className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300 font-semibold"
                      title={
                        liveAge != null
                          ? `Mercato aperto · prezzo aggiornato ${Math.round(liveAge)}s fa (cache 10s + polling 15s)`
                          : "Prezzo live"
                      }
                    >
                      <span className="relative inline-flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </span>
                      <Radio className="h-3 w-3" />
                      LIVE
                    </span>
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
            {/* V3.3: quando il mercato è aperto e il prezzo "live"
                differisce dalla chiusura precedente, mostra la previous
                close come contesto. La variazione % è già coperta
                sopra; questa caption fornisce il prezzo di partenza
                della giornata, utile per leggere la dimensione del
                movimento intraday. Nascosto a mercato chiuso (in quel
                caso il prezzo mostrato È già la chiusura). */}
            {isMarketOpen && live.data?.prev_close != null && (
              <div
                className="text-[11px] uppercase tracking-wider text-muted-foreground/80 mt-0.5"
                title="Chiusura della sessione di trading precedente — riferimento da cui calcolare la variazione intraday"
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
