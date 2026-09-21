import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AnalystRating } from "@/api/types";

import { AnalystTargetCard } from "./AnalystTargetCard";

/* ─── Le etichette buy/hold/sell non vanno MAI a capo ──────────────────────
 *
 * Con 20 buy e 1 hold l'etichetta «1 hold» riceveva il 4,8% della riga —
 * circa 30px — e andava su due righe, raddoppiando l'altezza della scheda per
 * il numero piu' piccolo che porta.
 *
 * ⚠️ jsdom non fa layout, quindi «non va a capo» non si puo' misurare qui: si
 * fissano le due proprieta' che lo garantiscono nel browser, e che il difetto
 * non aveva. Una larghezza percentuale e' la forma del difetto, quindi il
 * controllo negativo pretende che non ci sia.
 */

const ratings: AnalystRating[] = [
  { period: "0m", strong_buy: 8, buy: 12, hold: 1, sell: 0, strong_sell: 0 },
];

vi.mock("@/hooks/useStockFundamentals", () => ({
  useStockFundamentals: () => ({
    isLoading: false,
    data: { price_target: null, analyst_ratings: ratings, analyst_actions: [], fetched_at: null },
  }),
}));

function monta() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AnalystTargetCard ticker="NVDA" currency="USD" />
    </QueryClientProvider>,
  );
}

describe("AnalystTargetCard — barra delle raccomandazioni", () => {
  it("un'etichetta minoritaria resta su una riga", () => {
    monta();
    const hold = screen.getByText("1 hold");
    expect(hold).toHaveClass("whitespace-nowrap");
    // Il pavimento: non scende sotto il proprio contenuto.
    expect(hold).toHaveClass("min-w-max");
  });

  it("⚠️ la quota e' una crescita flex, non una larghezza", () => {
    monta();
    const hold = screen.getByText("1 hold");
    const buy = screen.getByText("20 buy");
    expect(hold.style.width).toBe("");
    expect(buy.style.width).toBe("");
    // Proporzionali ai conteggi finche' c'e' spazio.
    expect(hold.style.flexGrow).toBe("1");
    expect(buy.style.flexGrow).toBe("20");
  });

  it("la categoria a zero non ha etichetta", () => {
    monta();
    expect(screen.queryByText(/sell/)).toBeNull();
  });
});
