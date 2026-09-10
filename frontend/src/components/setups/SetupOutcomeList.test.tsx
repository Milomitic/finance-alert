import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Setup } from "@/hooks/useSetups";

import { SetupOutcomeList } from "./SetupOutcomeList";

/* Un setup convertito porta al segnale in cui e scattato.
 *
 * `converted_alert_id` viene scritto quando l'alert nasce — un fatto
 * registrato, non un'inferenza — e arrivava fino al tipo del frontend senza
 * essere reso, esattamente come `Position.alert_id`. I due insieme rendono
 * percorribile la catena che i dati contengono da sempre: setup → segnale →
 * posizione.
 */

function setup(over: Partial<Setup> = {}): Setup {
  return {
    id: 1,
    ticker: "AMD",
    name: "AMD Inc.",
    detector: "trend_pullback",
    tone: "bull",
    proximity: 0.8,
    distance_atr: 0.4,
    convenience: 62,
    missing: "chiusura sopra la EMA20",
    first_seen_at: "2026-08-01T00:00:00Z",
    last_seen_at: "2026-08-12T00:00:00Z",
    annotations: null,
    status: "converted",
    resolved_at: "2026-08-12T00:00:00Z",
    lead_days: 11,
    converted_alert_id: 77,
    ...over,
  };
}

function renderList(setups: Setup[], onOpenSignal = vi.fn()) {
  render(
    <MemoryRouter>
      <SetupOutcomeList setups={setups} onOpenSignal={onOpenSignal} />
    </MemoryRouter>,
  );
  return onOpenSignal;
}

describe("il segnale in cui il setup e scattato", () => {
  it("una riga convertita offre la via per raggiungerlo", () => {
    renderList([setup()]);

    expect(
      screen.getByRole("button", { name: /segnale in cui e scattato il setup su AMD/i }),
    ).toBeInTheDocument();
  });

  it("il click passa l'id di QUEL segnale", () => {
    const onOpenSignal = renderList([setup({ converted_alert_id: 4211 })]);

    return userEvent
      .click(screen.getByRole("button", { name: /segnale in cui e scattato/i }))
      .then(() => {
        expect(onOpenSignal).toHaveBeenCalledWith(4211);
      });
  });

  it("una riga scaduta non lo offre", () => {
    // Il controllo negativo che conta: un setup scaduto non e diventato nessun
    // segnale. Un pulsante li prometterebbe una pagina che non esiste, e
    // suggerirebbe che ogni attesa si sia risolta in qualcosa.
    renderList([setup({ status: "expired", lead_days: null, converted_alert_id: null })]);

    expect(screen.getByText("Scaduto")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /segnale in cui e scattato/i }),
    ).not.toBeInTheDocument();
  });

  it("una convertita senza l'id non lo offre", () => {
    // Le righe piu vecchie del campo. Il badge dice «Convertito» e il
    // collegamento non c'e: meglio di un pulsante che non porta da nessuna
    // parte.
    renderList([setup({ converted_alert_id: null })]);

    expect(screen.getByText("Convertito")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /segnale in cui e scattato/i }),
    ).not.toBeInTheDocument();
  });
});

describe("la struttura della riga", () => {
  it("il pulsante non e dentro l'ancora", () => {
    // ⚠️ La riga era un unico `<Link>` che avvolgeva tutto. Un controllo
    // interattivo annidato in un `<a>` e HTML non valido e si comporta male da
    // tastiera — l'invio attiva l'ancora, non il pulsante. Il difetto non si
    // vede a schermo e sopravvivrebbe a ogni test che guardi solo i ruoli.
    renderList([setup()]);

    const link = screen.getByRole("link", { name: /AMD/i });
    expect(link.querySelector("button")).toBeNull();
    expect(link.closest("li")?.querySelector("button")).not.toBeNull();
  });

  it("la riga porta ancora al titolo", () => {
    renderList([setup()]);

    expect(screen.getByRole("link", { name: /AMD/i })).toHaveAttribute(
      "href",
      "/stocks/AMD",
    );
  });
});
