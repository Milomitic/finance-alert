import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EtoroCosti } from "@/api/etoro";
import { filtersFromSearch, searchFromState } from "@/lib/alertFilters";
import type { Playbook } from "@/lib/tradePlaybook";
import { axeViolations, describeViolations } from "@/test/axe";

import { CostiEtoroPiano } from "./CostiEtoroPiano";

/* ─── Il costo del piano su eToro (FA-126) ────────────────────────────────
 * Il preventivo e' quello vero di SOXL ×5 con 500 USD, letto dal pod il
 * 2026-10-06: 3,75 di commissione, 0,77 di spread, 0,71 a notte. */

let costi: EtoroCosti | undefined;
let errore = false;
const chiesto = vi.fn();

vi.mock("@/hooks/useEtoro", () => ({
  useEtoroCosti: (p: unknown) => {
    chiesto(p);
    return { data: costi, isError: errore };
  },
}));

const PIANO: Playbook = {
  side: "long", action: "Long", horizon: "Medio", entry: 50, stop: 47, stopPct: 6, stopCapped: false,
  targets: [], duration: "2 - 6 settimane", riskBudgetPct: 1, positionPct: 100, leverage: 1, leverageNote: "",
};

const VERO: EtoroCosti = {
  configurato: true, disponibile: true, simbolo: "SOXL", apertura_usd: 4.52, notte_usd: 0.71, weekend_usd: 0,
  aggiornato_il: "2026-10-05T16:46:34Z",
  voci: [
    { tipo: "transactionFee", importo: 3.75, valuta: "USD", importo_usd: 3.75 },
    { tipo: "marketSpread", importo: 0.77, valuta: "USD", importo_usd: 0.77 },
    { tipo: "overnightFee", importo: 0.71, valuta: "USD", importo_usd: 0.71 },
  ],
};

beforeEach(() => {
  costi = VERO;
  errore = false;
  chiesto.mockReset();
});

describe("CostiEtoroPiano", () => {
  it("apertura, notti della tenuta, totale in % del margine e in R", () => {
    render(<CostiEtoroPiano ticker="SOXL" playbook={PIANO} />);
    expect(screen.getByText("$4.52")).toBeTruthy();
    expect(screen.getByText("$0.71/notte")).toBeTruthy();
    expect(screen.getByText("×28 notti")).toBeTruthy();
    expect(screen.getByText("$24.40")).toBeTruthy();
    expect(screen.getByText("+4.9% del margine · 0.16 R")).toBeTruthy();
    expect(screen.getByText("-30.0%")).toBeTruthy();
  });

  it("parte dalla leva del conto, ×5, e la cambia a richiesta", () => {
    render(<CostiEtoroPiano ticker="SOXL" playbook={PIANO} />);
    expect(screen.getByRole("button", { name: "×5" }).getAttribute("aria-pressed")).toBe("true");
    expect(chiesto).toHaveBeenLastCalledWith({ ticker: "SOXL", lato: "long", leva: 5, importo: 500, stop: 47 });
    fireEvent.click(screen.getByRole("button", { name: "×2" }));
    expect(chiesto).toHaveBeenLastCalledWith(expect.objectContaining({ leva: 2 }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "1000" } });
    expect(chiesto).toHaveBeenLastCalledWith(expect.objectContaining({ importo: 1000 }));
  });

  it("senza eToro collegato non compare", () => {
    costi = { ...VERO, configurato: false, disponibile: false };
    const { container } = render(<CostiEtoroPiano ticker="SOXL" playbook={PIANO} />);
    expect(container.textContent).toBe("");
  });

  it("un titolo non su eToro lo dice", () => {
    costi = { ...VERO, disponibile: false };
    render(<CostiEtoroPiano ticker="ZZZZ" playbook={PIANO} />);
    expect(screen.getByText("ZZZZ non risulta negoziabile su eToro.")).toBeTruthy();
  });

  it("un overnight in valuta ignota non diventa un totale", () => {
    costi = { ...VERO, notte_usd: null };
    render(<CostiEtoroPiano ticker="ENI.MI" playbook={PIANO} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("un errore di eToro si dice", () => {
    costi = undefined;
    errore = true;
    render(<CostiEtoroPiano ticker="SOXL" playbook={PIANO} />);
    expect(screen.getByText(/Preventivo eToro non disponibile/)).toBeTruthy();
  });

  it("nessuna violazione strutturale", async () => {
    const { container } = render(<CostiEtoroPiano ticker="SOXL" playbook={PIANO} />);
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toHaveLength(0);
  });
});

describe("il filtro «Negoziabili su eToro» nella lista segnali", () => {
  it("va e torna dall'URL", () => {
    const sp = searchFromState({ solo_etoro: true }, 0, "rilevanza", "desc", new URLSearchParams());
    expect(sp.get("solo_etoro")).toBe("true");
    expect(filtersFromSearch(sp).solo_etoro).toBe(true);
    expect(filtersFromSearch(new URLSearchParams()).solo_etoro).toBeUndefined();
  });
});
