import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EtoroAndamento, EtoroVivo } from "@/api/etoro";
import { axeViolations, describeViolations } from "@/test/axe";

import { ContoEtoroHero } from "./ContoEtoroHero";

/* ─── Il conto eToro in cima alla home (FA-127) ───────────────────────────
 *
 * I numeri sono quelli del conto vero letti il 2026-10-06. jsdom non fa
 * layout: qui si fissano testi, struttura, ARIA e l'altezza dichiarata; lo
 * spostamento vero lo misura il gate CLS.
 */

let andamento: EtoroAndamento | undefined;

vi.mock("@/hooks/useEtoro", () => ({
  useEtoroAndamento: () => ({ data: andamento, isLoading: andamento === undefined }),
}));

const VIVO: EtoroVivo = {
  configurato: true, aggiornato_il: "2026-10-06T10:03:00Z", in_ritardo: false, valuta: "USD",
  valore: 8255.93, valore_ieri: 8713.89, guadagno_giorno: -457.96, guadagno_giorno_pct: -5.25,
  pnl_aperto: 660.86, margine_usato: 7483.79, cassa: 111.28, esposizione: 38000, leva_effettiva: 4.6,
  posizioni: 19,
  strumenti: [
    { instrument_id: 3226, ticker: "SOXL", simbolo: "SOXL", nome: null, guadagno_giorno: -300, pnl: 965, esposizione: 8685, margine: 1547 },
    { instrument_id: 1069, ticker: "SMCI", simbolo: "SMCI", nome: null, guadagno_giorno: 120, pnl: 190, esposizione: 4192, margine: 800 },
    { instrument_id: 99, ticker: null, simbolo: "XYZ", nome: null, guadagno_giorno: -10, pnl: 0, esposizione: 100, margine: 20 },
  ],
};

function monta(v: EtoroVivo = VIVO) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ContoEtoroHero v={v} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  andamento = {
    configurato: true,
    giorni: [
      { giorno: "2026-09-01", valore: 7900, pnl_aperto: 300, fonte: "storico" },
      { giorno: "2026-10-05", valore: 8713.89, pnl_aperto: 900, fonte: "storico" },
    ],
    oggi: [{ istante: "2026-10-06T08:00:00Z", valore: 8600 }],
    periodi: [{ chiave: "1M", dal: "2026-09-05", valore_iniziale: 7900, valore_finale: 8255.93, variazione: 355.93,
      generato: 300, realizzato: 50, flussi: 55.93, generato_pct: 3.8 }],
  };
});

describe("ContoEtoroHero", () => {
  it("il valore, il giorno e le quattro grandezze di un conto a leva", () => {
    monta();
    const s = screen.getByRole("region", { name: "Il tuo conto eToro" });
    // Il numero grande e, nella curva, il minimo della scala.
    expect(within(s).getAllByText("$8,255.93")[0].className).toContain("text-[2.35rem]");
    expect(within(s).getByText("-$457.96")).toBeTruthy();
    expect(within(s).getByText("(-5.25%)")).toBeTruthy();
    expect(within(s).getByText("leva effettiva ×4.6")).toBeTruthy();
    expect(within(s).getByText("19 posizioni")).toBeTruthy();
    expect(within(s).getByText(/dal vivo/)).toBeTruthy();
  });

  it("dice quando i numeri sono in ritardo", () => {
    monta({ ...VIVO, in_ritardo: true });
    expect(screen.getByText(/in ritardo/)).toBeTruthy();
  });

  it("ha un'altezza fissa per ogni larghezza (gate CLS)", () => {
    monta();
    const cls = screen.getByRole("region", { name: "Il tuo conto eToro" }).className;
    expect(cls).toContain("h-[700px]");
    expect(cls).toContain("lg:h-[300px]");
  });

  it("sotto la curva il P/L generato, non la variazione del valore", () => {
    monta();
    expect(screen.getByRole("button", { name: "1M" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("+$300.00 (+3.8%)")).toBeTruthy();
    expect(screen.getByText("+$55.93")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Valore del conto, intervallo 1M/ })).toBeTruthy();
  });

  it("su «Oggi» la curva parte dalla chiusura di ieri e sotto c'e' il giorno", () => {
    monta();
    fireEvent.click(screen.getByRole("button", { name: "Oggi" }));
    expect(screen.getByRole("button", { name: "Oggi" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/Dalla chiusura di ieri/)).toBeTruthy();
  });

  it("un intervallo senza periodo lo dice invece di inventare un numero", () => {
    monta();
    fireEvent.click(screen.getByRole("button", { name: "3M" }));
    expect(screen.getByText("Rendimento del periodo non ancora calcolabile.")).toBeTruthy();
  });

  it("senza storico la curva lo dice, mentre carica pulsa", () => {
    andamento = { configurato: true, giorni: [], oggi: [], periodi: [] };
    monta({ ...VIVO, valore: null });
    expect(screen.getByText("Storico non ancora disponibile.")).toBeTruthy();
  });

  it("chi muove il conto: in ordine, col link solo se il titolo e' nel catalogo", () => {
    monta();
    const lista = screen.getByText("Chi muove il conto oggi").parentElement!;
    const righe = within(lista).getAllByRole("listitem");
    expect(righe.map((r) => r.textContent)).toEqual([
      expect.stringContaining("SOXL"), expect.stringContaining("SMCI"), expect.stringContaining("XYZ"),
    ]);
    expect(within(righe[0]).getByRole("link", { name: "SOXL" }).getAttribute("href")).toBe("/stocks/SOXL");
    expect(within(righe[2]).queryByRole("link")).toBeNull();
  });

  it("nessuna violazione strutturale", async () => {
    const { container } = monta();
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toHaveLength(0);
  });
});
