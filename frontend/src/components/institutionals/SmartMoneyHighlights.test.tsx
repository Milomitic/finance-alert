import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ActionAggregate, AggregateStats, InstitutionalSummary } from "@/api/types";

import { SmartMoneyHighlights } from "./SmartMoneyHighlights";

function mossa(
  ticker: string, action: string, value_usd: number | null, extra: Partial<ActionAggregate> = {},
): ActionAggregate {
  return {
    ticker, company_name: `${ticker} Corp`, institutional_slug: "berkshire",
    institutional_name: "Berkshire Hathaway", period_end_date: "2026-06-30",
    action, qoq_change_pct: 12.5, portfolio_pct: 4.2, value_usd, stock_id: 1, ...extra,
  };
}

function fondo(slug: string, periodo: string | null, valore: number | null): InstitutionalSummary {
  return {
    id: 1, slug, name: slug, manager_name: null, type: "superinvestor", source: "sec",
    source_url: null, description: null, aum_usd: null, latest_period_end: periodo,
    total_value_usd: valore, total_positions: 10,
  };
}

const AGG: AggregateStats = {
  most_picked: [{
    ticker: "AAPL", company_name: "Apple", holder_count: 42, total_value_usd: 9e10,
    total_pct_sum: 120, holders: ["a", "b"], stock_id: 1, stock_country: "US", stock_sector: "Tech",
  }],
  recent_buys: [mossa("NVDA", "new", 1.2e9), mossa("MSFT", "add", 3e8)],
  recent_sells: [mossa("TSLA", "sold_out", 8e8), mossa("META", "reduce", 2e8)],
  sector_tilt: { "Information Technology": 600, Energy: 400 },
};

const FONDI = [
  fondo("a", "2026-06-30", 1e9),
  fondo("b", "2026-03-31", 5e8),
  fondo("c", "2024-12-31", 1e8), // fermo da oltre due trimestri
];

function monta(agg: AggregateStats | undefined = AGG, fondi = FONDI) {
  return render(
    <MemoryRouter>
      <SmartMoneyHighlights agg={agg} fondi={fondi} />
    </MemoryRouter>,
  );
}

describe("le statistiche dicono su che base sono calcolate", () => {
  it("il trimestre porta accanto quanti fondi ci sono arrivati", () => {
    /* Senza, «ultimo trimestre: 30/06/26» lascia credere che la fotografia sia
     * completa, mentre i 13F arrivano scaglionati per 45 giorni. */
    monta();
    expect(screen.getByText("30/06/26")).toBeInTheDocument();
    expect(screen.getByText("1 fondi su 3 ci sono arrivati")).toBeInTheDocument();
  });

  it("dice quanti fondi sono fermi, invece di contarli come vivi", () => {
    monta();
    expect(screen.getByText("1 fermi da oltre 2 trimestri")).toBeInTheDocument();
  });

  it("senza portafogli dichiarati il capitale e' n/d, non zero", () => {
    // Zero direbbe «non possiedono niente»: e' un'affermazione, non un'assenza.
    monta(AGG, [fondo("x", "2026-06-30", null)]);
    expect(screen.getByText("n/d")).toBeInTheDocument();
  });

  it("il settore piu' pesato porta la sua quota sul capitale", () => {
    monta();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("Information Technology")).toBeInTheDocument();
  });
});

describe("le mosse", () => {
  it("ordinate per valore della posizione, la piu' grossa in cima", () => {
    monta();
    const comprato = screen.getByRole("region", { name: /Comprato/ });
    const righe = within(comprato).getAllByRole("listitem");
    expect(within(righe[0]).getByText("NVDA")).toBeInTheDocument();
    expect(within(righe[1]).getByText("MSFT")).toBeInTheDocument();
  });

  it("aprire e chiudere del tutto si leggono in italiano e in evidenza", () => {
    // Le costanti del backend sono in inglese e comparivano crude: «new»,
    // «sold_out». E una pastiglia piena distingue la mossa netta dalla
    // manutenzione di una posizione che c'era gia'.
    monta();
    expect(screen.getByText("nuova").className).toContain("bg-emerald-100");
    expect(screen.getByText("uscita").className).toContain("bg-rose-100");
    expect(screen.getByText("aumento").className).toContain("border");
    expect(screen.getByText("aumento").className).not.toContain("bg-emerald-100");
  });

  it("⚠️ il contenitore che scorre ha un nome ed e' raggiungibile da tastiera", () => {
    /* Il gate UI l'aveva gia' trovato sulle schede che questa fascia
     * sostituisce: cio' che sta oltre il taglio non esiste per chi non usa il
     * mouse. */
    monta();
    expect(screen.getByRole("region", { name: /Venduto/ })).toHaveAttribute("tabindex", "0");
  });

  it("una colonna vuota lo dice, invece di restare bianca", () => {
    monta({ ...AGG, recent_sells: [] });
    expect(screen.getByText(/Nessuna mossa di questo tipo/)).toBeInTheDocument();
  });

  it("dichiara il modello editoriale: il 13F e' long-only", () => {
    // «Comprato» non vuol dire «lungo contro corto»: senza questa riga il
    // lettore puo' leggerci un posizionamento che il 13F non descrive.
    monta();
    expect(screen.getByText(/long-only/)).toBeInTheDocument();
  });
});

describe("senza dati non inventa una pagina", () => {
  it("regge un aggregato assente", () => {
    /* ⚠️ NON si passa `undefined` a `monta`: un argomento `undefined` attiva il
     * valore di DEFAULT del parametro, quindi il componente riceverebbe
     * l'aggregato pieno e il test verificherebbe uno stato che non ha mai
     * creato — la famiglia «vero di niente» di CLAUDE.md, in versione
     * JavaScript. Qui si rende direttamente. */
    render(
      <MemoryRouter>
        <SmartMoneyHighlights agg={undefined} fondi={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Le mosse che contano")).toBeInTheDocument();
    expect(screen.getAllByText(/Nessuna mossa di questo tipo/)).toHaveLength(2);
  });
});
