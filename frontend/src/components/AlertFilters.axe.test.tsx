import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations, describeViolations } from "@/test/axe";

import { AlertFilters } from "./AlertFilters";

/* ─── Le sette tendine dei filtri Segnali hanno un NOME ───────────────────
 *
 * Il difetto era in produzione: `button-name` su sette bottoni, cioe' sette
 * controlli che uno screen reader annunciava identici e senza nome. Il testo
 * («ARCHIVIO», «TIPO SEGNALE», …) era a schermo e non era associato a nulla,
 * quindi il difetto era invisibile GUARDANDO — l'unico modo di vederlo era
 * ascoltare, o leggere un conteggio axe.
 *
 * ⚠️ Questo test verifica la correzione DOVE COSTA POCO. Il cricchetto e2e in
 * CI resta la misura che conta — li' ci sono gli stili veri e la pagina
 * intera — ma gira su push e risponde in minuti; qui la risposta e' immediata
 * e, soprattutto, non dipende dai dati del seme.
 *
 * ⚠️ E axe in jsdom NON prova che uno screen reader legga bene: `button-name`
 * si accontenta di `aria-label`, `aria-labelledby`, un `<label for>` o del
 * contenuto. Misurato in questa sessione: tutte e quattro le forme chiudono la
 * regola. La scelta di `aria-labelledby` con DUE id — etichetta e trigger —
 * non e' quindi imposta da axe ma dal fatto che il nome deve portare ANCHE il
 * valore corrente, e quel pezzo qui sotto e' asserito a mano.
 */

const VUOTI = {} as Parameters<typeof AlertFilters>[0]["value"];

function monta() {
  return render(<AlertFilters value={VUOTI} onChange={() => {}} />).container;
}

/** I sette grilletti delle tendine. */
function tendine(c: HTMLElement) {
  return Array.from(c.querySelectorAll('button[role="combobox"]'));
}

describe("AlertFilters — nomi accessibili delle tendine", () => {
  it("il pavimento: le sette tendine sono davvero rese", () => {
    /* Senza questo, «ogni tendina ha un nome» sarebbe vero di zero tendine —
     * la forma che CLAUDE.md registra quattro volte. La barra filtri e'
     * collassabile su telefono (`!open && "hidden"`), quindi un domani che
     * cambiasse il default di `open` renderebbe vacuo tutto il file. */
    expect(tendine(monta()).length).toBeGreaterThanOrEqual(7);
  });

  it("axe non riporta nessuna violazione", async () => {
    const c = monta();
    const v = await axeViolations(c);
    expect(v, describeViolations(v)).toEqual([]);
  });

  it("nessun grilletto e' senza nome", async () => {
    /* Ridondante con axe di proposito: axe riporta una REGOLA, questo nomina
     * il controllo. Se un domani si aggiungesse un ottavo filtro senza
     * etichetta, il messaggio dice quale. */
    const c = monta();
    const senzaNome = tendine(c).filter(
      (b) => !b.getAttribute("aria-label") && !b.getAttribute("aria-labelledby"),
    );
    expect(senzaNome.map((b) => b.outerHTML.slice(0, 80))).toEqual([]);
  });

  it("⚠️ il nome porta l'ETICHETTA e ANCHE il valore scelto", () => {
    /* Il punto che axe non puo' controllare, ed e' il motivo della forma con
     * due id. Con il solo id dell'etichetta il nome sarebbe «Archivio» e il
     * valore corrente non verrebbe annunciato da nessuna parte: per
     * `role="combobox"` il contenuto del bottone non e' il nome. */
    const c = monta();
    for (const b of tendine(c)) {
      const ids = (b.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean);
      expect(ids.length, `${b.outerHTML.slice(0, 60)} non punta a due nodi`).toBe(2);
      const testi = ids.map((id) => c.ownerDocument.getElementById(id)?.textContent?.trim() ?? "");
      expect(testi.every(Boolean), `un id di ${ids.join(" ")} non risolve`).toBe(true);
      // il secondo e' il trigger stesso, cioe' il valore corrente
      expect(ids[1]).toBe(b.id);
    }
  });

  it("⚠️ gli id generati sono UNICI anche con due barre montate", () => {
    /* `useId` esiste per questo, ma vale la pena fissarlo: con un id scritto a
     * mano due montaggi darebbero id doppi e `aria-labelledby` punterebbe
     * all'etichetta dell'ALTRA barra — un nome sbagliato, che e' peggio di un
     * nome assente perche' non lo segnala nessuna regola. */
    const { container } = render(
      <div>
        <AlertFilters value={VUOTI} onChange={() => {}} />
        <AlertFilters value={VUOTI} onChange={() => {}} />
      </div>,
    );
    const ids = tendine(container).flatMap((b) =>
      (b.getAttribute("aria-labelledby") ?? "").split(/\s+/).filter(Boolean),
    );
    expect(ids.length).toBeGreaterThanOrEqual(28);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
