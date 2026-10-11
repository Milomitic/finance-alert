import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { TickerHolder, TickerHolders } from "@/api/types";

let dati: TickerHolders = { ticker: "AAPL", holders: [], historical: [] };
const chiamate: unknown[][] = [];
vi.mock("@/hooks/useInstitutionals", () => ({
  useTickerInstitutionalHolders: (...a: unknown[]) => {
    chiamate.push(a);
    return { data: dati, isLoading: false };
  },
}));

const { InstitutionalHoldersCard } = await import("./InstitutionalHoldersCard");

function fondo(id: number, nome: string, extra: Partial<TickerHolder> = {}): TickerHolder {
  return {
    institutional_id: id, institutional_slug: `f${id}`, institutional_name: nome, institutional_manager: null,
    institutional_type: "superinvestor", period_end_date: "2026-06-30", shares: 100, value_usd: 1e6,
    portfolio_pct: 1, shares_change_pct: null, portfolio_weight_delta_pp: null, action: "hold", ...extra,
  } as TickerHolder;
}

function monta() {
  return render(<MemoryRouter><InstitutionalHoldersCard ticker="AAPL" /></MemoryRouter>);
}

describe("la scheda dei fondi che detengono il titolo", () => {
  it("in testa quanti fondi e quanto valgono in tutto", () => {
    dati = {
      ticker: "AAPL",
      holders: [
        fondo(1, "Dorsey Asset Management", { portfolio_pct: 8.5, value_usd: 132.16e6, action: "add", portfolio_weight_delta_pp: 3 }),
        fondo(2, "Dodge & Cox", { portfolio_pct: 2.4, value_usd: 4.55e9 }),
      ],
      historical: [],
    };
    monta();
    expect(screen.getByText("Fondi").nextSibling?.textContent).toBe("2");
    expect(screen.getByText("Valore detenuto").nextSibling?.textContent).toBe("$4.68B");
    // Tutti i detentori, non la prima pagina: il totale sarebbe falso.
    expect(chiamate.at(-1)).toEqual(["AAPL", 200, true]);
  });

  it("il nome intero, il valore, e la barra del peso sulla stessa scala", () => {
    dati = {
      ticker: "AAPL",
      holders: [
        fondo(1, "Dorsey Asset Management", { portfolio_pct: 8.5, value_usd: 132.16e6, action: "add", portfolio_weight_delta_pp: 3 }),
        fondo(2, "Dodge & Cox", { portfolio_pct: 2.4, value_usd: 4.55e9, action: "reduce", portfolio_weight_delta_pp: -0.1 }),
      ],
      historical: [],
    };
    const { container } = monta();
    expect(screen.getByRole("link", { name: "Dorsey Asset Management" })).toBeInTheDocument();
    const righe = container.querySelectorAll("ul > li");
    expect(within(righe[0] as HTMLElement).getByText("$132.16M")).toBeInTheDocument();
    expect(within(righe[0] as HTMLElement).getByText("8.5%")).toBeInTheDocument();
    expect(within(righe[0] as HTMLElement).getByText("+3.0 pp").className).toContain("emerald");
    expect(within(righe[1] as HTMLElement).getByText("−0.1 pp").className).toContain("rose");
    // Il piu' pesante riempie la barra, l'altro in proporzione.
    const barre = [...container.querySelectorAll("ul > li span.bg-primary\\/80")].map((b) => (b as HTMLElement).style.width);
    expect(barre[0]).toBe("100%");
    expect(parseFloat(barre[1])).toBeCloseTo((2.4 / 8.5) * 100, 1);
  });

  it("per valore al click, e i primi dieci con il resto a richiesta", async () => {
    dati = {
      ticker: "AAPL",
      holders: Array.from({ length: 12 }, (_, i) => fondo(i + 1, `Fondo ${i + 1}`, { portfolio_pct: 12 - i, value_usd: (i + 1) * 1e6 })),
      historical: [],
    };
    const { container } = monta();
    const nomi = () => [...container.querySelectorAll("ul > li a")].map((a) => a.textContent);
    expect(nomi()).toHaveLength(10);
    expect(nomi()[0]).toBe("Fondo 1");
    await userEvent.click(screen.getByRole("button", { name: "valore" }));
    expect(nomi()[0]).toBe("Fondo 12");
    await userEvent.click(screen.getByRole("button", { name: "Mostra tutti i 12" }));
    expect(nomi()).toHaveLength(12);
  });

  it("i fondi usciti stanno a parte, chiusi", async () => {
    dati = {
      ticker: "AAPL",
      holders: [fondo(1, "Dorsey Asset Management")],
      historical: [fondo(9, "AKO Capital", { action: "sold_out", portfolio_pct: 4.1, value_usd: 210.19e6 })],
    };
    monta();
    expect(screen.queryByText("AKO Capital")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Usciti di recente \(1\)/ }));
    expect(screen.getByText("AKO Capital")).toBeInTheDocument();
  });

  it("senza fondi lo dice", () => {
    dati = { ticker: "AAPL", holders: [], historical: [] };
    monta();
    expect(screen.getByText("Nessun fondo tracciato detiene questo titolo.")).toBeInTheDocument();
  });
});
