import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_FILTERS } from "@/lib/screenerFilters";

import { StockFiltersCard } from "./StockFiltersCard";

/* C-29: la ricerca della tabella conta fra i filtri attivi, ha il suo chip e
 * «Reset» la cancella insieme agli altri. */

describe("la ricerca fra i filtri", () => {
  it("conta come attiva e ha il chip", () => {
    render(<StockFiltersCard state={EMPTY_FILTERS} onChange={vi.fn()} filters={undefined} ricerca={{ q: "ban", onClear: vi.fn() }} />);
    expect(screen.getByText("1 attivi")).toBeInTheDocument();
    expect(screen.getByText("Cerca:")).toBeInTheDocument();
  });

  it("il chip e Reset la cancellano", async () => {
    const onClear = vi.fn();
    const onChange = vi.fn();
    render(<StockFiltersCard state={EMPTY_FILTERS} onChange={onChange} filters={undefined} ricerca={{ q: "ban", onClear }} />);
    await userEvent.click(screen.getByRole("button", { name: "Rimuovi la ricerca ban" }));
    expect(onClear).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: /Reset/ }));
    expect(onClear).toHaveBeenCalledTimes(2);
    expect(onChange).toHaveBeenCalledWith(EMPTY_FILTERS);
  });

  it("senza ricerca niente cambia", () => {
    render(<StockFiltersCard state={EMPTY_FILTERS} onChange={vi.fn()} filters={undefined} ricerca={{ q: "  ", onClear: vi.fn() }} />);
    expect(screen.queryByText("Cerca:")).toBeNull();
  });
});
