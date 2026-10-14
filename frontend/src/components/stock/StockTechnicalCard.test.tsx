import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { scoreBgColor } from "@/lib/scoreMeta";

import { StockTechnicalCard } from "./StockTechnicalCard";

const BASE = {
  stock_id: 1, ticker: "SOXL", composite: 95, trend: 100, momentum: 95, structure: 98,
  volume: 73, rel_strength: 99, signals: 98, posture: "Forte", computed_at: "2026-10-06T08:00:00Z",
  sector_rank: null as number | null, sector_peers: null as number | null,
};
let dati = { ...BASE };
vi.mock("@/hooks/useStockTechnical", () => ({
  useStockTechnical: () => ({ isLoading: false, noScoreYet: false, data: dati }),
}));

function monta() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StockTechnicalCard ticker="SOXL" />
    </QueryClientProvider>,
  );
}

describe("StockTechnicalCard", () => {
  it("niente «composito» e niente «Segnale recente», e la confidenza alta non si mostra", () => {
    dati = { ...BASE };
    monta();
    expect(screen.getByText("/ 100")).toBeInTheDocument();
    expect(screen.queryByText(/composito/)).toBeNull();
    expect(screen.queryByText(/Segnale recente/)).toBeNull();
    expect(screen.queryByText(/Confidenza/)).toBeNull();
  });

  it("la confidenza compare solo sotto il 50%", () => {
    dati = { ...BASE, signals: 49 };
    const { unmount } = monta();
    expect(screen.getByText(/Confidenza/)).toHaveTextContent("Confidenza 49%");
    unmount();
    dati = { ...BASE, signals: 50 };
    monta();
    expect(screen.queryByText(/Confidenza/)).toBeNull();
  });

  it("il rango nel settore va a capo, sotto il punteggio", () => {
    dati = { ...BASE, sector_rank: 25, sector_peers: 130 };
    monta();
    const rango = screen.getByText(/su 130 nel settore/);
    const punteggio = screen.getByText("/ 100").parentElement!;
    expect(punteggio.contains(rango)).toBe(false);
    expect(punteggio.nextElementSibling).toBe(rango);
  });

  it("le dimensioni hanno la forma dei pilastri della scheda Stock Score", () => {
    dati = { ...BASE };
    // Stessa riga, stessa taglia del valore, barra colorata per fascia (non
    // piu' azzurra): due schede vicine con la stessa scala la dicono uguale.
    monta();
    const valore = screen.getByText("73");
    expect(valore.className).toContain("text-sm");
    expect(valore.className).toContain("font-bold");
    expect(valore.parentElement!.className).toContain("grid-cols-[6.5rem_minmax(0,1fr)_2.25rem]");
    // La barra porta il colore della FASCIA, come i pilastri: 100 e 73 stanno
    // in fasce diverse e quindi in colori diversi (prima erano tutte uguali).
    const barra = (v: string) => screen.getByText(v).parentElement!.querySelector(":scope > div > div")!.className;
    expect(barra("73")).toContain(scoreBgColor(73));
    expect(barra("100")).toContain(scoreBgColor(100));
    expect(scoreBgColor(73)).not.toBe(scoreBgColor(100));
  });
});
