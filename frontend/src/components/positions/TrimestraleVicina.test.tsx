import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { FINESTRA_TRIMESTRALE_GG, TrimestraleVicina } from "./TrimestraleVicina";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 29, 12)); // 29 settembre, mezzogiorno locale
});
afterEach(() => vi.useRealTimers());

it.each([
  ["2026-09-29", "Trimestrale oggi"],
  ["2026-09-30", "Trimestrale domani"],
  ["2026-10-02 00:00:00", "Trimestrale fra 3 giorni"],
])("%s → %s", (data, testo) => {
  render(<TrimestraleVicina data={data} />);
  expect(screen.getByText(testo)).toBeTruthy();
});

it("oltre la finestra, nel passato o sconosciuta non dice niente", () => {
  const oltre = new Date(2026, 8, 29 + FINESTRA_TRIMESTRALE_GG + 1);
  const iso = `${oltre.getFullYear()}-${String(oltre.getMonth() + 1).padStart(2, "0")}-${String(oltre.getDate()).padStart(2, "0")}`;
  for (const data of [iso, "2026-09-28", null, undefined, "boh"]) {
    const { container, unmount } = render(<TrimestraleVicina data={data} />);
    expect(container.textContent).toBe("");
    unmount();
  }
});

it("l'ultimo giorno della finestra si mostra ancora", () => {
  const bordo = new Date(2026, 8, 29 + FINESTRA_TRIMESTRALE_GG);
  const iso = `${bordo.getFullYear()}-${String(bordo.getMonth() + 1).padStart(2, "0")}-${String(bordo.getDate()).padStart(2, "0")}`;
  render(<TrimestraleVicina data={iso} />);
  expect(screen.getByText(`Trimestrale fra ${FINESTRA_TRIMESTRALE_GG} giorni`)).toBeTruthy();
});
