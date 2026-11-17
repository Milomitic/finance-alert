import { describe, expect, it } from "vitest";

import { destinazioneDopoLogin } from "./dopoLogin";

describe("destinazioneDopoLogin", () => {
  it("torna alla pagina di partenza con la sua query e il frammento", () => {
    expect(destinazioneDopoLogin({ da: { pathname: "/alerts", search: "?vista=esiti", hash: "#x" } }))
      .toBe("/alerts?vista=esiti#x");
    expect(destinazioneDopoLogin({ da: { pathname: "/stocks/AAPL" } })).toBe("/stocks/AAPL");
  });

  it("senza una posizione valida porta alla dashboard", () => {
    expect(destinazioneDopoLogin(undefined)).toBe("/");
    expect(destinazioneDopoLogin(null)).toBe("/");
    expect(destinazioneDopoLogin({})).toBe("/");
    expect(destinazioneDopoLogin({ da: { pathname: 42 } })).toBe("/");
  });

  it("rifiuta indirizzi esterni e il login stesso", () => {
    expect(destinazioneDopoLogin({ da: { pathname: "//esempio.com/x" } })).toBe("/");
    expect(destinazioneDopoLogin({ da: { pathname: "https://esempio.com" } })).toBe("/");
    expect(destinazioneDopoLogin({ da: { pathname: "/login" } })).toBe("/");
  });

  it("ignora query e frammenti malformati", () => {
    expect(destinazioneDopoLogin({ da: { pathname: "/calendar", search: "x=1", hash: "y" } })).toBe("/calendar");
  });
});
