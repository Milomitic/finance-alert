import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* FA-188: le tessere del contesto dicono valore, un mese fa e percentile col periodo. */

vi.mock("@/api/client", async () => {
  const vero = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...vero,
    api: async () => ({
      tessere: [
        { chiave: "vix", nome: "VIX, volatilita' attesa", valore: 23.81, unita: "", prima: 26.9, variazione_relativa: -0.115,
          percentile: 78.4, percentile_dal: "1990-01-02", serie: [20, 25, 23.81], data: "2026-11-27", nota: null, simbolo: "^VIX" },
        { chiave: "curva", nome: "Tassi USA 10 anni meno 2 anni", valore: 0.42, unita: "%", prima: 0.35, variazione_relativa: null,
          percentile: 61, percentile_dal: "2023-05-08", serie: [0.3, 0.42], data: "2026-11-26", nota: "10 anni 4,93%, 2 anni 4,51%", simbolo: null },
        { chiave: "ampiezza", nome: "Titoli sopra la media a 200", valore: 49.5, unita: "%", prima: null, variazione_relativa: null,
          percentile: null, percentile_dal: null, serie: [], data: null, nota: "Archivio dal 28/11/2026: 1 giorno, il percentile arriva con un anno.", simbolo: null },
      ],
    }),
  };
});

const { ContestoMercato } = await import("./ContestoMercato");

describe("ContestoMercato", () => {
  it("valore, un mese fa, percentile col periodo; l'archivio corto lo dice", async () => {
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ContestoMercato /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText("23,81")).toBeInTheDocument();
    expect(screen.getByText("in un mese −11,5%")).toBeInTheDocument();
    expect(screen.getByText("al 78° percentile dal 1990")).toBeInTheDocument();
    expect(screen.getByText("0,42%")).toBeInTheDocument();
    expect(screen.getByText("un mese fa 0,35%")).toBeInTheDocument();
    expect(screen.getByText(/il percentile arriva con un anno/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /VIX/ })).toHaveAttribute("href", "/markets/%5EVIX");
    expect(screen.getByText(/non la prevede/)).toBeInTheDocument();
  });
});
