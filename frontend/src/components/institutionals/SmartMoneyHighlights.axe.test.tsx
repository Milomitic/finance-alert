import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { AggregateStats } from "@/api/types";
import { axeViolations, describeViolations } from "@/test/axe";

import { SmartMoneyHighlights } from "./SmartMoneyHighlights";

/* ─── Il difetto che il cancello ha trovato, e che qui costa due secondi ───
 *
 * La prima versione di questa fascia metteva `role="region"` sull'`<ul>` che
 * scorre, per dargli un nome e il fuoco. Sembra ragionevole e rompe due cose
 * insieme: `region` SOSTITUISCE il ruolo `list`, quindi l'elemento porta un
 * ruolo che la specifica non ammette su `<ul>` (`aria-allowed-role`) e ogni
 * `<li>` resta orfano del genitore che gli serve (`listitem`).
 *
 * Il gate UI in CI l'ha misurato — `aria-allowed-role: 0 -> 2`,
 * `listitem: 0 -> 30` — e ha fatto il suo mestiere: niente e' stato
 * rilasciato. Ma risponde in minuti e gira solo su push. Queste due regole
 * sono STRUTTURALI, cioe' esattamente cio' che axe vede anche senza stili:
 * qui la stessa risposta arriva subito.
 *
 * ⚠️ Resta un pavimento, non una certificazione: in jsdom non c'e' foglio di
 * stile, quindi contrasto, bersagli tattili e visibilita' del fuoco non sono
 * misurabili. Quelli restano al cancello con gli stili veri.
 */

const AGG: AggregateStats = {
  most_picked: [],
  recent_buys: [{
    ticker: "NVDA", company_name: "Nvidia", institutional_slug: "berkshire",
    institutional_name: "Berkshire Hathaway", period_end_date: "2026-06-30",
    action: "new", qoq_change_pct: 12.5, portfolio_pct: 4.2, value_usd: 1.2e9, stock_id: 1,
  }],
  recent_sells: [{
    ticker: "TSLA", company_name: "Tesla", institutional_slug: "bridgewater",
    institutional_name: "Bridgewater", period_end_date: "2026-06-30",
    action: "sold_out", qoq_change_pct: -100, portfolio_pct: null, value_usd: 8e8, stock_id: 2,
  }],
  sector_tilt: { Tech: 100 },
};

function monta() {
  return render(
    <MemoryRouter>
      <SmartMoneyHighlights agg={AGG} fondi={[]} />
    </MemoryRouter>,
  ).container;
}

describe("SmartMoneyHighlights — accessibilita' strutturale", () => {
  it("non porta violazioni che axe possa vedere senza stili", async () => {
    const v = await axeViolations(monta());
    expect(v, describeViolations(v)).toHaveLength(0);
  });

  it("le liste restano liste, e il ruolo che scorre sta sul contenitore", () => {
    // La forma precisa della correzione: il `region` avvolge la lista invece
    // di sostituirne il ruolo. Asserirla qui evita che qualcuno la
    // «semplifichi» rimettendo l'attributo sull'`<ul>`.
    const c = monta();
    for (const ul of Array.from(c.querySelectorAll("ul"))) {
      expect(ul.getAttribute("role")).toBeNull();
    }
    const regioni = Array.from(c.querySelectorAll('[role="region"]'));
    expect(regioni).toHaveLength(2);
    for (const r of regioni) {
      expect(r.tagName).toBe("DIV");
      expect(r).toHaveAttribute("tabindex", "0");
      expect(r.getAttribute("aria-label")).toBeTruthy();
      expect(r.querySelector("ul")).not.toBeNull();
    }
  });

  it("⚠️ controllo negativo: lo scanner SA vedere questo difetto", async () => {
    /* Senza, il verde qui sopra sarebbe indistinguibile da uno scanner
     * configurato male. Si ricostruisce la forma sbagliata e si pretende che
     * entrambe le regole scattino. */
    const { container } = render(
      <div>
        <ul role="region" aria-label="sbagliata" tabIndex={0}>
          <li>una riga</li>
        </ul>
      </div>,
    );
    const v = await axeViolations(container);
    const regole = v.map((x) => x.id);
    expect(regole).toContain("aria-allowed-role");
    expect(regole).toContain("listitem");
  });
});
