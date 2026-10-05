import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EtoroPortafoglio, EtoroStrumento } from "@/api/etoro";
import { pos } from "@/test/etoroFixture";
import { axeViolations, describeViolations } from "@/test/axe";

import { EtoroPortafoglioCard } from "./EtoroPortafoglioCard";

/* ─── La scheda del portafoglio eToro (FA-124) ────────────────────────────
 *
 * Le posizioni del caso vero: CFD long ×5, piu' posizioni sullo stesso
 * strumento. jsdom non fa layout, quindi qui si fissano struttura, testi e
 * ARIA; l'ingombro lo misura il gate UI.
 */

let portafoglio: EtoroPortafoglio;
const abbina = vi.fn();
const sincronizza = vi.fn();

vi.mock("@/hooks/useEtoro", () => ({
  useAbbinaEtoro: () => ({ mutate: abbina, isPending: false, error: null }),
  useSincronizzaEtoro: () => ({ mutate: sincronizza, isPending: false, isError: false, error: null }),
}));

function monta(errore = false) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EtoroPortafoglioCard d={errore ? undefined : portafoglio} errore={errore} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const RR: EtoroStrumento = {
  instrument_id: 2002, simbolo: "RR", nome: "Rolls-Royce Holdings", tipo: "Stocks",
  abbinamento: "da_confermare", ticker: null, candidato_ticker: "RR", candidato_nome: "Richtech Robotics Inc.",
};

const CONTO = {
  aggiornato_il: "2026-10-05T12:00:00Z", valuta: "USD", credito_usd: 1234.5, valore_totale: 8500,
  pnl_aperto: 760, guadagno_giorno: -42.5, guadagno_giorno_pct: -0.5,
};

beforeEach(() => {
  abbina.mockReset();
  sincronizza.mockReset();
  portafoglio = {
    configurato: true, conto: CONTO, da_decidere: [], chiuse: [],
    aperte: [
      pos({ position_id: 1, instrument_id: 3226, margine_usd: 270, esposizione_usd: 1450, pnl_usd: 100 }),
      pos({ position_id: 2, instrument_id: 3226, margine_usd: 354, esposizione_usd: 2054, pnl_usd: 284, stop: null, stop_pct_margine: null }),
      pos({ position_id: 3, instrument_id: 1130, simbolo: "MU", ticker: "MU", nome: "Micron Technology, Inc.", esposizione_usd: 2996, pnl_usd: 6, margine_usd: 598 }),
    ],
  };
});

describe("EtoroPortafoglioCard", () => {
  it("senza chiavi dice dove generarle, senza mostrare numeri", () => {
    portafoglio = { configurato: false, conto: null, aperte: [], chiuse: [], da_decidere: [] };
    monta();
    expect(screen.getByText(/API Key Management/)).toBeTruthy();
    expect(screen.queryByText("Valore del conto")).toBeNull();
  });

  it("un errore di eToro si dice, senza numeri", () => {
    monta(true);
    expect(screen.getByText("Portafoglio eToro non disponibile.")).toBeTruthy();
  });

  it("una riga per strumento, la piu' esposta in cima", () => {
    monta();
    const righe = screen.getAllByRole("button", { name: /Mostra le posizioni su/ });
    expect(righe.map((b) => b.getAttribute("aria-label"))).toEqual([
      "Mostra le posizioni su SOXL", "Mostra le posizioni su MU",
    ]);
    expect(screen.getByText(/Long ×5 CFD · 2 posizioni/)).toBeTruthy();
  });

  it("dice quante posizioni non hanno uno stop", () => {
    monta();
    expect(screen.getByText("1 senza stop")).toBeTruthy();
  });

  it("il dettaglio si apre a richiesta e porta lo stop in % del margine", () => {
    monta();
    const bottone = screen.getByRole("button", { name: "Mostra le posizioni su MU" });
    // ⚠️ Nessun aria-controls finche' il pannello non esiste (axe, CLAUDE.md).
    expect(bottone.getAttribute("aria-controls")).toBeNull();
    fireEvent.click(bottone);
    const id = bottone.getAttribute("aria-controls");
    expect(id).toBeTruthy();
    const pannello = document.getElementById(id!)!;
    expect(within(pannello).getByText(/-50.0% del margine/)).toBeTruthy();
  });

  it("i totali del conto in dollari", () => {
    monta();
    expect(screen.getByText("Valore del conto")).toBeTruthy();
    expect(screen.getByText("Cassa disponibile")).toBeTruthy();
  });

  it("segnala il doppione con una posizione manuale", () => {
    portafoglio.aperte[2] = { ...portafoglio.aperte[2], anche_manuale: true };
    monta();
    expect(screen.getByText(/MU è anche fra le posizioni inserite a mano/)).toBeTruthy();
  });

  it("sincronizza a richiesta", () => {
    monta();
    fireEvent.click(screen.getByRole("button", { name: "Sincronizza adesso con eToro" }));
    expect(sincronizza).toHaveBeenCalledOnce();
  });

  it("le chiuse recenti col motivo", () => {
    portafoglio.chiuse = [pos({ position_id: 9, chiusa_il: "2026-10-04T15:00:00Z", motivo_chiusura: "target", profitto_netto_usd: 145 })];
    monta();
    expect(screen.getByText(/a target il 04\/10\/26/)).toBeTruthy();
  });

  it("nessuna violazione strutturale, anche col dettaglio aperto e un abbinamento da decidere", async () => {
    portafoglio.da_decidere = [RR];
    const { container } = monta();
    fireEvent.click(screen.getByRole("button", { name: "Mostra le posizioni su SOXL" }));
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toHaveLength(0);
  });
});

describe("EtoroDaAbbinare", () => {
  it("non compare quando non c'e' niente da decidere", () => {
    monta();
    expect(screen.queryByText("Da abbinare al catalogo")).toBeNull();
  });

  it("conferma il candidato, un altro ticker, o «non è nel catalogo»", () => {
    portafoglio.da_decidere = [RR];
    monta();
    fireEvent.click(screen.getByRole("button", { name: /È RR/ }));
    expect(abbina).toHaveBeenLastCalledWith({ instrumentId: 2002, ticker: "RR" });
    fireEvent.change(screen.getByRole("textbox", { name: "Ticker del catalogo per RR" }), { target: { value: "RR.L" } });
    fireEvent.click(screen.getByRole("button", { name: "Abbina" }));
    expect(abbina).toHaveBeenLastCalledWith({ instrumentId: 2002, ticker: "RR.L" });
    fireEvent.click(screen.getByRole("button", { name: "Non è nel catalogo" }));
    expect(abbina).toHaveBeenLastCalledWith({ instrumentId: 2002, ticker: null });
  });
});
