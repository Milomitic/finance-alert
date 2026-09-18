import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { AlertSetupOrigin } from "./AlertSetupOrigin";

/* Da quale setup e' nato un segnale (FA-066). Un fatto sulla storia del
 * titolo, mai un rinforzo: i setup non fanno previsioni. */

const base = {
  id: 7,
  ticker: "ACME",
  signal_date: "2026-08-10",
  triggered_at: "2026-08-11T10:00:00Z",
  snapshot: { tone: "bull" },
} as unknown as Alert;

function monta(alert: Alert, onNavigate?: () => void) {
  return render(
    <MemoryRouter>
      <AlertSetupOrigin alert={alert} onNavigate={onNavigate} />
    </MemoryRouter>,
  );
}

const origine = (over: Partial<NonNullable<Alert["setup_origin"]>> = {}): Alert => ({
  ...base,
  setup_origin: {
    setup_id: 3,
    detector: "trend_pullback",
    first_seen_at: "2026-08-04T09:00:00Z",
    lead_days: 6,
    ...over,
  },
});

describe("AlertSetupOrigin", () => {
  it("senza origine non rende niente", () => {
    const { container } = monta({ ...base, setup_origin: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("dice il setup, da quando si formava e con quanto anticipo", () => {
    monta(origine());
    const testo = document.body.textContent ?? "";
    expect(testo).toMatch(/Trend \+ Pullback/);
    expect(testo).toMatch(/4 ago/);
    expect(testo).toMatch(/6 giorni di anticipo/);
  });

  it("usa il singolare per un giorno", () => {
    monta(origine({ lead_days: 1 }));
    expect(document.body.textContent).toMatch(/1 giorno di anticipo/);
  });

  it("senza anticipo registrato non ne inventa uno", () => {
    monta(origine({ lead_days: null }));
    // Il pavimento: la frase c'e', manca solo l'anticipo.
    expect(document.body.textContent).toMatch(/Preceduto da un setup/);
    expect(document.body.textContent).not.toMatch(/anticipo/);
  });

  it("non si legge come una conferma", () => {
    monta(origine());
    expect(document.body.textContent).not.toMatch(/conferm|probabilit|affidabil|rafforz/i);
  });

  it("porta agli esiti dei setup di QUESTO titolo, e chiude chi lo ospita", async () => {
    const onNavigate = vi.fn();
    monta(origine(), onNavigate);
    const link = screen.getByRole("link", { name: /esiti dei setup di ACME/i });
    expect(link).toHaveAttribute("href", "/alerts?vista=esiti&esiti=setup&ticker=ACME");
    await userEvent.click(link);
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
