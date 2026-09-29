import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { FilterStrip } from "./FilterStrip";

function monta(props: Partial<Parameters<typeof FilterStrip>[0]> = {}) {
  const onSoloMieiChange = vi.fn();
  render(
    <FilterStrip
      kind="all" onKindChange={() => {}} importance={new Set(["high", "medium", "low"])}
      onImportanceToggle={() => {}} importanceDisabled={false}
      soloMiei={false} onSoloMieiChange={onSoloMieiChange} soloMieiDisabled={false}
      {...props}
    />,
  );
  return { onSoloMieiChange, bottone: screen.getByRole("button", { name: /I miei titoli/ }) };
}

it("l'interruttore dei tuoi titoli dice il suo stato e lo cambia", () => {
  const { onSoloMieiChange, bottone } = monta();
  expect(bottone).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(bottone);
  expect(onSoloMieiChange).toHaveBeenCalledWith(true);
});

it("con «Solo macro» non c'e' niente da restringere, e si spegne", () => {
  const { bottone } = monta({ kind: "macro", soloMieiDisabled: true });
  expect(bottone).toBeDisabled();
});
