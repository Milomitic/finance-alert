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

/** Le righe dati di una vista, senza la testata. */
function righe(container: HTMLElement, vista: "detentori" | "operazioni") {
  return [...container.querySelectorAll(`ul[data-vista=${vista}] > li`)].slice(1) as HTMLElement[];
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

  it("una linea per fondo: nome, barra, peso, movimento e valore nella stessa riga", () => {
    dati = {
      ticker: "AAPL",
      holders: [
        fondo(1, "Dorsey Asset Management", { portfolio_pct: 8.5, value_usd: 132.16e6, action: "add", portfolio_weight_delta_pp: 3 }),
        fondo(2, "Dodge & Cox", { portfolio_pct: 2.4, value_usd: 4.55e9, action: "reduce", portfolio_weight_delta_pp: -0.1 }),
      ],
      historical: [],
    };
    const { container } = monta();
    // Per valore: Dodge & Cox ($4.55B) prima di Dorsey ($132M).
    const [seconda, prima] = righe(container, "detentori");
    // Un solo livello: i cinque campi sono figli diretti della stessa griglia.
    expect(prima.children).toHaveLength(5);
    expect(within(prima).getByRole("link", { name: "Dorsey Asset Management" })).toBeInTheDocument();
    expect(within(prima).getByText("$132.16M")).toBeInTheDocument();
    expect(within(prima).getByText("8.5%")).toBeInTheDocument();
    expect(within(prima).getByText("+3.0 pp").className).toContain("emerald");
    expect(within(seconda).getByText("−0.1 pp").className).toContain("rose");
    // Testata e righe hanno la stessa griglia: le colonne si allineano.
    const testata = container.querySelector("ul[data-vista=detentori] > li")!;
    const colonne = "sm:grid-cols-[minmax(0,1fr)_4.5rem_2.75rem_3.5rem_4rem]";
    expect(testata.className).toContain(colonne);
    expect(prima.className).toContain(colonne);
    // Il piu' pesante riempie la barra, l'altro in proporzione.
    const barre = [...container.querySelectorAll('span[class~="bg-primary/80"]')].map((b) => (b as HTMLElement).style.width);
    expect(barre[1]).toBe("100%");
    expect(parseFloat(barre[0])).toBeCloseTo((2.4 / 8.5) * 100, 1);
  });

  it("sempre per valore, e subito solo le posizioni da 10 milioni in su", async () => {
    dati = {
      ticker: "AAPL",
      holders: [
        fondo(1, "Piccolo", { portfolio_pct: 30, value_usd: 4e6 }),
        fondo(2, "Grande", { portfolio_pct: 1, value_usd: 2e9 }),
        fondo(3, "Medio", { portfolio_pct: 5, value_usd: 10e6 }),
        fondo(4, "Minimo", { portfolio_pct: 0.1, value_usd: 1e5 }),
      ],
      historical: [],
    };
    const { container } = monta();
    const nomi = () => righe(container, "detentori").map((li) => li.querySelector("a")?.textContent);
    expect(nomi()).toEqual(["Grande", "Medio"]);
    // Niente piu' scelta dell'ordinamento.
    expect(screen.queryByRole("button", { name: "Peso" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Mostra altri 2 (sotto $10M)" }));
    expect(nomi()).toEqual(["Grande", "Medio", "Piccolo", "Minimo"]);
    // Il riepilogo conta tutti, mostrati o no.
    expect(screen.getByText("Fondi").nextSibling?.textContent).toBe("4");
  });

  it("le due viste hanno la stessa riga", async () => {
    dati = { ticker: "AAPL", holders: [fondo(1, "Dorsey Asset Management", { value_usd: 5e8 })], historical: [] };
    const { container } = monta();
    const riga = (v: "detentori" | "operazioni") => righe(container, v)[0].className.replace(/grid-cols-\S+|sm:grid-cols-\S+|min-w-\S+|md:min-w-0/g, "").split(/\s+/).filter(Boolean).join(" ");
    const detentori = riga("detentori");
    await userEvent.click(screen.getByRole("button", { name: "Ultime operazioni" }));
    expect(riga("operazioni")).toBe(detentori);
  });

  it("le ultime operazioni: il verbo e la data, uscite comprese, dalla piu' recente", async () => {
    dati = {
      ticker: "AAPL",
      holders: [
        fondo(1, "Dorsey Asset Management", { action: "add", period_end_date: "2026-03-31" }),
        fondo(2, "Dodge & Cox", { action: "new" }),
      ],
      historical: [
        fondo(9, "AKO Capital", { action: "sold_out", period_end_date: "2026-06-30", value_usd: 210.19e6 }),
        // Un fondo ancora presente non si ripete fra le uscite.
        fondo(1, "Dorsey Asset Management", { action: "sold_out", period_end_date: "2025-12-31" }),
      ],
    };
    const { container } = monta();
    expect(screen.queryByText("AKO Capital")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Ultime operazioni" }));
    expect(screen.getByRole("button", { name: "Ultime operazioni" })).toHaveAttribute("aria-pressed", "true");
    const r = righe(container, "operazioni");
    expect(r.map((li) => li.querySelector("a")?.textContent)).toEqual(["AKO Capital", "Dodge & Cox", "Dorsey Asset Management"]);
    expect(within(r[0]).getByText("Sold out")).toBeInTheDocument();
    expect(within(r[1]).getByText("Nuovo")).toBeInTheDocument();
    expect(within(r[2]).getByText("31/03/26")).toBeInTheDocument();
    // Il nome della scheda resta lo stesso in entrambe le viste.
    expect(screen.getByText("Superinvestor / fondi")).toBeInTheDocument();
  });

  it("senza fondi lo dice", () => {
    dati = { ticker: "AAPL", holders: [], historical: [] };
    monta();
    expect(screen.getByText("Nessun fondo tracciato detiene questo titolo.")).toBeInTheDocument();
  });
});
