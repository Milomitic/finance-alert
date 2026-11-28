import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { type ParametriStudio, parametriDaUrl } from "@/lib/studio";

/* FA-199: il modulo dello Studio scritto come la domanda. */

vi.mock("@/api/client", async () => {
  const vero = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...vero,
    api: async (url: string) => {
      if (url.startsWith("/api/studio/serie_macro")) return [{ id: "CPIAUCSL", nome: "US CPI release", rilasci: 19 }];
      if (url.startsWith("/api/stocks/search")) return { items: [{ stock: { ticker: "AAPL", name: "Apple" } }], total: 1, has_more: false };
      if (url.startsWith("/api/dashboard/live-assets")) return { assets: [{ symbol: "^GSPC", name: "S&P 500" }] };
      return null;
    },
  };
});

const { ModuloStudio } = await import("./ModuloStudio");

let ultima: ParametriStudio | null = null;

function Banco({ iniziale }: { iniziale: string }) {
  const [b, setB] = useState(parametriDaUrl(new URLSearchParams(iniziale)));
  const cambia = (p: ParametriStudio) => {
    ultima = p;
    setB(p);
  };
  return <ModuloStudio bozza={b} onBozza={cambia} onCalcola={() => {}} />;
}

function monta(iniziale: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><Banco iniziale={iniziale} /></QueryClientProvider>);
}

describe("ModuloStudio", () => {
  it("la domanda si legge come una frase, e il verso cambia il segno della soglia", () => {
    monta("simbolo=AAPL&modello=dopo_movimento&soglia=-10&sedute=5&orizzonte=21");
    expect(screen.getByText("% o più in")).toBeInTheDocument();
    expect(screen.getByLabelText(/Entità del movimento/)).toHaveValue(10);
    fireEvent.change(screen.getByLabelText("Verso del movimento"), { target: { value: "su" } });
    expect(ultima?.soglia).toBe(10);
    fireEvent.change(screen.getByLabelText(/Entità del movimento/), { target: { value: "7" } });
    expect(ultima?.soglia).toBe(7);
  });

  it("la serie macro si sceglie per nome, con quanti rilasci ha", async () => {
    monta("simbolo=^GSPC&modello=evento&tipo=macro");
    const opzione = await screen.findByRole("option", { name: "US CPI release (19 rilasci)" });
    expect(opzione).toHaveValue("CPIAUCSL");
    expect(screen.getByRole("button", { name: "Calcola" })).toBeDisabled();   // serie non ancora scelta
    fireEvent.change(screen.getByLabelText("Serie macro"), { target: { value: "CPIAUCSL" } });
    expect(screen.getByRole("button", { name: "Calcola" })).toBeEnabled();
  });

  it("senza simbolo non si calcola; il simbolo suggerisce titoli e mercati", async () => {
    monta("modello=stagionalita");
    expect(screen.getByRole("button", { name: "Calcola" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Simbolo/), { target: { value: "s" } });   // «S&P 500»; Apple viene dalla ricerca finta
    // I suggerimenti stanno in un <datalist>, che jsdom non espone come ruoli.
    await waitFor(() => expect(document.querySelector('datalist option[value="AAPL"]')?.textContent).toBe("Apple"));
    expect(document.querySelector('datalist option[value="^GSPC"]')?.textContent).toBe("S&P 500");
  });

  it("toccare prima, cali e recuperi, e al netto di (FA-196/197/198)", () => {
    monta("simbolo=AAPL&modello=primo_passaggio");
    expect(screen.getByLabelText("Verso dell'operazione")).toHaveValue("long");
    expect(screen.getByLabelText(/Obiettivo in percentuale/)).toHaveValue(8);
    expect(screen.queryByLabelText("Al netto di un riferimento")).toBeNull();     // non vale qui
    fireEvent.click(screen.getByRole("button", { name: "Dopo un movimento" }));
    fireEvent.change(screen.getByLabelText("Al netto di un riferimento"), { target: { value: "^GSPC" } });
    expect(ultima?.netto).toBe("^GSPC");
    fireEvent.click(screen.getByRole("button", { name: "Cali e recuperi" }));
    expect(screen.getByLabelText(/Soglia del calo/)).toHaveValue(10);
  });
});
