import type { TrimestraleMia } from "@/api/dashboard";

/* Formati della scheda «Sui tuoi titoli» (FA-149). */

const GIORNI = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];
const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

/** «oggi», «domani», «ven 21 nov», con l'ora di Roma quando c'e'.
 *  La data si legge dal TESTO: `new Date("2026-11-21")` e' mezzanotte UTC e
 *  a ovest di Greenwich diventerebbe il 20. */
export function quandoTrimestrale(t: TrimestraleMia): string {
  const [a, m, g] = t.data.split("-").map(Number);
  const giorno = t.giorni === 0 ? "oggi" : t.giorni === 1 ? "domani"
    : `${GIORNI[new Date(Date.UTC(a, m - 1, g)).getUTCDay()]} ${g} ${MESI[m - 1]}`;
  if (!t.ora_utc) return giorno;
  const ora = new Date(`${t.data}T${t.ora_utc}:00Z`).toLocaleTimeString("it-IT", {
    hour: "2-digit", minute: "2-digit", timeZone: "Europe/Rome",
  });
  return `${giorno} ${ora}`;
}

/** «12 min fa», «3 h fa», «2 g fa». */
export function tempoFa(iso: string, adesso: number): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const minuti = Math.max(0, Math.round((adesso - t) / 60_000));
  if (minuti < 60) return `${minuti} min fa`;
  const ore = Math.round(minuti / 60);
  return ore < 24 ? `${ore} h fa` : `${Math.round(ore / 24)} g fa`;
}
