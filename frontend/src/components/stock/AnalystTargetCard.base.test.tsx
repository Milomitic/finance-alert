import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalystPriceTarget } from "@/api/types";

import { AnalystTargetCard } from "./AnalystTargetCard";

/* ─── La card Analyst dichiara su QUALE prezzo calcola l'upside ────────────
 *
 * Il backend ora mette in `price_target.current` l'ultima chiusura
 * memorizzata — la stessa base della card Stock Score — con la sua data in
 * `current_as_of`. Prima era il prezzo allegato da yfinance, vecchio fino a
 * sette giorni, e le due card davano due upside diversi dello stesso target
 * (`backend/tests/test_base_prezzo_unica_fra_schede.py`).
 *
 * Qui si fissa la meta' visibile: il marcatore non dice piu' «ora» (non e' il
 * prezzo live), dice di quale giorno e' la chiusura, e il prezzo e' nella
 * valuta del titolo invece di un `$` scritto a mano.
 */

let pt: AnalystPriceTarget;

vi.mock("@/hooks/useStockFundamentals", () => ({
  useStockFundamentals: () => ({
    isLoading: false,
    data: { price_target: pt, analyst_ratings: [], analyst_actions: [], fetched_at: null },
  }),
}));

function monta(currency: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <AnalystTargetCard ticker="ENEL.MI" currency={currency} />
    </QueryClientProvider>,
  );
}

describe("AnalystTargetCard — base dell'upside", () => {
  beforeEach(() => {
    pt = { current: 55.41, current_as_of: "2026-09-14", low: 50, mean: 67.43, median: 68, high: 80 };
  });

  it("il marcatore porta la data della chiusura, non «ora»", () => {
    monta("EUR");
    expect(screen.getByText("14/09")).toBeInTheDocument();
    expect(screen.queryByText("ora")).toBeNull();
  });

  it("l'upside e' calcolato sulla chiusura", () => {
    monta("EUR");
    // (67.43 / 55.41 - 1) * 100 = 21.7
    expect(screen.getByText(/\+21\.7%/)).toBeInTheDocument();
  });

  it("il prezzo e' nella valuta del titolo, non in dollari", () => {
    const { container } = monta("EUR");
    expect(container.textContent).not.toContain("$55.41");
  });

  it("senza data la base non finge di essere una chiusura", () => {
    pt = { ...pt, current_as_of: null };
    monta("EUR");
    expect(screen.queryByText("14/09")).toBeNull();
    expect(screen.getByText("prezzo")).toBeInTheDocument();
  });
});
