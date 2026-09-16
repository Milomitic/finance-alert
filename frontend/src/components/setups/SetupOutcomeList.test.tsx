import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Setup } from "@/hooks/useSetups";

import { SetupOutcomeList } from "./SetupOutcomeList";

/* Un setup convertito porta al segnale in cui è scattato.
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
      screen.getByRole("button", { name: /segnale in cui è scattato il setup su AMD/i }),
    ).toBeInTheDocument();
  });

  it("il click passa l'id di QUEL segnale", () => {
    const onOpenSignal = renderList([setup({ converted_alert_id: 4211 })]);

    return userEvent
      .click(screen.getByRole("button", { name: /segnale in cui è scattato/i }))
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
      screen.queryByRole("button", { name: /segnale in cui è scattato/i }),
    ).not.toBeInTheDocument();
  });

  it("una convertita senza l'id non lo offre", () => {
    // Le righe piu vecchie del campo. Il badge dice «Convertito» e il
    // collegamento non c'e: meglio di un pulsante che non porta da nessuna
    // parte.
    renderList([setup({ converted_alert_id: null })]);

    expect(screen.getByText("Convertito")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /segnale in cui è scattato/i }),
    ).not.toBeInTheDocument();
  });
});

describe("il focus durante il caricamento del segnale", () => {
  it("il pulsante resta focalizzabile e non riapre mentre carica", async () => {
    // Col segnale in caricamento il pulsante era `disabled`: il dialogo si apre
    // in quel momento, e alla chiusura il focus non puo' tornare su un elemento
    // disabilitato — finiva sul BODY. Trovato nel collaudo in browser.
    const onOpenSignal = vi.fn();
    render(
      <MemoryRouter>
        <SetupOutcomeList
          setups={[setup({ converted_alert_id: 4211 })]}
          onOpenSignal={onOpenSignal}
          pendingAlertId={4211}
        />
      </MemoryRouter>,
    );
    const b = screen.getByRole("button", { name: /segnale in cui è scattato/i });
    expect(b).not.toBeDisabled();
    expect(b).toHaveAttribute("aria-disabled", "true");
    b.focus();
    expect(b).toHaveFocus();
    await userEvent.click(b);
    expect(onOpenSignal).not.toHaveBeenCalled();
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

/* ─── Perché un episodio si è chiuso, e i 322 che non lo dicono ────────────
 *
 * FA-061. La distinzione era già calcolata dentro `expire_stale_setups` — le
 * due ragioni finivano contate separatamente nel log — e poi scritte entrambe
 * come `expired`, quindi a posteriori non si poteva più sapere quale.
 *
 * ⚠️ Il caso DOMINANTE è «non lo so». Misurato in produzione il 2026-09-14:
 * 322 setup scaduti senza ragione registrata contro UNO con la ragione, perché
 * la colonna è nata quel giorno. Il progetto parte da lì.
 */
describe("la ragione della chiusura", () => {
  it("⚠️ un episodio chiuso prima che la colonna esistesse DICE di non saperlo", () => {
    // Tacere li farebbe sembrare tutti dello stesso tipo, che è precisamente
    // ciò che non si sa. È la stessa distinzione fra «—» e «0» che questo
    // progetto applica ai numeri.
    renderList([setup({ status: "expired", closed_reason: null, converted_alert_id: null })]);
    expect(document.body.textContent).toContain("ragione non registrata");
  });

  it("nomina le due scadenze, che dicono cose diverse sul detector", () => {
    renderList([
      setup({ id: 1, status: "expired", closed_reason: "stale", converted_alert_id: null }),
      setup({ id: 2, ticker: "NVDA", status: "expired", closed_reason: "aged", converted_alert_id: null }),
    ]);
    const t = document.body.textContent ?? "";
    // Decadimento: il mercato è andato oltre.
    expect(t).toContain("le condizioni si sono sfaldate");
    // Tetto d'attesa: un cancello che descrive uno stato invece di dare un
    // anticipo — dice qualcosa sul DETECTOR, non sul mercato.
    expect(t).toContain("tetto d'attesa");
  });

  it("⚠️ un ritirato è marcato FUORI dal tasso, perché il backend lo esclude", () => {
    // Senza questa marca chi conta le righe a occhio ottiene un rapporto
    // diverso da quello che l'app riporta, e non ha modo di sapere perché.
    renderList([setup({ status: "expired", closed_reason: "decayed", converted_alert_id: null })]);
    const t = document.body.textContent ?? "";
    expect(t).toContain("Ritirato");
    expect(t).toContain("fuori dal tasso");
    expect(t).not.toContain("Scaduto");
  });

  it("un convertito non porta nessuna ragione di chiusura", () => {
    // Controllo negativo: `closed_reason` è nullo per costruzione sulle
    // convertite, e senza questo l'asserzione sopra sarebbe vera anche di un
    // componente che stampa la ragione ovunque.
    renderList([setup()]);
    const t = document.body.textContent ?? "";
    expect(t).toContain("Convertito");
    expect(t).not.toContain("ragione non registrata");
    expect(t).not.toContain("fuori dal tasso");
  });
});

/* ─── La quarta ragione: la serie del titolo si è fermata ──────────────────
 *
 * FA-071, e chiude il buco che FA-061 aveva lasciato dichiarato: quella voce
 * elencava QUATTRO ragioni di chiusura e ne furono costruite tre, perché
 * «dati insufficienti» non aveva popolazione. La popolazione è comparsa
 * misurando i titoli morti: 9 setup aperti su 12 titoli, 4 in shortlist.
 */
describe("un setup appeso a una serie ferma", () => {
  it("dice che la serie si è fermata, non che le condizioni sono decadute", () => {
    // ⚠️ La differenza non è cosmetica: «le condizioni si sono sfaldate»
    // sarebbe un'affermazione FALSA sul mercato, mentre il fatto è che il
    // titolo ha smesso di quotare.
    renderList([setup({ status: "expired", closed_reason: "no_data", converted_alert_id: null })]);
    const t = document.body.textContent ?? "";
    expect(t).toContain("la serie prezzi del titolo si è fermata");
    expect(t).not.toContain("le condizioni si sono sfaldate");
  });

  it("⚠️ conta nel tasso di conversione, a differenza di un ritirato", () => {
    // L'occasione di convertire c'era davvero: gliel'ha tolta il titolo. Un
    // ritirato invece non l'ha mai avuta, ed è per questo che il backend lo
    // esclude dal denominatore.
    renderList([setup({ status: "expired", closed_reason: "no_data", converted_alert_id: null })]);
    const t = document.body.textContent ?? "";
    expect(t).toContain("Scaduto");
    expect(t).not.toContain("fuori dal tasso");
  });
});
