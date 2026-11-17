import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Table, TableBody, TableCell, TableRow } from "./table";

/* Il contenitore di una tabella che scorre di lato si raggiunge da tastiera
 * (E-04), e solo quello: una tabella che sta nella sua scheda non deve
 * diventare una fermata in piu' del Tab.
 *
 * jsdom non fa layout, quindi larghezze e osservatore sono simulati: il
 * finto ResizeObserver chiama subito la callback, come fa il browser alla
 * prima osservazione. */

const originali = {
  ro: globalThis.ResizeObserver,
  sw: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth"),
  cw: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth"),
};

function simula(contenuto: number, contenitore: number) {
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", { configurable: true, get: () => contenuto });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => contenitore });
  globalThis.ResizeObserver = class {
    cb: ResizeObserverCallback;
    constructor(cb: ResizeObserverCallback) { this.cb = cb; }
    observe() { this.cb([], this as unknown as ResizeObserver); }
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

function monta() {
  return render(
    <Table aria-label="Posizioni">
      <TableBody><TableRow><TableCell>x</TableCell></TableRow></TableBody>
    </Table>,
  ).container.firstElementChild as HTMLElement;
}

afterEach(() => {
  globalThis.ResizeObserver = originali.ro;
  if (originali.sw) Object.defineProperty(HTMLElement.prototype, "scrollWidth", originali.sw);
  if (originali.cw) Object.defineProperty(HTMLElement.prototype, "clientWidth", originali.cw);
  vi.restoreAllMocks();
});

describe("Table — contenitore che scorre di lato", () => {
  it("se scorre e' una regione focalizzabile col nome della tabella", () => {
    simula(900, 375);
    const div = monta();
    expect(div.getAttribute("tabindex")).toBe("0");
    expect(div.getAttribute("role")).toBe("region");
    expect(div.getAttribute("aria-label")).toBe("Posizioni");
  });

  it("se sta nella sua scheda non aggiunge fermate al Tab", () => {
    simula(300, 375);
    const div = monta();
    expect(div.hasAttribute("tabindex")).toBe(false);
    expect(div.hasAttribute("role")).toBe(false);
  });
});
