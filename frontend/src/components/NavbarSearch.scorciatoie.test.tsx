import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

/* Ctrl+K e i preferiti nella ricerca (FA-112). */

vi.mock("@/hooks/useStockSearch", () => ({
  useStockSearch: () => ({ data: undefined, isLoading: false, isError: false }),
}));
vi.mock("@/hooks/useMarketSummary", () => ({ useMarketSummary: () => ({ data: undefined }) }));
vi.mock("@/hooks/usePreferiti", () => ({
  usePreferiti: () => ({ data: [{ ticker: "ENI.MI" }, { ticker: "AAPL" }] }),
}));
vi.mock("@/hooks/useMediaQuery", () => ({ useIsPhone: () => false }));

import { NavbarSearch } from "./NavbarSearch";
import { aggiungiRecente } from "@/lib/titoliRecenti";

function monta() {
  return render(
    <MemoryRouter>
      <input aria-label="un altro campo" />
      <NavbarSearch />
    </MemoryRouter>,
  );
}

it("Ctrl+K porta alla ricerca anche da dentro un altro campo", () => {
  monta();
  const altro = screen.getByLabelText("un altro campo");
  altro.focus();
  fireEvent.keyDown(document, { key: "k", ctrlKey: true });
  expect(document.activeElement).toBe(screen.getByRole("combobox"));
});

it("Cmd+K sul Mac fa lo stesso", () => {
  monta();
  fireEvent.keyDown(document, { key: "K", metaKey: true });
  expect(document.activeElement).toBe(screen.getByRole("combobox"));
});

it("«/» dentro un campo e' un carattere, non una scorciatoia", () => {
  monta();
  const altro = screen.getByLabelText("un altro campo");
  altro.focus();
  fireEvent.keyDown(document, { key: "/" });
  expect(document.activeElement).toBe(altro);
});

it("a casella vuota i preferiti stanno in cima, e i recenti non li ripetono", () => {
  for (const t of ["AAPL", "NVDA"]) aggiungiRecente(t);
  monta();
  fireEvent.keyDown(document, { key: "k", ctrlKey: true });
  const opzioni = screen.getAllByRole("option").map((o) => o.textContent ?? "");
  expect(opzioni.map((o) => o.match(/ENI\.MI|AAPL|NVDA/)?.[0])).toEqual(["ENI.MI", "AAPL", "NVDA"]);
  expect(screen.getByText("★ Preferiti (2)")).toBeTruthy();
  expect(screen.getByText("🕓 Visti di recente (1)")).toBeTruthy();
});
