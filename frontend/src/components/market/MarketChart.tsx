import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import { OhlcLegend, barToLegend, type LegendDatum } from "@/components/chart/ohlcLegend";
import type { IndicatorStyle } from "@/components/stock/IndicatorToggles";
import type { RegisterChart } from "@/hooks/useChartSync";
import type { MarketDetailBar, MarketIndicatorPoint, MarketIndicators } from "@/hooks/useMarketDetail";
import { defaultVisibleBars, isIntraday } from "@/lib/timeframeZoom";

interface Props {
  bars: MarketDetailBar[];
  indicators?: MarketIndicators;
  styles?: {
    ema20: IndicatorStyle;
    ema50: IndicatorStyle;
    ema200: IndicatorStyle;
    bb: IndicatorStyle;
  };
  showVolume?: boolean;
  timeframe?: string;
  onReady?: RegisterChart;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

function pointsToChartData(points: MarketIndicatorPoint[] | undefined) {
  if (!points) return [];
  return points
    .filter((p) => p.value !== null)
    .map((p) => ({ time: dateToTime(p.date), value: p.value as number }));
}

// Candlestick + indicator overlay chart for the MarketDetailPage.
// Same indicator capability as PriceChart: EMA20/50/200, Bollinger
// Bands, optional volume, plus chart-sync hooks for RSI/MACD subpanels.
export function MarketChart({
  bars,
  indicators,
  styles,
  showVolume = true,
  timeframe,
  onReady,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  // OHLC legend machinery — same pattern as PriceChart (shared renderer in
  // components/chart/ohlcLegend). Refs because the crosshair handler is
  // registered once at chart mount and must not close over stale snapshots.
  const barsByTimeRef = useRef<Map<number, MarketDetailBar & { idx: number }>>(new Map());
  const barsRef = useRef<MarketDetailBar[]>([]);
  const timeframeRef = useRef<string | undefined>(timeframe);
  const latestLegendRef = useRef<LegendDatum | null>(null);
  const [legend, setLegend] = useState<LegendDatum | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMiddleRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      // autoSize: width/height below are read ONCE at creation, so without
      // this the canvas kept its mount-time size forever — a rotation or any
      // container change left it the wrong width. The explicit sizes stay as
      // the documented fallback for when ResizeObserver is unavailable.
      autoSize: true,
      width: el.clientWidth,
      height: el.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(115, 115, 115, 1)",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(115, 115, 115, 0.08)" },
        horzLines: { color: "rgba(115, 115, 115, 0.08)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(115, 115, 115, 0.2)" },
      timeScale: {
        borderColor: "rgba(115, 115, 115, 0.2)",
        // ALL three intraday timeframes need the clock on the axis — "5m" was
        // missing here, so a 5m chart fell back to the date-only formatter and
        // every tick of the same session rendered the identical "28" / "29".
        // With timeVisible the library labels intra-session ticks "09:35" and
        // keeps the date only on day boundaries.
        //
        // No custom tickMarkFormatter on purpose (PriceChart has one): market
        // assets are indices / FX / crypto with no single exchange timezone,
        // so the axis stays in UTC — which is exactly what the shared OHLC
        // legend does for these bars (`formatBarDate` defaults tz="UTC").
        // Axis and legend must agree; adding a local-tz formatter here would
        // desync them.
        // Letto dal ref: l'orologio sull'asse viene poi RIAPPLICATO
        // dall'effetto qui sotto a ogni cambio di intervallo, quindi la
        // creazione non dipende dalla prop. Al montaggio il ref e' gia'
        // inizializzato col valore corrente.
        timeVisible: isIntraday(timeframeRef.current),
        secondsVisible: false,
      },
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: "#17b551",
      downColor: "#dc2626",
      borderUpColor: "#17b551",
      borderDownColor: "#dc2626",
      wickUpColor: "#17b551",
      wickDownColor: "#dc2626",
    });
    ema20Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    ema50Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    ema200Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    bbUpperRef.current = chart.addLineSeries({ lineStyle: 2, priceLineVisible: false, lastValueVisible: true });
    bbLowerRef.current = chart.addLineSeries({ lineStyle: 2, priceLineVisible: false, lastValueVisible: true });
    bbMiddleRef.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });

    if (showVolume) {
      volumeRef.current = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
        color: "rgba(115, 115, 115, 0.4)",
      });
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });
    }

    const ro = new ResizeObserver(() => {
      if (!chartRef.current || !containerRef.current) return;
      chartRef.current.resize(
        containerRef.current.clientWidth,
        containerRef.current.clientHeight,
      );
    });
    ro.observe(el);

    // Crosshair → legend: hovered bar while over a candle, latest bar when
    // the cursor leaves the plot (the corner always shows something).
    const crosshairHandler = (param: { time?: Time }) => {
      if (!param.time) {
        setLegend(latestLegendRef.current);
        return;
      }
      const bar = barsByTimeRef.current.get(param.time as number);
      if (!bar) {
        setLegend(latestLegendRef.current);
        return;
      }
      const prevBar = bar.idx > 0 ? barsRef.current[bar.idx - 1] : null;
      setLegend(barToLegend(bar, prevBar, timeframeRef.current));
    };
    chart.subscribeCrosshairMove(crosshairHandler);

    const unregister = onReady?.(chart);

    return () => {
      unregister?.();
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      bbUpperRef.current = null;
      bbMiddleRef.current = null;
      bbLowerRef.current = null;
      volumeRef.current = null;
    };
  }, [showVolume, onReady]);

  /* ⚠️ L'orologio sull'asse va RIAPPLICATO, non solo impostato alla nascita.
   *
   * Il grafico si crea una volta sola (`[showVolume, onReady]`), quindi
   * passando da giornaliero a 30m l'asse restava senza ore: le barre
   * diventavano intraday e le etichette continuavano a mostrare solo la data.
   * Difetto reale e PLAUSIBILE — un asse con sole date non sembra rotto — ed
   * e' precisamente cio' che `exhaustive-deps` stava segnalando su
   * `timeframe`. La regola aveva ragione; la correzione non era pero'
   * aggiungere la dipendenza, che avrebbe ricostruito tutto il grafico. */
  useEffect(() => {
    chartRef.current?.applyOptions({
      timeScale: { timeVisible: isIntraday(timeframe) },
    });
  }, [timeframe]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    // Keep the legend lookups in sync with the data (handler closes over
    // refs registered at mount).
    timeframeRef.current = timeframe;
    barsRef.current = bars;
    const map = new Map<number, MarketDetailBar & { idx: number }>();
    bars.forEach((b, idx) => {
      map.set(dateToTime(b.date) as unknown as number, { ...b, idx });
    });
    barsByTimeRef.current = map;
    const lastBar = bars[bars.length - 1];
    const prevOfLast = bars.length > 1 ? bars[bars.length - 2] : null;
    const latest = lastBar ? barToLegend(lastBar, prevOfLast, timeframe) : null;
    latestLegendRef.current = latest;
    setLegend(latest);
    candle.setData(
      bars.map((b) => ({
        time: dateToTime(b.date),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    if (showVolume && volumeRef.current) {
      volumeRef.current.setData(
        bars
          .filter((b) => b.volume != null && b.volume > 0)
          .map((b) => ({
            time: dateToTime(b.date),
            value: b.volume as number,
            color: b.close >= b.open ? "rgba(22, 163, 74, 0.35)" : "rgba(220, 38, 38, 0.35)",
          })),
      );
    }
    const ts = chartRef.current?.timeScale();
    if (!ts) return;
    const n = defaultVisibleBars(timeframe);
    if (n !== null && bars.length > n) {
      ts.setVisibleLogicalRange({ from: bars.length - n, to: bars.length - 1 });
    } else {
      ts.fitContent();
    }
  }, [bars, showVolume, timeframe]);

  /* ⚠️ Le FETTE si estraggono qui, fuori dagli effetti.
   *
   * Prima ogni effetto leggeva `indicators` e `styles` interi e dichiarava
   * come dipendenza la sola fetta che gli interessava: le due cose non
   * coincidevano, ed e' esattamente cio' che `exhaustive-deps` segnalava.
   *
   * ⚠️ La correzione NON e' aggiungere gli oggetti alle dipendenze: cosi'
   * cambiare il colore delle Bollinger rieseguirebbe anche i tre effetti
   * delle EMA, che ricaricherebbero i loro dati per niente. L'intento
   * originale — «reagisci solo alla tua fetta» — era giusto; mancava solo di
   * scriverlo in modo che il corpo dell'effetto leggesse davvero solo quella. */
  const datiEma20 = indicators?.ema20;
  const datiEma50 = indicators?.ema50;
  const datiEma200 = indicators?.ema200;
  const datiBbAlta = indicators?.bb_upper;
  const datiBbMedia = indicators?.bb_middle;
  const datiBbBassa = indicators?.bb_lower;
  const stileEma20 = styles?.ema20;
  const stileEma50 = styles?.ema50;
  const stileEma200 = styles?.ema200;
  const stileBb = styles?.bb;

  useEffect(() => {
    const serie = ema20Ref.current;
    if (!serie || !datiEma20) return;
    if (stileEma20) {
      serie.applyOptions({
        visible: stileEma20.visible,
        color: stileEma20.color,
        lineWidth: stileEma20.width as 1 | 2 | 3 | 4,
      });
    }
    serie.setData(pointsToChartData(datiEma20));
  }, [datiEma20, stileEma20]);

  useEffect(() => {
    const serie = ema50Ref.current;
    if (!serie || !datiEma50) return;
    if (stileEma50) {
      serie.applyOptions({
        visible: stileEma50.visible,
        color: stileEma50.color,
        lineWidth: stileEma50.width as 1 | 2 | 3 | 4,
      });
    }
    serie.setData(pointsToChartData(datiEma50));
  }, [datiEma50, stileEma50]);

  useEffect(() => {
    const serie = ema200Ref.current;
    if (!serie || !datiEma200) return;
    if (stileEma200) {
      serie.applyOptions({
        visible: stileEma200.visible,
        color: stileEma200.color,
        lineWidth: stileEma200.width as 1 | 2 | 3 | 4,
      });
    }
    serie.setData(pointsToChartData(datiEma200));
  }, [datiEma200, stileEma200]);

  useEffect(() => {
    const alta = bbUpperRef.current;
    const media = bbMiddleRef.current;
    const bassa = bbLowerRef.current;
    if (!alta || !media || !bassa) return;
    if (!datiBbAlta || !datiBbMedia || !datiBbBassa) return;
    if (stileBb) {
      const w = stileBb.width as 1 | 2 | 3 | 4;
      for (const serie of [alta, media, bassa]) {
        serie.applyOptions({ visible: stileBb.visible, color: stileBb.color, lineWidth: w });
      }
    }
    alta.setData(pointsToChartData(datiBbAlta));
    media.setData(pointsToChartData(datiBbMedia));
    bassa.setData(pointsToChartData(datiBbBassa));
  }, [datiBbAlta, datiBbMedia, datiBbBassa, stileBb]);

  return (
    <div ref={containerRef} className="h-full w-full relative">
      <OhlcLegend legend={legend} />
    </div>
  );
}
