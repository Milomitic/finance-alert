import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Position } from "@/api/types";

import { AzioniPosizione } from "./AzioniPosizione";

/* D-34: chiudere ed eliminare chiedono un secondo tocco dell'app, non un
 * confirm() del browser, e il primo tocco di «Chiudi» dice il risultato. */

const aperta = { id: 7, ticker: "AAPL", closed_at: null, unrealized_pct: 3.24, realized_pct: null } as unknown as Position;

describe("AzioniPosizione", () => {
  it("chiudere: il primo tocco dice il P/L, il secondo chiude", async () => {
    const onClose = vi.fn();
    render(<AzioniPosizione p={aperta} onClose={onClose} onDelete={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Chiudi AAPL al prezzo corrente" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Chiudi · P/L +3,2%?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Conferma: chiudi AAPL/ }));
    expect(onClose).toHaveBeenCalledWith(aperta);
  });

  it("eliminare chiede il secondo tocco, e il cestino ha un nome", async () => {
    const onDelete = vi.fn();
    render(<AzioniPosizione p={aperta} onDelete={onDelete} />);
    await userEvent.click(screen.getByRole("button", { name: "Elimina la posizione su AAPL" }));
    expect(onDelete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Conferma: elimina la posizione su AAPL" }));
    expect(onDelete).toHaveBeenCalledWith(aperta);
  });

  it("senza onClose (posizione chiusa) c'e' solo Elimina", () => {
    render(<AzioniPosizione p={{ ...aperta, closed_at: "2026-11-20" } as Position} onDelete={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Chiudi/ })).toBeNull();
  });
});
