import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/dashboard", () => ({ dashboard: { summary: vi.fn(async () => ({ riepilogo: true })) } }));
vi.mock("@/api/market", () => ({ market: { summary: vi.fn(async () => ({ mercato: true })) } }));
vi.mock("@/api/etoro", () => ({ fetchEtoroVivo: vi.fn(async () => ({ conto: true })) }));
vi.mock("@/api/client", () => ({ api: vi.fn(async () => ({ paniere: true })) }));

const { persistiHome, precaricaHome, ripristinaHome } = await import("./avvioHome");

/* FA-179, fase C: l'ultima risposta buona torna subito, ma solo se e'
 * fresca e della stessa versione dell'app; e le richieste partono prima. */

const ORA = 1_700_000_000_000;

describe("la cache della home sul dispositivo", () => {
  it("salva una risposta riuscita e la ripristina se e' fresca e della stessa versione", async () => {
    const qc = new QueryClient();
    const smetti = persistiHome(qc, "v1");
    qc.setQueryData(["live-assets"], { assets: [1] });
    await new Promise((r) => setTimeout(r, 0));
    smetti();
    const salvato = JSON.parse(localStorage.getItem("home:live-assets") as string);
    expect(salvato).toMatchObject({ v: "v1", d: { assets: [1] } });

    const nuovo = new QueryClient();
    expect(ripristinaHome(nuovo, salvato.t + 60_000, "v1")).toBe(1);
    expect(nuovo.getQueryData(["live-assets"])).toEqual({ assets: [1] });
  });

  it("non ripristina un dato oltre l'eta' massima: meglio lo scheletro", () => {
    localStorage.setItem("home:live-assets", JSON.stringify({ v: "v1", t: ORA - 3 * 86_400_000, d: { vecchio: true } }));
    const qc = new QueryClient();
    expect(ripristinaHome(qc, ORA, "v1")).toBe(0);
    expect(qc.getQueryData(["live-assets"])).toBeUndefined();
  });

  it("non ripristina un dato salvato da un'altra versione dell'app", () => {
    localStorage.setItem("home:dashboard/summary", JSON.stringify({ v: "vecchia", t: ORA, d: { forma: "vecchia" } }));
    const qc = new QueryClient();
    expect(ripristinaHome(qc, ORA, "nuova")).toBe(0);
  });

  it("una voce rovinata non rompe niente", () => {
    localStorage.setItem("home:etoro/vivo", "{non json");
    expect(ripristinaHome(new QueryClient(), ORA, "v1")).toBe(0);
  });
});

describe("le richieste della home partono prima del montaggio", () => {
  it("sulla home precarica le quattro query critiche", async () => {
    const qc = new QueryClient();
    precaricaHome(qc, "/");
    await new Promise((r) => setTimeout(r, 0));
    expect(qc.getQueryData(["dashboard", "summary"])).toEqual({ riepilogo: true });
    expect(qc.getQueryData(["live-assets"])).toEqual({ paniere: true });
  });

  it("su un'altra pagina no", () => {
    const qc = new QueryClient();
    precaricaHome(qc, "/alerts");
    expect(qc.getQueryCache().getAll()).toHaveLength(0);
  });
});
