import { Building2 } from "lucide-react";
import { useEffect, useState } from "react";

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
 * CDN chain for stock logos. Tries each in order, falling through on 404.
 * Probed coverage:
 *   - parqet (full ticker, e.g. ENI.MI, 0688.HK): best EU/HK/CN coverage
 *   - parqet (ticker base, e.g. STLA): catches stocks listed on multiple exchanges
 *     where parqet only has the US listing
 *   - FMP (bare ticker, e.g. AAPL): good US coverage
 */
function logoSources(ticker: string): string[] {
  const base = ticker.split(".")[0];
  const enc = encodeURIComponent(ticker);
  const encBase = encodeURIComponent(base);
  return [
    `https://assets.parqet.com/logos/symbol/${enc}`,
    base !== ticker ? `https://assets.parqet.com/logos/symbol/${encBase}` : null,
    `https://financialmodelingprep.com/image-stock/${encBase}.png`,
  ].filter((u): u is string => u !== null);
}

export function StockLogo({ ticker, size = "sm" }: Props) {
  const [srcIdx, setSrcIdx] = useState(0);
  const [exhausted, setExhausted] = useState(false);

  // Reset state when ticker changes (e.g. row in a list re-renders with new ticker)
  useEffect(() => {
    setSrcIdx(0);
    setExhausted(false);
  }, [ticker]);

  if (!ticker) return null;
  const px = SIZE_PX[size];
  const sources = logoSources(ticker);

  if (exhausted) {
    return (
      <span
        className="inline-flex items-center justify-center rounded-full bg-muted/60 text-muted-foreground shrink-0"
        style={{ width: px, height: px }}
        title={ticker}
        aria-label={`${ticker} logo unavailable`}
      >
        <Building2 style={{ width: px * 0.55, height: px * 0.55 }} />
      </span>
    );
  }

  return (
    <img
      src={sources[srcIdx]}
      alt={`${ticker} logo`}
      width={px}
      height={px}
      onError={() => {
        if (srcIdx < sources.length - 1) {
          setSrcIdx(srcIdx + 1);
        } else {
          setExhausted(true);
        }
      }}
      className={cn("rounded-full bg-white border border-border/50 shrink-0")}
      style={{ width: px, height: px, objectFit: "contain" }}
      loading="lazy"
    />
  );
}
