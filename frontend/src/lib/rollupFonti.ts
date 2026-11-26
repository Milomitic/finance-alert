/* Lo stato di un cluster di fonti dati nella Diagnostica (D-54). */

export type SaluteFonte = "healthy" | "degraded" | "failing" | "unavailable" | "idle" | "stale";

export function normHealth(h: string): SaluteFonte {
  return h === "healthy" || h === "degraded" || h === "failing" ||
    h === "unavailable" || h === "stale"
    ? h
    : "idle";
}

/** ⚠️ Prima bastava UNA fonte sana per dire «Operativa»: un cluster Macro
 *  con FRED fermo e il consenso attivo era verde, cioe' la forma esatta del
 *  guasto di FRED fermo 60 giorni. La ridondanza tiene in piedi l'app, ma per
 *  chi diagnostica il degrado di una fonte e' proprio l'informazione: una
 *  fonte in errore o degradata rende il cluster «Degradata», anche con le
 *  altre sane. */
export function rollup(sources: readonly { health: string }[]): SaluteFonte {
  if (sources.length === 0) return "idle";
  const s = sources.map((x) => normHealth(x.health));
  if (s.every((h) => h === "failing")) return "failing";
  if (s.some((h) => h === "failing" || h === "degraded")) return "degraded";
  if (s.some((h) => h === "healthy")) return "healthy";
  // Nessuna sana ne' in errore: una fonte stantia (successi fermi oltre la
  // cadenza attesa) marca il cluster come stantio.
  if (s.some((h) => h === "stale")) return "stale";
  // Solo unavailable/idle: se almeno una fonte e' plan-gated, il cluster e'
  // «non disponibile» (slate), non un incidente.
  if (s.some((h) => h === "unavailable")) return "unavailable";
  return "idle";
}
