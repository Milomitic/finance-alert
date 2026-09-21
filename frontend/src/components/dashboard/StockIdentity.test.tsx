import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StockIdentity } from "./StockIdentity";

/* La forma `riga` delle card della home: ticker e nome sulla STESSA riga, e
 * il nome mai su telefono.
 *
 * ⚠️ jsdom non applica i media query, quindi «nascosto sotto sm» non si vede
 * qui: si fissano le classi che lo fanno nel browser. */
describe("StockIdentity", () => {
  it("in riga: ticker e nome nello stesso contenitore, non impilati", () => {
    render(<StockIdentity ticker="PURR" name="Hyperliquid Strategies Inc." forma="riga" />);
    const ticker = screen.getByText("PURR");
    const nome = screen.getByText("Hyperliquid Strategies Inc.");
    expect(ticker.parentElement).toBe(nome.parentElement);
    expect(ticker.parentElement).toHaveClass("flex");
  });

  it("in riga il nome sparisce su telefono e il ticker non si stringe mai", () => {
    render(<StockIdentity ticker="PURR" name="Hyperliquid Strategies Inc." forma="riga" />);
    expect(screen.getByText("Hyperliquid Strategies Inc.")).toHaveClass("hidden", "sm:block", "truncate");
    // Quando lo spazio manca cede la decorazione, non l'identita'.
    expect(screen.getByText("PURR")).toHaveClass("shrink-0");
  });

  it("la forma impilata resta quella di prima dove non la si cambia", () => {
    // Controllo negativo: le tabelle dei settori non l'hanno chiesta.
    render(<StockIdentity ticker="PURR" name="Hyperliquid Strategies Inc." />);
    // Due blocchi uno sopra l'altro, e il nome visibile a ogni larghezza.
    expect(screen.getByText("PURR").tagName).toBe("DIV");
    expect(screen.getByText("Hyperliquid Strategies Inc.").tagName).toBe("DIV");
    expect(screen.getByText("Hyperliquid Strategies Inc.")).not.toHaveClass("hidden");
  });
});
