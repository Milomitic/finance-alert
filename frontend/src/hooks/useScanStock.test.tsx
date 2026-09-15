import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { CHIAVI_DOPO_SCAN_LOCALE, useScanStock } from "./useAlertMutations";

/* FA-072. «Processa segnali» su un titolo creava alert e setup in modo
 * sincrono, ma invalidava soltanto il dettaglio titolo: la lista Segnali — e
 * perfino la scheda «Storico completo» della stessa card — restava quella di
 * prima finche' non passava lo scan dell'universo. */

const api = vi.fn();
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: (...a: unknown[]) => api(...a) };
});
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const SORGENTI = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function avvolto() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalida = vi.spyOn(qc, "invalidateQueries");
  const scrive = vi.spyOn(qc, "setQueryData");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { wrapper, invalida, scrive };
}

describe("dopo lo scan di un titolo", () => {
  it("invalida la lista globale e lo storico completo, non solo il dettaglio", async () => {
    api.mockResolvedValue({ added: 2, total: 9 });
    const { wrapper, invalida } = avvolto();
    const { result } = renderHook(() => useScanStock("AAPL"), { wrapper });

    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const chiavi = invalida.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    // Il difetto: prima c'era soltanto questa.
    expect(chiavi).toContain(JSON.stringify(["stock-detail", "AAPL"]));
    // Le due liste che la voce nomina.
    expect(chiavi).toContain(JSON.stringify(["alerts"]));
    expect(chiavi).toContain(JSON.stringify(["alert-storico", "AAPL"]));
    expect(chiavi).toHaveLength(CHIAVI_DOPO_SCAN_LOCALE("AAPL").length);
  });

  it("⚠️ NON finge una scansione dell'universo", async () => {
    /* Quella transizione porta il toast «Scan completato» e la contabilita' di
     * fine giro, che uno scan locale per perimetro non deve fare (FA-062). Il
     * modo sbagliato di chiudere FA-072 sarebbe scrivere nello stato dello scan
     * per far scattare `useScanStatus`. */
    api.mockResolvedValue({ added: 1, total: 3 });
    const { wrapper, scrive } = avvolto();
    const { result } = renderHook(() => useScanStock("AAPL"), { wrapper });

    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(scrive).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("un errore non invalida niente", async () => {
    // Il finto restituisce sempre: a lanciare e' il guscio, non il vi.fn()
    // (CLAUDE.md, «vi.fn() che lancia fa fallire il test anche quando
    // l'errore E' gestito»).
    api.mockImplementation(async () => {
      throw new Error("422");
    });
    const { wrapper, invalida } = avvolto();
    const { result } = renderHook(() => useScanStock("AAPL"), { wrapper });

    await act(async () => {
      result.current.mutate();
    });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalida).not.toHaveBeenCalled();
  });
});

describe("censimento: nessuna lista di segnali o setup resta fuori", () => {
  /* ⚠️ L'elenco e' scritto a mano, e un elenco a mano invecchia alla prossima
   * query nuova — che e' come la scheda «Storico completo» era rimasta fuori.
   * Si censiscono le radici delle chiavi di query nei sorgenti e si pretende
   * che quelle che dipendono da alert o setup siano coperte, oppure esentate
   * con una ragione. */
  const ESENTATE: Record<string, string> = {
    "price-alerts": "gli alert di PREZZO non li crea il motore dei segnali",
  };

  it("il censimento trova davvero delle chiavi", () => {
    const radici = radiciDelleChiavi();
    expect(radici.size).toBeGreaterThan(20);
  });

  it("ogni radice che parla di alert o setup e' invalidata o esentata", () => {
    const coperte = new Set<string>(CHIAVI_DOPO_SCAN_LOCALE("X").map((k) => k[0]));
    const scoperte = [...radiciDelleChiavi()]
      .filter((r) => /alert|setup|confluen/i.test(r))
      .filter((r) => !coperte.has(r) && !(r in ESENTATE));
    expect(scoperte).toEqual([]);
  });
});

function radiciDelleChiavi(): Set<string> {
  const radici = new Set<string>();
  for (const [file, testo] of Object.entries(SORGENTI)) {
    if (/\.test\.tsx?$/.test(file)) continue;
    for (const m of testo.matchAll(/queryKey:\s*\[\s*"([a-z0-9-]+)"/g)) radici.add(m[1]);
  }
  return radici;
}
