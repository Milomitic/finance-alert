import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";

import { messaggioErrore } from "./errori";

describe("messaggioErrore", () => {
  it("dice quale guasto e', in italiano, senza il testo del server", () => {
    expect(messaggioErrore(new ApiError(401, "User not found"))).toMatch(/sessione/);
    expect(messaggioErrore(new ApiError(429, "Too Many Requests"))).toMatch(/Troppe richieste/);
    expect(messaggioErrore(new ApiError(503, "upstream"))).toMatch(/fonte/);
    expect(messaggioErrore(new ApiError(500, "boom"))).toMatch(/server/);
    expect(messaggioErrore(new ApiError(500, "boom"))).not.toContain("boom");
  });

  it("riconosce la rete assente", () => {
    expect(messaggioErrore(new TypeError("Failed to fetch"))).toMatch(/Connessione/);
  });

  it("senza niente di utile da aggiungere tace", () => {
    expect(messaggioErrore(undefined)).toBeNull();
    expect(messaggioErrore(new Error("qualcosa"))).toBeNull();
  });
});
