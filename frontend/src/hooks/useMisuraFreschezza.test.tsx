import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const inviate: [string, number][] = [];
vi.mock("@/lib/rum", () => ({ report: (m: string, v: number) => inviate.push([m, v]) }));

const { useMisuraFreschezza } = await import("./useMisuraFreschezza");
const { QUERY_CRITICHE_HOME } = await import("@/lib/freschezzaHome");

/* FA-179, fase D: la misura parte solo quando TUTTE le query critiche hanno
 * un dato ricevuto in questa visita, e una volta per caricamento. */

describe("useMisuraFreschezza", () => {
  it("invia DATI_FRESCHI quando tutte le query critiche sono arrivate, una volta", () => {
    const qc = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const { rerender } = renderHook(() => useMisuraFreschezza(), { wrapper });
    expect(inviate).toEqual([]);
    for (const c of QUERY_CRITICHE_HOME) qc.setQueryData(c.chiave, { ok: true });
    rerender();
    rerender();
    expect(inviate.filter(([m]) => m === "DATI_FRESCHI")).toHaveLength(1);
  });
});
