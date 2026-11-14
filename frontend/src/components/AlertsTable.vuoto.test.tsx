import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AlertsTable } from "./AlertsTable";

/* FA-136: la lista dei segnali parte dai titoli in posizione e fra i
 * preferiti. Vuota, deve dire PERCHE' — altrimenti si legge come «oggi non e'
 * scattato niente» quando sull'universo i segnali ci sono. Chi sa il perche'
 * e' la vista, quindi lo passa alla tabella. */

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

function monta(props: { q?: string; vuoto?: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlertsTable
          alerts={[]} selectedIds={new Set()} onSelect={() => {}} onSelectAll={() => {}}
          onRowClick={() => {}} q={props.q ?? ""} onQueryChange={() => {}} vuoto={props.vuoto}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("la tabella vuota", () => {
  it("senza indicazioni dice il messaggio generico", () => {
    monta({});
    expect(screen.getByText("Nessun segnale con questi filtri.")).toBeInTheDocument();
  });

  it("con la ragione della vista mostra quella", () => {
    monta({ vuoto: <span>Nessun segnale sui tuoi titoli</span> });
    expect(screen.getByText("Nessun segnale sui tuoi titoli")).toBeInTheDocument();
    expect(screen.queryByText("Nessun segnale con questi filtri.")).toBeNull();
  });

  it("una ricerca vuota resta una ricerca vuota", () => {
    monta({ q: "zzz", vuoto: <span>Nessun segnale sui tuoi titoli</span> });
    expect(screen.getByText('Nessun risultato per "zzz".')).toBeInTheDocument();
  });
});
