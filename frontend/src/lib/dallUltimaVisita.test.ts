import { expect, it } from "vitest";

import { contati, etichettaDal } from "./dallUltimaVisita";

const ADESSO = new Date(2026, 8, 29, 18, 0);   // mar 29 settembre, 18:00 locali

it.each([
  [new Date(2026, 8, 29, 14, 10), "Dalle 14:10"],
  [new Date(2026, 8, 28, 22, 5), "Da ieri alle 22:05"],
  [new Date(2026, 8, 26, 9, 5), "Da sab 26 set alle 09:05"],
])("%s → %s", (dal, atteso) => {
  expect(etichettaDal(dal.toISOString(), ADESSO)).toBe(atteso);
});

it("il primo del mese: ieri e' l'ultimo del mese prima", () => {
  expect(etichettaDal(new Date(2026, 8, 30, 23, 0).toISOString(), new Date(2026, 9, 1, 8, 0)))
    .toBe("Da ieri alle 23:00");
});

it("singolare e plurale", () => {
  expect(contati(1, "segnale nuovo", "segnali nuovi")).toBe("1 segnale nuovo");
  expect(contati(3, "segnale nuovo", "segnali nuovi")).toBe("3 segnali nuovi");
});
