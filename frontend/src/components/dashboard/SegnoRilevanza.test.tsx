import { render } from "@testing-library/react";
import { expect, it } from "vitest";

import { SegnoRilevanza } from "./AnalystActionsCard";

it.each([
  ["posizione", "in posizione"],
  ["preferito", "preferito"],
] as const)("%s: il segno ha un nome per gli assistivi", (rilevanza, nome) => {
  const { container } = render(<SegnoRilevanza rilevanza={rilevanza} />);
  expect(container.querySelector(".sr-only")?.textContent).toBe(nome);
  // Sull'angolo del logo: non prende larghezza nella riga.
  expect(container.firstElementChild?.className).toContain("absolute");
});

it("un titolo non seguito non porta nessun segno", () => {
  for (const r of [null, undefined, "altro"]) {
    const { container, unmount } = render(<SegnoRilevanza rilevanza={r} />);
    expect(container.innerHTML).toBe("");
    unmount();
  }
});
