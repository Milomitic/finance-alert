/* One owner for "render this number as money".
 *
 * There were THREE implementations and they disagreed. The screener carried a
 * symbol map and got it right; PositionsPage carried an `Intl` helper; the
 * stock detail page carried neither and hard-coded `$` in a dozen places,
 * while 312 of the 1010 catalogued stocks are quoted in pounds, euros, Hong
 * Kong dollars, yen or won. For roughly a third of the universe the symbol
 * beside the price was not ambiguous, it was WRONG.
 *
 * This is the frontend twin of `currency_units` on the backend, which
 * consolidated the same problem after finding the pence logic quintuplicated
 * across five services.
 *
 * ⚠️ Three rules, each of which a plausible implementation gets wrong:
 *
 * 1. **A missing currency must NOT become USD.** PositionsPage's helper read
 *    `currency && /^[A-Z]{3}$/.test(currency) ? currency : "USD"`, which does
 *    two damaging things at once: it prints dollars for a stock whose currency
 *    simply was not loaded, and — because the regex demands three UPPERCASE
 *    letters — it rejects yfinance's `GBp` and prints dollars for a London
 *    stock specifically. `fx_service` settled this on the backend in the same
 *    words: an unresolvable currency is UNKNOWN and the caller shows nothing.
 *
 * 2. **Symbols must stay distinct.** `Intl`'s `currencyDisplay: "narrowSymbol"`
 *    looks like the obvious way to get "$" instead of "USD" and collapses USD,
 *    HKD and AUD into a single "$" — reintroducing the whole problem on the 59
 *    Hong Kong names in the catalog. The map below keeps them apart, and so
 *    does `CN¥` against `¥`.
 *
 * 3. **`GBp` is a LABEL problem, never a value one.** Stored LSE prices are
 *    already pounds; the pence→pounds division happens once, at ingest. This
 *    module relabels and never divides.
 */

/** yfinance's spellings for London pence. Mirrors the backend tuple in
 *  `currency_units.MINOR_UNIT_CURRENCIES`. */
const MINOR_UNITS = new Set(["GBp", "GBX"]);

/** ISO-4217 shape: exactly three letters. */
const ISO_4217 = /^[A-Za-z]{3}$/;

/** Symbols for the currencies this catalog actually holds, plus the majors.
 *  Promoted verbatim from the screener's `CURRENCY_SYMBOL`, which is where
 *  this app first got it right — with one correction: `CNY` was `¥`, the same
 *  glyph as `JPY`, so a yuan price and a yen price rendered identically. */
const SYMBOLS: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", CHF: "CHF",
  CAD: "C$", AUD: "A$", HKD: "HK$", CNY: "CN¥", KRW: "₩",
  NOK: "NKr", SEK: "SKr", DKK: "DKr", SGD: "S$", NZD: "NZ$",
  ZAR: "R", INR: "₹", BRL: "R$", MXN: "MX$", PLN: "zł",
};

/** The code a stored value should be DISPLAYED under.
 *
 *  Returns null when there is nothing trustworthy to show — the correct answer
 *  for market assets, since an index level and an FX cross are not denominated
 *  in anything and inventing a unit would be a claim the data does not make. */
export function displayCurrency(currency: string | null | undefined): string | null {
  if (!currency) return null;
  if (MINOR_UNITS.has(currency)) return "GBP";
  if (!ISO_4217.test(currency)) return null;
  return currency.toUpperCase();
}

/** The symbol to put in front of a figure, or the ISO code with a trailing
 *  space when no widely-recognized symbol exists. "HKD 18.40" beats both
 *  "? 18.40" and a bare number.
 *
 *  Null when the currency is unknown — the caller then renders the number
 *  bare rather than borrowing someone else's unit. */
export function currencySymbol(currency: string | null | undefined): string | null {
  const code = displayCurrency(currency);
  if (!code) return null;
  return SYMBOLS[code] ?? `${code} `;
}

/** Decimals by magnitude: a 0.0234 penny stock or FX cross collapses to
 *  "0.02" at two digits, losing the part that moves.
 *
 *  Zero is excluded deliberately. It is "below 1" arithmetically and has no
 *  small part to preserve, so the extra digits buy nothing and "$0.0000" reads
 *  like a precision claim about a number that carries none. */
function decimalsFor(value: number): number {
  return value !== 0 && Math.abs(value) < 1 ? 4 : 2;
}

/** Format a value as money in its own currency: `$35.04`, `£13.44`,
 *  `HK$120.00`, `KRW 71300.00`.
 *
 *  With no usable currency the number is returned BARE. A caller that needs to
 *  say "unknown" should say it in words beside the number, not by borrowing a
 *  currency.
 */
export function formatMoney(
  value: number | null | undefined,
  currency: string | null | undefined,
  opts: { decimals?: number } = {},
): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const digits = opts.decimals ?? decimalsFor(value);
  return `${currencySymbol(currency) ?? ""}${value.toFixed(digits)}`;
}

/** Signed variant, for a change or a P&L where the direction is the point.
 *  The sign leads the symbol (`+$1.20`, `-£0.35`) so a column of them stays
 *  scannable down the sign column. */
export function formatMoneySigned(
  value: number | null | undefined,
  currency: string | null | undefined,
  opts: { decimals?: number } = {},
): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatMoney(Math.abs(value), currency, opts)}`;
}
