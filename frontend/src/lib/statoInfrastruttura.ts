import type { InfraHealth } from "@/api/platformHealth";

/* ─── L'infrastruttura nel banner della Diagnostica (D-48) ─────────────────
 *
 * Il banner leggeva solo il riepilogo del server (fonti, job, scansioni,
 * breaker): un nodo con tre allarmi di Prometheus accesi e il certificato a
 * 12 giorni lasciava «Tutti i sistemi operativi». Qui l'infrastruttura si
 * riduce a un livello e a dei motivi, e il banner prende il PEGGIORE fra le
 * due letture. Le soglie sono quelle della scheda Infrastruttura. */

export type Livello = "operational" | "degraded" | "outage";

export interface StatoInfrastruttura {
  livello: Livello;
  motivi: string[];
}

export function statoInfrastruttura(data: InfraHealth | null | undefined): StatoInfrastruttura | null {
  if (!data) return null;
  if (!data.available) {
    // Non e' un guasto dell'app e non e' «tutto a posto»: lo si dice.
    return { livello: "operational", motivi: ["Stato dell'infrastruttura sconosciuto: Prometheus non risponde"] };
  }
  const motivi: string[] = [];
  let livello: Livello = "operational";
  const giu = data.targets_down ?? 0;
  const allarmi = data.alerts_firing ?? 0;
  if (giu > 0) {
    livello = "outage";
    motivi.push(`${giu} target di Prometheus giù`);
  }
  if (allarmi > 0) {
    if (livello === "operational") livello = "degraded";
    motivi.push(`${allarmi} allarm${allarmi === 1 ? "e acceso" : "i accesi"}`);
  }
  if ((data.restarts_24h ?? 0) >= 3) {
    if (livello === "operational") livello = "degraded";
    motivi.push(`${data.restarts_24h} riavvii nelle ultime 24 ore`);
  }
  if (data.memory_pct != null && data.memory_pct >= 90) {
    if (livello === "operational") livello = "degraded";
    motivi.push(`memoria del nodo al ${Math.round(data.memory_pct)}%`);
  }
  if (data.cert_days != null && data.cert_days < 20) {
    if (livello === "operational") livello = "degraded";
    motivi.push(`certificato in scadenza fra ${Math.round(data.cert_days)} giorni`);
  }
  return { livello, motivi };
}

const ORDINE: Record<Livello, number> = { operational: 0, degraded: 1, outage: 2 };

export function peggiore(a: Livello, b: Livello | undefined): Livello {
  return b && ORDINE[b] > ORDINE[a] ? b : a;
}
