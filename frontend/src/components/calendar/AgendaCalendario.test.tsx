import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { CalendarEvent } from "@/api/types";
import { TooltipProvider } from "@/components/ui/tooltip";

import { AgendaCalendario } from "./AgendaCalendario";

/* L'agenda sotto `lg` (D-61): solo i giorni con eventi, in ordine, solo
 * quelli del periodo visibile, e il nome del titolo leggibile. */

const ev = (date: string, ticker: string) =>
  ({ date, kind: "earnings", ticker, name: `Societa ${ticker}`, eps_estimate: null,
     revenue_estimate: null, sector: null, market_cap: null }) as unknown as CalendarEvent;

function monta(onSelect = vi.fn()) {
  render(
    <MemoryRouter>
      <TooltipProvider>
      <AgendaCalendario
        events={[ev("2026-11-20", "MSFT"), ev("2026-11-03", "AAPL"), ev("2026-10-30", "FUORI"), ev("2026-11-20", "NVDA")]}
        daISO="2026-11-01"
        aISO="2026-11-30"
        selectedDate={null}
        onSelectDate={onSelect}
      />
      </TooltipProvider>
    </MemoryRouter>,
  );
  return onSelect;
}

describe("AgendaCalendario", () => {
  it("un blocco per giorno con eventi, in ordine, senza i giorni fuori periodo", () => {
    monta();
    const giorni = screen.getAllByRole("listitem");
    expect(giorni).toHaveLength(2);
    expect(giorni[0]).toHaveTextContent("3 novembre");
    expect(giorni[1]).toHaveTextContent("2 eventi");
    expect(screen.queryByText("FUORI")).toBeNull();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("toccare il giorno apre il dettaglio di quel giorno", () => {
    const onSelect = monta();
    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(onSelect).toHaveBeenCalledWith("2026-11-03");
  });
});
