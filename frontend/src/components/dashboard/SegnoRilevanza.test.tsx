import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import type { AnalystAction } from "@/api/dashboard";

import { ActionRow, SegnoRilevanza } from "./AnalystActionsCard";

const AZIONE: AnalystAction = {
  ticker: "ADBE", name: "Adobe", date: "2026-09-28", firm: "Stifel", to_grade: "Buy",
  from_grade: "Hold", action: "up", current_price_target: null, from_news: false,
};

it.each([
  ["posizione", "ADBE, in posizione"],
  ["preferito", "ADBE, preferito"],
] as const)("%s: il nome della riga dice il titolo e poi il segno", (rilevanza, inizio) => {
  render(
    <MemoryRouter>
      <ul><ActionRow a={{ ...AZIONE, rilevanza }} /></ul>
    </MemoryRouter>,
  );
  // ⚠️ Prima il testo stava prima del ticker e il nome usciva «in posizioneADBE».
  expect(screen.getByRole("link").textContent?.includes(inizio)).toBe(true);
});

it("il segno sul logo e' solo visivo e non prende larghezza", () => {
  const { container } = render(<SegnoRilevanza rilevanza="posizione" />);
  const segno = container.firstElementChild;
  expect(segno?.getAttribute("aria-hidden")).toBe("true");
  expect(segno?.className).toContain("absolute");
});

it("un titolo non seguito non porta nessun segno", () => {
  for (const r of [null, undefined, "altro"]) {
    const { container, unmount } = render(<SegnoRilevanza rilevanza={r} />);
    expect(container.innerHTML).toBe("");
    unmount();
  }
  render(<MemoryRouter><ul><ActionRow a={AZIONE} /></ul></MemoryRouter>);
  expect(screen.getByRole("link").textContent).not.toMatch(/posizione|preferito/);
});
