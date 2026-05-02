import { useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  ticker: string | null | undefined;
  size?: "xs" | "sm" | "md";
}

const SIZE_PX: Record<NonNullable<Props["size"]>, number> = {
  xs: 20,
  sm: 26,
  md: 34,
};

/**
 * Strip yfinance exchange suffix (AAPL.MX -> AAPL, ENI.MI -> ENI, 600519.SS -> 600519).
 * The fmp endpoint expects the base ticker for US stocks; for non-US tickers
 * it usually 404s and we fall through to the initials avatar.
 */
function logoUrl(ticker: string): string {
  const base = ticker.split(".")[0];
  return `https://financialmodelingprep.com/image-stock/${base}.png`;
}

/**
 * Deterministic HSL colour from ticker hash — same ticker always gets the
 * same colour. Range avoids dark/desaturated colours so the white initial
 * letter stays legible.
 */
function colorForTicker(ticker: string): string {
  let hash = 0;
  for (let i = 0; i < ticker.length; i++) {
    hash = (hash * 31 + ticker.charCodeAt(i)) | 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}deg 55% 45%)`;
}

export function StockLogo({ ticker, size = "sm" }: Props) {
  const [errored, setErrored] = useState(false);
  if (!ticker) return null;
  const px = SIZE_PX[size];

  if (errored) {
    return (
      <span
        className="inline-flex items-center justify-center rounded-full text-white font-bold shrink-0"
        style={{
          width: px,
          height: px,
          backgroundColor: colorForTicker(ticker),
          fontSize: Math.round(px * 0.4),
        }}
        title={ticker}
        aria-label={`${ticker} logo`}
      >
        {ticker.split(".")[0].slice(0, 2).toUpperCase()}
      </span>
    );
  }

  return (
    <img
      src={logoUrl(ticker)}
      alt={`${ticker} logo`}
      width={px}
      height={px}
      onError={() => setErrored(true)}
      className={cn("rounded-full bg-white border border-border/50 shrink-0")}
      style={{ width: px, height: px, objectFit: "contain" }}
      loading="lazy"
    />
  );
}
