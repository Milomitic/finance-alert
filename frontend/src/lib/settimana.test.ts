import { describe, expect, it } from "vitest";

import { etichettaGiorno } from "./settimana";

describe("le etichette", () => {
  it("oggi, domani, poi il giorno col numero", () => {
    expect(etichettaGiorno("2026-09-28", 0)).toBe("Oggi");
    expect(etichettaGiorno("2026-09-29", 1)).toBe("Domani");
    expect(etichettaGiorno("2026-09-30", 2)).toBe("mer 30");
  });
});
