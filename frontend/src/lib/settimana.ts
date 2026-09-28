import type { CalendarEvent, EarningsEvent } from "@/api/types";

import { agendaDelGiorno, type VoceMacro } from "./oggiMercato";

/* ─── Che cosa arriva questa settimana (FA-088, idea dell'utente) ─────────
 *
 * Una risposta sola a «cosa arriva nei prossimi giorni»: i dati macro che
 * muovono i mercati e le trimestrali dei TUOI titoli — posizioni aperte e
 * preferiti. Tutto il catalogo sarebbe troppo (centinaia di trimestrali a
 * settimana in stagione); i titoli seguiti sono l'insieme che serve davvero,
 * e con i preferiti di FA-112 il nodo aperto della proposta si scioglie.
 *
 * I giorni sono quelli di NEW YORK, come i rilasci del calendario: la
 * regola e le sue ragioni stanno in `oggiMercato.ts`, qui si riusano.
 */

export type Rilevanza = "posizione" | "preferito";

export interface TrimestraleSeguita {
  evento: EarningsEvent;
  rilevanza: Rilevanza;
}

export interface GiornoSettimana {
  giorno: string;
  /** 0 = oggi. La distanza in giorni che la scheda scrive accanto. */
  distanza: number;
  /** Solo importanza alta: e' la settimana, non il calendario completo. */
  macro: VoceMacro[];
  trimestrali: TrimestraleSeguita[];
}

function piuGiorni(giorno: string, n: number): string {
  // Mezzogiorno UTC: lontano da entrambi i bordi del giorno, nessuna ora
  // legale puo' spostarlo in quello accanto.
  const t = new Date(`${giorno}T12:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

function fineSettimana(giorno: string): boolean {
  const d = new Date(`${giorno}T12:00:00Z`).getUTCDay();
  return d === 0 || d === 6;
}

/** I prossimi `giorni` giorni da `oggi` compreso. Un sabato o una domenica
 *  senza niente non occupano una colonna: non c'e' seduta, e una colonna vuota
 *  sarebbe spazio che non dice niente. Un giorno feriale vuoto resta, perche'
 *  «niente in arrivo» quel giorno e' un'informazione. */
export function settimana(
  eventi: readonly CalendarEvent[] | undefined,
  oggi: string,
  titoli: ReadonlyMap<string, Rilevanza>,
  giorni = 7,
): GiornoSettimana[] {
  const out: GiornoSettimana[] = [];
  for (let i = 0; i < giorni; i++) {
    const giorno = piuGiorni(oggi, i);
    const agenda = agendaDelGiorno(eventi, giorno);
    const macro = agenda.macro.filter((m) => m.importanza === "high");
    const trimestrali = [...agenda.primaDellApertura, ...agenda.dopoLaChiusura, ...agenda.senzaOrario]
      .filter((e) => titoli.has(e.ticker))
      .map((evento) => ({ evento, rilevanza: titoli.get(evento.ticker) as Rilevanza }))
      // Le posizioni prima dei preferiti, come nella lista dei segnali.
      .sort((a, b) => (a.rilevanza === b.rilevanza ? 0 : a.rilevanza === "posizione" ? -1 : 1));
    if (fineSettimana(giorno) && macro.length === 0 && trimestrali.length === 0) continue;
    out.push({ giorno, distanza: i, macro, trimestrali });
  }
  return out;
}

/** «Oggi», «Domani», o il giorno della settimana col numero: «mer 30». */
export function etichettaGiorno(giorno: string, distanza: number): string {
  if (distanza === 0) return "Oggi";
  if (distanza === 1) return "Domani";
  return new Date(`${giorno}T12:00:00Z`).toLocaleDateString("it-IT", {
    weekday: "short", day: "numeric", timeZone: "UTC",
  });
}
