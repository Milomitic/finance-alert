import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Confluence } from "@/api/alerts";
import { axeViolations, describeViolations } from "@/test/axe";

import { AlertsInsightCard } from "./AlertsInsightCard";

/* ─── Un controllo alla volta nelle righe delle confluenze (FA-108) ───────
 *
 * Ogni riga era un `<div role="button">` che conteneva il link al titolo:
 * un controllo dentro un controllo. axe lo contava — `nested-interactive`, le
 * dieci violazioni di /alerts che non stavano nella tabella — e uno screen
 * reader ne annuncia uno solo dei due. Ora il pulsante e' il numero di
 * posizione, accanto al link e non intorno.
 *
 * ⚠️ Il pulsante non ha un gestore suo: il suo clic risale a quello della
 * riga. Il test sul «UNA volta» esiste per chi un domani glielo aggiungesse,
 * facendo partire il filtro due volte.
 */

function cl(i: number): Confluence {
  return {
    ticker: `T${i}`, name: `Titolo ${i}`, direction: i % 2 ? "bull" : "bear",
    strength: 70 - i, n_signals: 3, effective_n: 2, bull_strength: 60,
    bear_strength: 10, contested: i === 2, multi_horizon: i === 1,
    horizons: ["short", "medium"],
    components: [{
      alert_id: i, rule_kind: "signal:sr_flip", signal_name: "sr_flip",
      strength: 80, confidence: 80, tone: "bull", horizon: "short",
      signal_date: "2026-09-20",
    }],
  } as unknown as Confluence;
}

const DODICI = Array.from({ length: 12 }, (_, i) => cl(i + 1));

function monta(onTickerSelect: (t: string) => void = () => {}) {
  return render(
    <MemoryRouter>
      <AlertsInsightCard clusters={DODICI} onTickerSelect={onTickerSelect} />
    </MemoryRouter>,
  ).container;
}

describe("AlertsInsightCard — le righe delle confluenze", () => {
  it("il pavimento: dieci righe, ognuna col suo pulsante", () => {
    monta();
    expect(screen.getAllByRole("button", { name: /^Filtra i segnali su T\d+$/ })).toHaveLength(10);
  });

  it("axe non riporta nessuna violazione", async () => {
    const v = await axeViolations(monta());
    expect(v, describeViolations(v)).toEqual([]);
  });

  it("il pulsante filtra UNA volta, il link al titolo no", async () => {
    const onTickerSelect = vi.fn();
    monta(onTickerSelect);

    await userEvent.click(screen.getByRole("button", { name: "Filtra i segnali su T1" }));
    expect(onTickerSelect).toHaveBeenCalledTimes(1);
    expect(onTickerSelect).toHaveBeenCalledWith("T1");

    onTickerSelect.mockClear();
    await userEvent.click(screen.getByRole("link", { name: "T2" }));
    expect(onTickerSelect).not.toHaveBeenCalled();
  });

  it("da tastiera: Invio sul pulsante filtra", async () => {
    const onTickerSelect = vi.fn();
    monta(onTickerSelect);
    screen.getByRole("button", { name: "Filtra i segnali su T3" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(onTickerSelect).toHaveBeenCalledExactlyOnceWith("T3");
  });
});
