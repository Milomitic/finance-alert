import { StrictMode } from "react";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import UsoPagineCard from "@/components/health/UsoPagineCard";

const registra = vi.hoisted(() => vi.fn());
vi.mock("@/api/uso", () => ({ registraPagina: (...a: unknown[]) => { registra(...a); return Promise.resolve(); } }));

import { UsoPagineReporter } from "./UsoPagineReporter";

let vai: (to: string) => void = () => undefined;
function Navigatore() {
  const navigate = useNavigate();
  vai = (to) => navigate(to);
  return null;
}

function monta(iniziale: string) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[iniziale]}>
        <Navigatore />
        <UsoPagineReporter />
      </MemoryRouter>
    </StrictMode>,
  );
}

beforeEach(() => registra.mockClear());

it("conta la pagina d'ingresso UNA volta anche sotto StrictMode", () => {
  monta("/stocks");
  expect(registra.mock.calls).toEqual([["/stocks", null]]);
});

it("un cambio di pagina si conta, un cambio di filtri no", () => {
  monta("/stocks");
  act(() => vai("/stocks?q=apple&settore=Tech"));
  act(() => vai("/stocks/AAPL"));
  act(() => vai("/stocks/AAPL?range=1y"));
  expect(registra.mock.calls).toEqual([["/stocks", null], ["/stocks/AAPL", null]]);
});

it("sulle pagine a viste la vista E' la pagina", () => {
  monta("/alerts");
  act(() => vai("/alerts?vista=formazione"));
  act(() => vai("/alerts?vista=formazione&detector=gap_and_go"));
  act(() => vai("/alerts"));
  expect(registra.mock.calls).toEqual([
    ["/alerts", null], ["/alerts", "formazione"], ["/alerts", null],
  ]);
});

it("altrove un parametro vista non e' una pagina nuova", () => {
  monta("/calendar");
  act(() => vai("/calendar?vista=mese"));
  expect(registra.mock.calls).toEqual([["/calendar", null]]);
});

// ── la scheda della Diagnostica ───────────────────────────────────────────

it("la scheda dice da quando conta, e da' un nome a ogni pagina", () => {
  render(
    <UsoPagineCard
      uso={{
        dal: "2026-09-28", oggi: "2026-09-30",
        rotte: [
          { rotta: "/stocks/:ticker", ultimi_7: 12, ultimi_30: 12, ultimo_giorno: "2026-09-30" },
          { rotta: "/alerts?vista=formazione", ultimi_7: 3, ultimi_30: 3, ultimo_giorno: "2026-09-29" },
        ],
      }}
    />,
  );
  expect(screen.getByText("contate dal 28/09/2026")).toBeTruthy();
  expect(screen.getByText("Dettaglio titolo")).toBeTruthy();
  expect(screen.getByText("Segnali · In formazione")).toBeTruthy();
});

it("NON SO e nessuna apertura sono due cose diverse", () => {
  const { rerender } = render(<UsoPagineCard uso={null} />);
  expect(screen.getByText(/non disponibile/)).toBeTruthy();
  rerender(<UsoPagineCard uso={{ dal: null, oggi: "2026-09-28", rotte: [] }} />);
  expect(screen.getByText("Nessuna apertura contata ancora.")).toBeTruthy();
});
