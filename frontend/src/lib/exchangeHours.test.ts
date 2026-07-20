import { describe, expect, it } from "vitest";

import { exchangeTimezone } from "@/lib/exchangeHours";

describe("exchangeTimezone", () => {
  it("maps US listings (no suffix) to New York", () => {
    expect(exchangeTimezone("AAPL")).toBe("America/New_York");
    expect(exchangeTimezone("BRK-B")).toBe("America/New_York");
  });

  it("maps known exchange suffixes to their IANA zone", () => {
    expect(exchangeTimezone("HSBA.L")).toBe("Europe/London");
    expect(exchangeTimezone("ENEL.MI")).toBe("Europe/Berlin");
    expect(exchangeTimezone("0700.HK")).toBe("Asia/Hong_Kong");
    expect(exchangeTimezone("000300.SS")).toBe("Asia/Shanghai");
    expect(exchangeTimezone("7203.T")).toBe("Asia/Tokyo");
    expect(exchangeTimezone("EQNR.OL")).toBe("Europe/Oslo");
    expect(exchangeTimezone("BHP.AX")).toBe("Australia/Sydney");
  });

  it("falls back to US for an unknown suffix or empty input", () => {
    expect(exchangeTimezone("FOO.ZZ")).toBe("America/New_York");
    expect(exchangeTimezone("")).toBe("America/New_York");
    expect(exchangeTimezone(null)).toBe("America/New_York");
    expect(exchangeTimezone(undefined)).toBe("America/New_York");
  });
});
