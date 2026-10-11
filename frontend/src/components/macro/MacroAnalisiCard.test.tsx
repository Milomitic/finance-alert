import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MacroAnalisi } from "@/api/types";

import { MacroAnalisiCard } from "./MacroAnalisiCard";

const CPI: MacroAnalisi = {
  ultima: 0.396, media: 0.27, dev_std: 0.18, zscore: 0.7, percentile: 74, annualizzata_3m: 3.1,
  serie: 3, n_variazioni: 39, massimo: 334.131, massimo_il: "2026-08-01", minimo: 307.3, minimo_il: "2023-09-01",
  reazione_n: 16, reazione_rilascio: 0.92, reazione_altri: 0.61,
  reazione_ultimi: [{ data: "2026-09-11", rendimento: 0.8 }, { data: "2026-08-12", rendimento: -1.1 }],
  correlazione_r: 0.12, correlazione_n: 39, correlazione_dal: "2023-06-01", correlazione_al: "2026-08-01",
};

describe("MacroAnalisiCard", () => {
  it("i numeri con il loro campione", () => {
    render(<MacroAnalisiCard a={CPI} unita="%" valueKind="index" sourceScale={null} esitoUltima="sotto" />);
    // L'ultima variazione e' positiva ma sotto la sua stima: rossa.
    expect(screen.getByText("+0.4%").className).toContain("rose");
    // Le statistiche non hanno una stima: nessun colore di segno.
    expect(screen.getByText("+0.3%").className).not.toMatch(/emerald|rose/);
    expect(screen.getByText(/più alta del 74% dei periodi/)).toBeInTheDocument();
    expect(screen.getByText(/su 39 periodi/)).toBeInTheDocument();
    expect(screen.getByText(/3 rialzi/)).toBeInTheDocument();
    expect(screen.getByText("±0.9%")).toBeInTheDocument();
    expect(screen.getByText(/16 rilasci/)).toBeInTheDocument();
    expect(screen.getByText(/debole positiva/)).toBeInTheDocument();
    expect(screen.getByText(/39 mesi/)).toBeInTheDocument();
  });

  it("dove i dati non bastano lo dice, e la scheda non cambia forma", () => {
    render(<MacroAnalisiCard a={{ ultima: 0.25, n_variazioni: 5, serie: 0 }} unita="pp" valueKind="pct" sourceScale={null} />);
    expect(screen.getByText("+0.25 pp")).toBeInTheDocument();
    expect(screen.getByText(/Servono almeno 12 variazioni/)).toBeInTheDocument();
    expect(screen.getByText(/Servono almeno 6 rilasci/)).toBeInTheDocument();
    expect(screen.getAllByText("Non applicabile").length).toBeGreaterThanOrEqual(2);
    // Sette tessere in tutti e due i casi.
    expect(screen.getAllByRole("button").length).toBeGreaterThanOrEqual(7);
  });
});
