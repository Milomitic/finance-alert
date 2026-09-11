import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import NotFoundPage from "./NotFoundPage";

/* ─── Il 404 deve dirsi anche nella linguetta ─────────────────────────────
 *
 * FA-013. Trovato dalla verifica a schermo: la pagina rende «Errore 404 ·
 * Pagina non trovata» e la scheda del browser continua a dire «Finance-Alert».
 *
 * ⚠️ Il motivo e strutturale, non una dimenticanza. Il titolo per rotta lo
 * imposta `Layout`, leggendolo da `NAV` — e il 404 e montato FUORI da Layout,
 * come fratello di `path="*"`. Quindi per quella pagina l'effetto non gira
 * affatto, e il valore che resta e quello del documento statico.
 *
 * Che sia fuori da Layout e anche cio che rende la correzione sicura: gli
 * effetti dei figli girano PRIMA di quelli del genitore, quindi una pagina
 * dentro Layout che si intitolasse da sola verrebbe sovrascritta subito dopo.
 * Qui nessuno la sovrascrive.
 */

const TITOLO_ORIGINALE = document.title;
afterEach(() => {
  document.title = TITOLO_ORIGINALE;
});

describe("NotFoundPage", () => {
  it("intitola la scheda come le altre rotte", () => {
    render(<MemoryRouter><NotFoundPage /></MemoryRouter>);
    expect(document.title).toBe("Pagina non trovata · Finance-Alert");
  });

  it("⚠️ non e generico: una scheda che dice solo «Finance-Alert» non distingue un 404", () => {
    // Con dieci schede aperte, il titolo e l'unica cosa che si legge.
    render(<MemoryRouter><NotFoundPage /></MemoryRouter>);
    expect(document.title).not.toBe("Finance-Alert");
  });

  it("lascia due uscite: indietro e dashboard", () => {
    render(<MemoryRouter><NotFoundPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /indietro/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeTruthy();
  });
});
