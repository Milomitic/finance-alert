import type { LiveQuote, OhlcvBar } from "@/api/types";

/**
 * Merge the live quote into the OHLCV series so the rightmost candle reflects
 * the in-session price instead of yesterday's close.
 *
 * Why this is needed: for 1d/1w/1m/all the backend reads daily bars from the
 * DB, only refreshed by the EOD scan at 23:30. During the trading day the
 * latest stored bar is yesterday's close — the chart's last candle would
 * otherwise lag the live header price.
 *
 *  - 1d: if last.date is older than today, APPEND a new bar dated today with
 *    open/high/low/close synthesized from the live quote.
 *  - 1w / 1m / all: the last bar covers a multi-day range that includes today,
 *    so UPDATE its close (= live price) and extend high/low with today's
 *    session extremes.
 *
 * Intraday timeframes (5m / 30m / 1h) are excluded: those come straight from
 * yfinance and already include today's partial bar with live values. Volume is
 * intentionally left untouched for 1w/1m/all to avoid double-counting today.
 *
 * Pre-market caveat: yfinance's `day_open`/`day_high`/`day_low` still describe
 * YESTERDAY's regular session before today's open, so synthesizing the candle
 * from them rebuilds yesterday's bar verbatim — the "two identical candles"
 * bug. In PRE we instead open the new candle at the prior CLOSE (gap
 * continuity) and let the single evolving pre-market tick define its range.
 */
export function mergeLiveQuoteIntoOhlcv(
  ohlcv: OhlcvBar[],
  live: LiveQuote | undefined,
  range: string,
): OhlcvBar[] {
  if (range === "5m" || range === "30m" || range === "1h") return ohlcv;
  if (!live || live.price == null || ohlcv.length === 0) return ohlcv;
  const todayISO = new Date().toISOString().slice(0, 10);
  // Overlay the live quote whenever the backend says `price` is TODAY's value
  // — a genuine open session (OPEN/PRE) OR the post-close gap where the backend
  // serves today's official/provisional close (as_of_date === today). When
  // `price` is yesterday's close we DON'T overlay: appending an echo of the
  // last DB bar would just duplicate the rightmost candle.
  const showsToday =
    live.market_state === "OPEN" ||
    live.market_state === "PRE" ||
    live.as_of_date === todayISO;
  if (!showsToday) return ohlcv;

  const last = ohlcv[ohlcv.length - 1];
  const isPre = live.market_state === "PRE";
  // In PRE, day_open/high/low are stale (yesterday's session); anchor to the
  // prior close so we don't rebuild yesterday's candle.
  const liveOpen = isPre ? last.close : live.day_open ?? live.price;
  const liveHigh = isPre
    ? Math.max(last.close, live.price)
    : Math.max(live.day_high ?? live.price, live.price);
  const liveLow = isPre
    ? Math.min(last.close, live.price)
    : Math.min(live.day_low ?? live.price, live.price);

  if (range === "1d" && last.date < todayISO) {
    return [
      ...ohlcv,
      {
        date: todayISO,
        open: liveOpen,
        high: liveHigh,
        low: liveLow,
        close: live.price,
        volume: live.volume ?? 0,
      },
    ];
  }
  return [
    ...ohlcv.slice(0, -1),
    {
      ...last,
      close: live.price,
      high: Math.max(last.high, liveHigh),
      low: Math.min(last.low, liveLow),
    },
  ];
}
