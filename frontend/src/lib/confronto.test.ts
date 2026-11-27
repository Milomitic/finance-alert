import { describe, expect, it } from "vitest";

import { conConfronto, PREDEFINITI, periodoDaUrl, simboliDaUrl } from "./confronto";

/* FA-187: lo stato del confronto nell'URL. */

describe("confronto nell'URL", () => {
  it("senza parametro i predefiniti; vuoto vuol dire nessuno", () => {
    expect(simboliDaUrl(new URLSearchParams(""))).toEqual(PREDEFINITI);
    expect(simboliDaUrl(new URLSearchParams("confronta="))).toEqual([]);
  });

  it("senza doppioni, maiuscoli, al massimo sei", () => {
    expect(simboliDaUrl(new URLSearchParams("confronta=aapl,^GSPC,AAPL"))).toEqual(["AAPL", "^GSPC"]);
    expect(simboliDaUrl(new URLSearchParams("confronta=a,b,c,d,e,f,g"))).toHaveLength(6);
  });

  it("un periodo sconosciuto torna a YTD, e gli altri parametri restano", () => {
    expect(periodoDaUrl(new URLSearchParams("periodo=99a"))).toBe("ytd");
    const n = conConfronto(new URLSearchParams("x=1"), ["GC=F"], "5a");
    expect(n.get("x")).toBe("1");
    expect(n.get("confronta")).toBe("GC=F");
    expect(n.get("periodo")).toBe("5a");
  });
});
