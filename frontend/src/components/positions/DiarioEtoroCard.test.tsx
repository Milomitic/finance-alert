import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EtoroDiario, EtoroOperazione } from "@/api/etoro";
import { axeViolations, describeViolations } from "@/test/axe";

import { DiarioEtoroCard } from "./DiarioEtoroCard";

let diario: EtoroDiario | undefined;

vi.mock("@/hooks/useEtoro", () => ({
  useEtoroDiario: () => ({ data: diario }),
}));

function op(over: Partial<EtoroOperazione> = {}): EtoroOperazione {
  return {
    position_id: 1, instrument_id: 3226, ticker: "SOXL", simbolo: "SOXL", aperta_il: "2026-09-10T14:00:00Z",
    chiusa_il: "2026-09-16T15:00:00Z", lato: "long", leva: 5, prezzo_apertura: 30, prezzo_chiusura: 33,
    investimento_usd: 500, profitto_netto_usd: 150, commissioni_usd: 2, pct_investimento: 30, giorni: 6,
    alert_id: 42, detector: "trend_pullback", segnale_il: "2026-09-09T22:00:00Z", r_reale: 1.5, r_piano: 1.2,
    esito_piano: "tp1", ...over,
  };
}

function monta(apri = vi.fn()) {
  render(
    <MemoryRouter>
      <DiarioEtoroCard onApriSegnale={apri} />
    </MemoryRouter>,
  );
  return apri;
}

beforeEach(() => {
  diario = {
    operazioni: [op(), op({ position_id: 2, ticker: null, simbolo: "BTC", alert_id: null, detector: null,
      r_reale: null, r_piano: null, profitto_netto_usd: -40, pct_investimento: -8, giorni: 0.5 })],
    tutte: { n: 2, vincenti: 1, profitto_usd: 110, vincenti_pct: 50, profitto_medio_usd: 55 },
    precedute: { n: 1, vincenti: 1, profitto_usd: 150, vincenti_pct: null, profitto_medio_usd: 150 },
    non_precedute: { n: 1, vincenti: 0, profitto_usd: -40, vincenti_pct: null, profitto_medio_usd: -40 },
    r_reale_medio: 1.5, r_piano_medio: 1.2, con_r: 1,
    anni: [{ anno: 2026, n: 2, profitto_usd: 110, profitto_eur: 94.02, commissioni_usd: 4 }],
  };
});

describe("DiarioEtoroCard", () => {
  it("senza operazioni non compare", () => {
    diario = { ...diario!, operazioni: [], tutte: null };
    monta();
    expect(screen.queryByText(/Diario eToro/)).toBeNull();
  });

  it("il riepilogo, col conteggio accanto al tasso", () => {
    monta();
    // Il realizzato totale, e lo stesso numero nella riga dell'anno.
    expect(screen.getAllByText("+$110.00")).toHaveLength(2);
    expect(screen.getByText("1 su 2")).toBeTruthy();
    expect(screen.getByText("+1.50 R")).toBeTruthy();
    expect(screen.getByText("piano +1.20 R · su 1")).toBeTruthy();
    // Su una sola operazione il tasso non si mostra.
    expect(screen.getByText("1 · +$150.00")).toBeTruthy();
  });

  it("l'anno in dollari e in euro", () => {
    monta();
    expect(screen.getByText("≈ +€94.02")).toBeTruthy();
  });

  it("senza cambio l'euro lo dice", () => {
    diario!.anni[0].profitto_eur = null;
    monta();
    expect(screen.getByText("in euro: cambio non disponibile")).toBeTruthy();
  });

  it("il segnale che ha preceduto un'operazione si apre", () => {
    const apri = monta();
    fireEvent.click(screen.getByRole("button", { name: /dopo Trend \+ Pull · \+1\.5 R \(piano \+1\.2 R\)/ }));
    expect(apri).toHaveBeenCalledWith(42);
    expect(screen.getByText("senza segnale")).toBeTruthy();
  });

  it("le ultime 15, e tutte a richiesta", () => {
    diario!.operazioni = Array.from({ length: 20 }, (_, i) => op({ position_id: i + 1 }));
    monta();
    expect(screen.getAllByRole("listitem").filter((l) => l.textContent?.includes("Long ×5"))).toHaveLength(15);
    fireEvent.click(screen.getByRole("button", { name: "Mostra tutte e 20" }));
    expect(screen.getAllByRole("listitem").filter((l) => l.textContent?.includes("Long ×5"))).toHaveLength(20);
  });

  it("nessuna violazione strutturale", async () => {
    const { container } = render(<MemoryRouter><DiarioEtoroCard onApriSegnale={() => {}} /></MemoryRouter>);
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toHaveLength(0);
  });
});
