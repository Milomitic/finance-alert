import { describe, expect, it } from "vitest";

import type { InfraHealth } from "@/api/platformHealth";

import { peggiore, statoInfrastruttura } from "./statoInfrastruttura";

const sano = {
  available: true, targets_up: 12, targets_down: 0, alerts_firing: 0, firing_alerts: [], down_targets: [],
  restarts_24h: 0, memory_pct: 60, cert_days: 70,
} as unknown as InfraHealth;

describe("lo stato dell'infrastruttura nel banner (D-48)", () => {
  it("sana: nessun motivo", () => {
    expect(statoInfrastruttura(sano)).toEqual({ livello: "operational", motivi: [] });
  });

  it("allarmi accesi e certificato vicino: degradata, con i motivi", () => {
    const s = statoInfrastruttura({ ...sano, alerts_firing: 3, cert_days: 12 });
    expect(s?.livello).toBe("degraded");
    expect(s?.motivi).toEqual(["3 allarmi accesi", "certificato in scadenza fra 12 giorni"]);
  });

  it("un target giu' e' un'interruzione", () => {
    expect(statoInfrastruttura({ ...sano, targets_down: 1 })?.livello).toBe("outage");
  });

  it("Prometheus muto: non peggiora il banner ma lo dice", () => {
    const s = statoInfrastruttura({ available: false } as InfraHealth);
    expect(s?.livello).toBe("operational");
    expect(s?.motivi[0]).toMatch(/sconosciuto/);
  });

  it("il banner prende il peggiore", () => {
    expect(peggiore("operational", "degraded")).toBe("degraded");
    expect(peggiore("outage", "degraded")).toBe("outage");
    expect(peggiore("degraded", undefined)).toBe("degraded");
  });
});
