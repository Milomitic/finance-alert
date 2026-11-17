import { describe, expect, it } from "vitest";

import { contoAtteso, ricordaConto } from "./contoAtteso";

describe("contoAtteso", () => {
  it("senza ricordo non riserva il posto", () => {
    expect(contoAtteso()).toBe(false);
  });

  it("ricorda se il conto c'era l'ultima volta", () => {
    ricordaConto(true);
    expect(contoAtteso()).toBe(true);
    ricordaConto(false);
    expect(contoAtteso()).toBe(false);
  });
});
