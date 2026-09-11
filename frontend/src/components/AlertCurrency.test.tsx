import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlaybookView } from "./PlaybookView";
import type { Playbook } from "@/lib/tradePlaybook";

/* ─── Il prezzo di un segnale, nella valuta del titolo ────────────────────
 *
 * FA-045. Trovata dalla verifica a schermo: il dialogo di un segnale su
 * ARGX.BR — titolo belga che la pagina Posizioni mostra a `EUR 850.60` —
 * rendeva sei cifre in dollari.
 *
 * ⚠️ Misurato in produzione: 2.669 segnali su 8.905, il **30,0%**, sono su
 * titoli non quotati in dollari. Stessa magnitudine di FA-025, che era P1.
 */

function playbook(over: Partial<Playbook> = {}): Playbook {
  return {
    side: "long",
    action: "Long",
    horizon: "Medio",
    entry: 850.6,
    stop: 780.2,
    stopPct: 8.3,
    stopCapped: false,
    targets: [{ label: "T1", price: 920.5, rr: 1.5 }],
    duration: "2-4 settimane",
    riskBudgetPct: 1,
    positionPct: 12,
    leverage: 1,
    leverageNote: "",
    ...over,
  };
}

describe("PlaybookView", () => {
  it("usa il simbolo della valuta ricevuta, non il dollaro", () => {
    render(<PlaybookView playbook={playbook()} currency="EUR" />);
    const t = document.body.innerText ?? document.body.textContent ?? "";
    expect(t).toContain("€850.60");
    expect(t).not.toMatch(/\$850/);
  });

  it("⚠️ una valuta sconosciuta lascia il numero NUDO, non in dollari", () => {
    // La regola di `formatMoney`: prendere in prestito il dollaro perche il
    // campo e vuoto e un'ipotesi presentata come un fatto.
    render(<PlaybookView playbook={playbook()} currency={null} />);
    const t = document.body.innerText ?? document.body.textContent ?? "";
    expect(t).toContain("850.60");
    expect(t).not.toContain("$850.60");
  });

  it("vale per ogni cella della geometria, non solo per l'ingresso", () => {
    render(<PlaybookView playbook={playbook()} currency="GBp" />);
    const t = document.body.innerText ?? document.body.textContent ?? "";
    // `GBp` e un'etichetta in pence su un valore gia in sterline: la
    // normalizzazione la fa `displayCurrency`, quindi qui si vede la sterlina.
    for (const atteso of ["£850.60", "£780.20", "£920.50"]) {
      expect(t).toContain(atteso);
    }
  });
});

describe("nessuna superficie dei segnali caccia il dollaro nel template", () => {
  /* Controllo sulla SORGENTE: un test di resa su un titolo americano
   * passerebbe comunque, perche li il dollaro e giusto. */
  /* ⚠️ DUE forme, non una. Nel piano il dollaro sta dentro un template
   * (`` `$${...}` ``), nel dialogo e TESTO JSX seguito da `{espressione}`. Una
   * regex sola le manca a turno.
   *
   * ⚠️ E deve essere PRECISA. Il primo tentativo cercava i nomi dei campi
   * dentro una qualunque interpolazione, e marcava `${p.stopPct.toFixed(1)}`
   * — riga corretta — solo perche `p.stop` ne e il prefisso. Un controllo
   * sulla sorgente che grida sul codice giusto viene cancellato dal primo che
   * lo incontra, ed e peggio di non averlo. */
  const DOLLARO_IN_TEMPLATE = /\$\$\{/;
  const DOLLARO_IN_JSX = /\$\{(alert\.trigger_price|invLevel|a\.trigger_price)/;

  it("il dialogo del segnale delega", async () => {
    const src = (await import("./AlertDetailDialog.tsx?raw")).default as string;
    expect(src).not.toMatch(DOLLARO_IN_TEMPLATE);
    expect(src).not.toMatch(DOLLARO_IN_JSX);
  });

  it("il piano operativo delega", async () => {
    const src = (await import("./PlaybookView.tsx?raw")).default as string;
    expect(src).not.toMatch(DOLLARO_IN_TEMPLATE);
    expect(src).not.toMatch(DOLLARO_IN_JSX);
  });

  it("il feed dei segnali recenti delega", async () => {
    const src = (await import("./dashboard/RecentAlertsFeed.tsx?raw")).default as string;
    expect(src).not.toMatch(DOLLARO_IN_TEMPLATE);
    expect(src).not.toMatch(DOLLARO_IN_JSX);
  });
});
