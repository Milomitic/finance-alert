import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRitornoInPrimoPiano } from "./useRitornoInPrimoPiano";

/* FA-179, fase A: tornando sulla pagina dopo un minuto le query si
 * ricaricano subito; un cambio di scheda rapido non le tocca. */

let nascosta = false;
Object.defineProperty(document, "hidden", { configurable: true, get: () => nascosta });

function cambia(n: boolean) {
  nascosta = n;
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => {
  vi.useRealTimers();
  nascosta = false;
});

function monta() {
  const qc = new QueryClient();
  const spia = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  renderHook(() => useRitornoInPrimoPiano(), { wrapper });
  return spia;
}

describe("useRitornoInPrimoPiano", () => {
  it("dopo un minuto nascosta, al ritorno ricarica le query attive", () => {
    vi.useFakeTimers();
    const spia = monta();
    cambia(true);
    vi.advanceTimersByTime(61_000);
    cambia(false);
    expect(spia).toHaveBeenCalledWith({ refetchType: "active" });
  });

  it("un cambio di scheda rapido non ricarica niente", () => {
    vi.useFakeTimers();
    const spia = monta();
    cambia(true);
    vi.advanceTimersByTime(5_000);
    cambia(false);
    expect(spia).not.toHaveBeenCalled();
  });
});
