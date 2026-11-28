import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScalaStoricaOut } from "@/api/schema.gen";

/* FA-206: fin dove arrivano i piani di questo tipo, per chi chiude a mano. */

let risposta: ScalaStoricaOut | null = null;
let aperto: { peak_fraction: number; current_fraction: number } | null = null;

vi.mock("@/api/client", async () => {
  const vero = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...vero,
    api: async (url: string) => (url.includes("scala-storica") ? risposta : aperto),
  };
});

const { ScalaStoricaBlock } = await import("./ScalaStoricaBlock");

function monta(props: { piccoChiuso?: number | null } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ScalaStoricaBlock id={7} {...props} /></QueryClientProvider>);
}

const SCALA: ScalaStoricaOut = {
  detector: "sr_flip", tone: "bull", piani: 120, sufficiente: true, orizzonte: 21, finestre: 9,
  dal: "2026-05-22", al: "2026-10-29", giorni_al_picco: 6,
  gradini: [
    { soglia: 25, toccati: 80, quota: 66.7, intervallo: [35, 88], esiti: { tp1: 30, stop: 25, scaduto: 25 } },
    { soglia: 50, toccati: 50, quota: 41.7, intervallo: [16, 72], esiti: { tp1: 30, stop: 8, scaduto: 12 } },
    { soglia: 75, toccati: 40, quota: 33.3, intervallo: [11, 65], esiti: { tp1: 30, stop: 3, ambigua: 1, scaduto: 6 } },
    { soglia: 90, toccati: 34, quota: 28.3, intervallo: [8, 61], esiti: { tp1: 30, stop: 1, scaduto: 3 } },
    { soglia: 100, toccati: 30, quota: 25, intervallo: [6, 57], esiti: { tp1: 30 } },
  ],
  stop: { numero: 50, passati_da_meta: 8, passati_da_un_quarto: 25, picco_mediano: 0.2 },
  scaduti: { numero: 40, picco_mediano: 0.45, chiusura_mediana: 0.1 },
};

describe("ScalaStoricaBlock", () => {
  it("i gradini con la quota, chi poi va a stop, e la restituzione", async () => {
    risposta = SCALA;
    monta({ piccoChiuso: 0.8 });
    expect(await screen.findByText("Fin dove arrivano i piani di questo tipo")).toBeInTheDocument();
    expect(screen.getByText("120 piani · 9 finestre indipendenti")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText("poi stop 4 su 40")).toBeInTheDocument();     // ambigua conta come stop
    expect(screen.getByText("30 completati")).toBeInTheDocument();
    expect(screen.getByText("8 su 50 (16%)")).toBeInTheDocument();
    expect(screen.getByText("45% poi 10%")).toBeInTheDocument();
    expect(screen.getByText("6 giorni dopo l'ingresso")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();                  // questo piano
  });

  it("il piano aperto prende il massimo dal suo percorso", async () => {
    risposta = SCALA;
    aperto = { peak_fraction: 0.55, current_fraction: 0.3 };
    monta();
    expect(await screen.findByText("55%")).toBeInTheDocument();
  });

  it("sotto venti piani dice che sono troppo pochi, senza gradini", async () => {
    risposta = { detector: "x", tone: "bull", piani: 7, sufficiente: false };
    monta({ piccoChiuso: null });
    expect(await screen.findByText(/Solo 7 piani chiusi/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
