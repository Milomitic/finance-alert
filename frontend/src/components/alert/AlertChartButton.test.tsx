import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { AlertChartButton, type AlertChartLink } from "./AlertChartButton";

/* «Mostra sul grafico» (FA-066). Tre stati: nessun grafico, grafico senza
 * quella barra, grafico con la barra. */

const alert = { id: 9, ticker: "ACME", signal_date: "2026-08-10" } as unknown as Alert;

const grafico = (has: boolean, ordine: string[] = []): AlertChartLink => ({
  has: () => has,
  show: vi.fn(() => {
    ordine.push("mostra");
  }),
});

describe("AlertChartButton", () => {
  it("senza grafico non offre niente", () => {
    const { container } = render(<AlertChartButton alert={alert} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("se la barra non e' caricata dice perche', invece di un bottone muto", () => {
    render(<AlertChartButton alert={alert} chart={grafico(false)} onClose={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/allarga l'intervallo/i)).toBeInTheDocument();
  });

  it("con la barra caricata chiude il dialogo e POI sposta il grafico", async () => {
    const ordine: string[] = [];
    const g = grafico(true, ordine);
    const onClose = vi.fn(() => {
      ordine.push("chiudi");
    });
    render(<AlertChartButton alert={alert} chart={g} onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: /mostra sul grafico/i }));

    expect(g.show).toHaveBeenCalledWith(alert);
    // ⚠️ L'ordine: il dialogo copre il grafico, e spostarlo sotto un modale
    // aperto e' un'azione che nessuno vede.
    expect(ordine).toEqual(["chiudi", "mostra"]);
  });
});
