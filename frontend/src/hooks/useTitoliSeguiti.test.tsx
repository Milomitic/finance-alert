import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { pos } from "@/test/etoroFixture";

import { useTitoliSeguiti } from "./useTitoliSeguiti";

/* I «tuoi titoli» lato client: preferiti, posizioni manuali e, da FA-124,
 * posizioni eToro — queste solo se abbinate al catalogo, come nel server. */

vi.mock("@/hooks/usePreferiti", () => ({
  usePreferiti: () => ({ data: [{ ticker: "AAPL" }, { ticker: "SOXL" }], isError: false }),
}));
vi.mock("@/hooks/usePositions", () => ({
  usePositions: () => ({ data: [{ ticker: "MB.MI", closed_at: null }, { ticker: "OLD", closed_at: "2026-09-01" }] }),
}));
vi.mock("@/hooks/useEtoro", () => ({
  useEtoroPortafoglio: () => ({
    data: {
      aperte: [pos({ ticker: "SOXL" }), pos({ position_id: 2, ticker: null, simbolo: "RR" })],
    },
  }),
}));

describe("useTitoliSeguiti", () => {
  it("una posizione eToro abbinata vale come posizione, anche su un preferito", () => {
    const { result } = renderHook(() => useTitoliSeguiti());
    const m = result.current.titoli;
    expect(m.get("SOXL")).toBe("posizione");
    expect(m.get("AAPL")).toBe("preferito");
    expect(m.get("MB.MI")).toBe("posizione");
    // Chiusa o non abbinata: non conta.
    expect(m.has("OLD")).toBe(false);
    expect(m.has("RR")).toBe(false);
    expect(result.current.pronto).toBe(true);
  });
});
