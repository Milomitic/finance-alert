import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";
import { AlertsTable } from "@/components/AlertsTable";
import { filtersFromSearch, ORDINE_PREDEFINITO, searchFromState } from "@/lib/alertFilters";

/* La lista dei segnali per rilevanza (FA-113). */

vi.mock("@/api/alerts", async (orig) => {
  const vero = await orig<Record<string, unknown>>();
  return {
    ...vero,
    alerts: {
      ...(vero.alerts as Record<string, unknown>),
      signalCalibration: async () => ({ detectors: {} }),
    },
  };
});

describe("l'URL", () => {
  it("la rilevanza e' l'ordine di riposo e non si scrive; la nascita ora si'", () => {
    expect(ORDINE_PREDEFINITO).toBe("rilevanza");
    const vuoto = new URLSearchParams();
    expect(searchFromState({}, 0, "rilevanza", "desc", vuoto).get("sort_by")).toBeNull();
    expect(searchFromState({}, 0, "emissione", "desc", vuoto).get("sort_by")).toBe("emissione");
  });

  it("il filtro «solo i miei titoli» va e torna dall'URL", () => {
    const sp = searchFromState({ solo_rilevanti: true }, 0, "rilevanza", "desc", new URLSearchParams());
    expect(sp.get("solo_rilevanti")).toBe("true");
    expect(filtersFromSearch(sp).solo_rilevanti).toBe(true);
    expect(filtersFromSearch(new URLSearchParams()).solo_rilevanti).toBeUndefined();
  });
});

function alert(id: number, rilevanza: Alert["rilevanza"]): Alert {
  return {
    id, rule_kind: "signal:trend_pullback", stock_id: id, ticker: `T${id}`,
    name: `Titolo ${id}`, currency: "USD", triggered_at: "2026-09-21T20:00:00Z",
    signal_date: "2026-09-15", trigger_price: 340,
    snapshot: { tone: "bull", strength: 81, probability: 50, chain: [] },
    read_at: null, archived_at: null, rilevanza,
  } as Alert;
}

function monta(sortBy: string, onSort: (c: string) => void = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlertsTable
          alerts={[alert(1, "posizione"), alert(2, "preferito"), alert(3, null)]}
          selectedIds={new Set()} onSelect={() => {}} onSelectAll={() => {}}
          onRowClick={() => {}} q="" onQueryChange={() => {}}
          sortBy={sortBy} sortDir="desc" onSort={onSort} onArchiveToggle={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("la tabella", () => {
  it("la riga dice PERCHE' sta in cima, anche a chi non vede l'icona", () => {
    monta("rilevanza");
    expect(screen.getByText("in posizione")).toBeTruthy();
    expect(screen.getByText("preferito")).toBeTruthy();
    expect(screen.getAllByText(/^(in posizione|preferito)$/)).toHaveLength(2);
  });

  it("l'interruttore dice il suo stato e chiede la rilevanza", () => {
    const chieste: string[] = [];
    monta("emissione", (c) => chieste.push(c));
    const stella = screen.getByRole("button", { name: /Prima i tuoi titoli/ });
    expect(stella.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(stella);
    expect(chieste).toEqual(["rilevanza"]);
  });

  it("acceso quando la lista e' gia' per rilevanza", () => {
    monta("rilevanza");
    expect(screen.getByRole("button", { name: /Prima i tuoi titoli/ }).getAttribute("aria-pressed")).toBe("true");
  });
});
