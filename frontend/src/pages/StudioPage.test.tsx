import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { intervallo, parametriDaUrl } from "@/lib/studio";

import StudioPage from "./StudioPage";

/* FA-157: la pagina Studio. Lo stato e' nell'URL, e ogni numero ha il suo caso base. */

const risposte: Record<string, unknown> = {};
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: async (url: string) => risposte[url.split("?")[0]] };
});

const misura = (media: number, finestre = 6) => ({
  casi: 12, finestre, media, mediana: media, quota_positivi: 0.5,
  intervallo: finestre >= 2 ? [media - 0.01, media + 0.01] : null,
});

function monta(url: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[url]}><StudioPage /></MemoryRouter></QueryClientProvider>);
}

describe("parametri dall'URL", () => {
  it("valori ammessi dal server anche da un link scritto a mano", () => {
    const p = parametriDaUrl(new URLSearchParams("simbolo=aapl&modello=boh&sedute=500&soglia=0&orizzonte=-3"));
    expect(p).toMatchObject({ simbolo: "AAPL", modello: "dopo_movimento", sedute: 63, soglia: -10, orizzonte: 1 });
  });

  it("l'intervallo dice perche' manca", () => {
    expect(intervallo(misura(0.02, 1) as never)).toMatch(/meno di due finestre/);
    expect(intervallo(misura(0.02) as never)).toBe("da +1,0% a +3,0%");
  });
});

describe("StudioPage", () => {
  it("senza simbolo propone domande d'esempio (D-81)", () => {
    monta("/studio");
    expect(screen.getByText(/Scegli un simbolo, oppure parti da una di queste domande/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AAPL nelle 21 sedute dopo un calo del 10%/ })).toBeInTheDocument();
  });

  it("dopo un movimento: condizione contro base", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL", condizione: misura(0.03), base: misura(0.01), differenza: 0.02,
      intervallo_differenza: [-0.01, 0.05], verdetto: "non_concludente",
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(await screen.findByText("Dopo il movimento")).toBeInTheDocument();
    expect(screen.getByText("Base: tutte le finestre")).toBeInTheDocument();
    expect(screen.getByText("+2,00%")).toBeInTheDocument();
    // D-84: il verdetto sta sopra i numeri, con l'intervallo della differenza.
    expect(screen.getByText("Non concludente")).toBeInTheDocument();
    expect(screen.getByText(/da −1,00% a \+5,00%, 95%/)).toBeInTheDocument();
  });

  it("attorno a un evento: il percorso e la misura", async () => {
    risposte["/api/studio/evento"] = {
      simbolo: "AAPL", tipo: "trimestrali", serie_macro: null, eventi: 0, percorso: [],
      a_orizzonte: misura(0, 0), base: misura(0.001), orizzonte: 5,
      differenza: null, intervallo_differenza: null, verdetto: "non_concludente",
    };
    monta("/studio?simbolo=AAPL&modello=evento");
    expect(await screen.findByText(/Nessuna trimestrale passata nota/)).toBeInTheDocument();
  });

  it("un effetto che cambia segno fra le due meta' non e' «diverso», e la distribuzione si vede (ondata 1)", async () => {
    risposte["/api/studio/dopo_movimento"] = {
      simbolo: "AAPL",
      condizione: { ...misura(0.03, 40), mediana: -0.01, p10: -0.08, p90: 0.12, peggiore: -0.2, migliore: 0.3 },
      base: misura(0.01, 120), differenza: 0.02, intervallo_differenza: [0.005, 0.035], verdetto: "instabile",
      stabilita: { prima: 0.05, seconda: -0.01, concordi: false },
      istogramma: [{ da: -0.1, a: 0, condizione: 0.4, base: 0.5 }, { da: 0, a: 0.1, condizione: 0.6, base: 0.5 }],
      parametri: { sedute: 5, soglia_pct: -10, orizzonte: 21 },
    };
    monta("/studio?simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(await screen.findByText("Non regge nelle due metà")).toBeInTheDocument();
    expect(screen.getByText(/Prima metà \+5,00% · seconda metà −1,00%/)).toBeInTheDocument();
    expect(screen.getByText("Distribuzione")).toBeInTheDocument();
    expect(screen.getByText("−20,0%")).toBeInTheDocument();
    // D-87: il risultato ripete la domanda.
    expect(screen.getByRole("heading", { name: /AAPL · Dopo un movimento/ })).toBeInTheDocument();
  });
});

