import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Flag, Zap } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import { axeViolations, describeViolations } from "@/test/axe";

import { SchedePagina } from "./schede-pagina";

/* Il componente unico delle schede di pagina: Segnali, Diagnostica,
 * Superinvestor, Calendario, e il sotto-selettore di Esiti. */

const VOCI = [
  { id: "segnali", label: "Segnali", icon: Zap, descrizione: "Segnali scattati" },
  { id: "esiti", label: "Esiti", icon: Flag, descrizione: "Come si sono chiusi" },
] as const;

function monta(opts: { attiva?: "segnali" | "esiti"; dimensione?: "grande" | "compatta" } = {}) {
  const onCambia = vi.fn();
  const r = render(
    <SchedePagina
      voci={VOCI}
      attiva={opts.attiva ?? "segnali"}
      onCambia={onCambia}
      etichetta="Scheda"
      dimensione={opts.dimensione}
    />,
  );
  return { onCambia, ...r };
}

describe("SchedePagina", () => {
  it("una sola scheda e' attiva, e lo dice", () => {
    monta({ attiva: "esiti" });
    expect(screen.getByRole("button", { name: "Esiti" })).toHaveAttribute("aria-pressed", "true");
    // Il controllo negativo: due schede attive non direbbero dove si e'.
    expect(screen.getByRole("button", { name: "Segnali" })).toHaveAttribute("aria-pressed", "false");
  });

  it("cliccare una scheda chiede quella", async () => {
    const { onCambia } = monta();
    await userEvent.click(screen.getByRole("button", { name: "Esiti" }));
    expect(onCambia).toHaveBeenCalledWith("esiti");
  });

  it("⚠️ il nome e' l'etichetta sola; la descrizione arriva come DESCRIZIONE", () => {
    // Col nome calcolato dal contenuto, «Esiti» diventerebbe «Esiti Come si
    // sono chiusi» e ogni ricerca per nome smetterebbe di trovarla.
    monta();
    const esiti = screen.getByRole("button", { name: "Esiti" });
    expect(esiti).toHaveAccessibleName("Esiti");
    expect(esiti).toHaveAccessibleDescription("Come si sono chiusi");
  });

  it("non promette un tabpanel", () => {
    monta();
    for (const b of screen.getAllByRole("button")) {
      expect(b).not.toHaveAttribute("aria-controls");
      expect(b).not.toHaveAttribute("role", "tab");
    }
  });

  it("la scheda attiva ha la barra sotto e l'icona nel colore primario", () => {
    const { container } = monta();
    const [attiva, altra] = screen.getAllByRole("button");
    expect(attiva.querySelector("span.bg-primary")).not.toBeNull();
    expect(altra.querySelector("span.bg-primary")).toBeNull();
    expect(attiva.querySelector("svg")?.getAttribute("class")).toMatch(/text-primary/);
    expect(container.firstElementChild).toHaveAttribute("aria-label", "Scheda");
  });

  it("la taglia compatta non rende la descrizione, e non vi rimanda", () => {
    // Un `aria-describedby` verso un id che non c'e' e' la relazione
    // inventata che il componente esiste per evitare.
    monta({ dimensione: "compatta" });
    for (const b of screen.getAllByRole("button")) {
      expect(b).not.toHaveAttribute("aria-describedby");
    }
    expect(screen.queryByText("Come si sono chiusi")).not.toBeInTheDocument();
  });

  it("axe: nessuna violazione strutturale", async () => {
    const { container } = monta();
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toHaveLength(0);
  });
});
