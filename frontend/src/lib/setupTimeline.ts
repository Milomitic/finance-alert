import type { Setup } from "@/hooks/useSetups";

/* ─── La storia di un setup chiuso, in passi che dicono cosa si sa ──────────
 *
 * apertura → evento di conversione → esito. Ogni passo porta il FATTO o dice
 * che il fatto non c'e': dal 2026-09-16 il setup registra la barra, il prezzo e
 * l'esito dell'evento che l'ha convertito, ma le conversioni precedenti no, e
 * 85 setup rimasti attivi per un difetto sono stati riconciliati senza quella
 * barra. Una riga muta li farebbe sembrare tutti uguali.
 *
 * ⚠️ L'esito e' quello dell'EVENTO, non del segnale che si apre col pulsante:
 * la scansione continua ad aggiornare il segnale finche' la condizione tiene,
 * quindi la data che il segnale mostra oggi puo' essere successiva.
 */

export type EsitoTono = "ok" | "bad" | null;

export interface PassoEvento {
  /** «evento 15 set», oppure la ragione per cui la barra non c'e'. */
  evento: string;
  /** L'esito dell'evento, o perche' non c'e' ancora / non ci sara'. */
  esito: string;
  /** Colore dell'esito SINGOLO: e' un fatto su questo evento, non una
   *  statistica, quindi il verso si puo' mostrare. */
  tono: EsitoTono;
}

function giorno(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(d.getTime())
    ? null
    : d.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

function segno(pct: number): string {
  // Stessa forma delle tessere sopra la lista (`toFixed`): due separatori
  // decimali sulla stessa pagina si leggono come due unita' diverse.
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

/** Evento ed esito di un setup CONVERTITO; null per ogni altro stato. */
export function conversionStep(setup: Setup): PassoEvento | null {
  if (setup.status !== "converted") return null;

  const quando = giorno(setup.converted_signal_date);
  const evento =
    quando !== null
      ? `evento ${quando}` +
        (setup.bar_lead_days != null ? ` (${setup.bar_lead_days}g dopo l'apertura)` : "")
      : setup.conversion_source === "reconciled"
        ? "barra dell'evento non registrata (riconciliato)"
        : "barra dell'evento non registrata (storico)";

  if (setup.outcome_signal_date) {
    const h = setup.outcome_horizon_days;
    const orizzonte = h ? ` a ${h}g` : "";
    if (setup.outcome_mkt_neutral_hit == null) {
      return { evento, esito: `esito${orizzonte}: senza riferimento di mercato quel giorno`, tono: null };
    }
    const eccesso =
      setup.outcome_mkt_neutral_excess_pct != null
        ? ` (${segno(setup.outcome_mkt_neutral_excess_pct)})`
        : "";
    return setup.outcome_mkt_neutral_hit === 1
      ? { evento, esito: `sopra il mercato${orizzonte}${eccesso}`, tono: "ok" }
      : { evento, esito: `sotto il mercato${orizzonte}${eccesso}`, tono: "bad" };
  }

  if (quando === null && setup.conversion_source === "reconciled") {
    return { evento, esito: "esito non misurabile", tono: null };
  }
  return { evento, esito: "esito in maturazione", tono: null };
}

/** Per il dialogo del segnale: la barra su cui il setup si e' convertito, SOLO
 *  quando differisce da quella che il segnale mostra oggi. */
export function conversionBarNote(
  convertedSignalDate: string | null | undefined,
  alertSignalDate: string | null | undefined,
): string | null {
  if (!convertedSignalDate || convertedSignalDate === alertSignalDate?.slice(0, 10)) return null;
  const quando = giorno(convertedSignalDate);
  return quando
    ? `Il setup si è convertito sulla barra del ${quando}; il segnale è stato aggiornato dopo, perché la condizione è proseguita.`
    : null;
}
