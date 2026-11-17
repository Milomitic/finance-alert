import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useTitoloScheda } from "./useTitoloScheda";

describe("useTitoloScheda", () => {
  it("scrive il titolo della scheda per una pagina di dettaglio", () => {
    renderHook(() => useTitoloScheda("AAPL"));
    expect(document.title).toBe("AAPL · Finance-Alert");
  });

  it("senza testo non tocca il titolo", () => {
    document.title = "Screener · Finance-Alert";
    renderHook(() => useTitoloScheda(null));
    expect(document.title).toBe("Screener · Finance-Alert");
  });
});
