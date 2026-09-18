import type { CalendarEvent, EarningsEvent, MacroEvent, MacroImportance } from "@/api/types";

import { etWallClock } from "./usSession";

/* ─── L'agenda della seduta che sta per cominciare ────────────────────────── *
 *
 * Alle 04:34 di New York la domanda non e' solo «dove sono i futures»: e' «che
 * cosa esce oggi». Un dato macro alle 08:30 ET muove l'apertura piu' di
 * qualunque movimento pre-market, e una trimestrale prima della campanella
 * spiega il titolo che sta gia' correndo.
 *
 * ⚠️ Gli orari di rilascio arrivano in UTC (`release_time`, "12:30" = 08:30 a
 * New York) e il giorno di riferimento e' quello di NEW YORK, non quello di
 * chi guarda: alle 01:00 italiane a Wall Street e' ancora ieri sera. Le due
 * conversioni stanno qui, pure e verificabili, invece che dentro il JSX.
 */

export interface VoceMacro {
  /** "08:30" nell'ora di New York, o null quando il rilascio non ha un orario
   *  pubblicato (parecchie serie FRED non ce l'hanno). */
  oraET: string | null;
  etichetta: string;
  importanza: MacroImportance;
  regione: string;
  seriesId: number | null;
}

export interface AgendaOggi {
  macro: VoceMacro[];
  /** Trimestrali attese PRIMA della campanella: sono quelle che spiegano un
   *  titolo che si muove nel pre-market. */
  primaDellApertura: EarningsEvent[];
  /** Dopo la chiusura: non muovono questa seduta, ma la sera si'. */
  dopoLaChiusura: EarningsEvent[];
  /** Senza indicazione di orario. Restano contate a parte invece di essere
   *  attribuite d'ufficio al mattino: `earnings_when` e' gia' un'inferenza. */
  senzaOrario: EarningsEvent[];
}

const ORDINE_IMPORTANZA: Record<MacroImportance, number> = { high: 0, medium: 1, low: 2 };

/** L'ora di New York di un rilascio, da giorno + orario UTC. Null quando
 *  l'orario manca o non e' interpretabile: un'ora inventata su un calendario
 *  e' peggio di nessuna ora. */
export function oraNewYork(giorno: string, oraUtc: string | null | undefined): string | null {
  if (!oraUtc || !/^\d{2}:\d{2}$/.test(oraUtc)) return null;
  const t = new Date(`${giorno}T${oraUtc}:00Z`);
  if (Number.isNaN(t.getTime())) return null;
  // Passa dal calendario IANA, quindi l'ora legale e' gia' dentro: 12:30 UTC
  // vale 08:30 a settembre e 07:30 a gennaio.
  return etWallClock(t).label;
}

/**
 * Filtra gli eventi del calendario sul GIORNO DI NEW YORK e li ordina come si
 * leggono: i macro per orario (quelli senza orario in fondo, poi per
 * importanza), le trimestrali divise per momento della seduta.
 */
export function agendaDelGiorno(
  eventi: readonly CalendarEvent[] | undefined,
  giornoET: string,
): AgendaOggi {
  const diOggi = (eventi ?? []).filter((e) => e.date === giornoET);

  const macro: VoceMacro[] = diOggi
    .filter((e): e is MacroEvent => e.kind === "macro")
    .map((e) => ({
      oraET: oraNewYork(e.date, e.release_time),
      etichetta: e.label,
      importanza: e.importance,
      regione: e.region,
      seriesId: e.series_id ?? null,
    }))
    .sort((a, b) => {
      // Senza orario in fondo: la lista si legge come una scaletta, e una voce
      // senza ora in mezzo alle altre romperebbe la sequenza.
      if (a.oraET == null && b.oraET == null) {
        return ORDINE_IMPORTANZA[a.importanza] - ORDINE_IMPORTANZA[b.importanza];
      }
      if (a.oraET == null) return 1;
      if (b.oraET == null) return -1;
      return a.oraET.localeCompare(b.oraET);
    });

  const trimestrali = diOggi.filter((e): e is EarningsEvent => e.kind === "earnings");
  /* Le piu' grosse per prime: in una riga ci stanno pochi nomi, e «chi conta»
   * qui e' la capitalizzazione, non l'ordine alfabetico. Chi non ha una
   * capitalizzazione nota va in fondo invece che in testa con uno zero. */
  const perPeso = (a: EarningsEvent, b: EarningsEvent) =>
    (b.market_cap ?? -1) - (a.market_cap ?? -1);

  return {
    macro,
    primaDellApertura: trimestrali.filter((e) => e.earnings_when === "pre").sort(perPeso),
    dopoLaChiusura: trimestrali.filter((e) => e.earnings_when === "after").sort(perPeso),
    senzaOrario: trimestrali.filter((e) => e.earnings_when == null).sort(perPeso),
  };
}

/** Vero quando non c'e' NIENTE da dire: chi rende a schermo omette la riga
 *  invece di scrivere «nessun evento», che occuperebbe una riga per dire zero. */
export function agendaVuota(a: AgendaOggi): boolean {
  return (
    a.macro.length === 0 &&
    a.primaDellApertura.length === 0 &&
    a.dopoLaChiusura.length === 0 &&
    a.senzaOrario.length === 0
  );
}
