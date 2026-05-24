import type { SignalLevel } from "@/api/types";

function levelFromDetail(detail: string | null | undefined): number | null {
  if (!detail) return null;
  const m = detail.match(/livello\s+(\d+(?:[.,]\d+)?)/i);
  return m ? parseFloat(m[1].replace(",", ".")) : null;
}

function levelFromAnnotations(tone: string | null | undefined, levels: SignalLevel[]): number | null {
  const want = tone === "bear" ? "resistance" : "support";
  const hit = levels.find((l) => l.kind === want && Number.isFinite(l.price));
  if (hit) return hit.price;
  const any = levels.find((l) => Number.isFinite(l.price));
  return any ? any.price : null;
}

function fmtLvl(n: number): string {
  return n >= 100 ? n.toFixed(1) : n.toFixed(2);
}

/* Case-specific plain-language gloss for a chain step. Weaves in the actual
   direction (rialzista/ribassista) and the relevant level when available, so a
   line reads e.g. "Inversione ribassista a ridosso della resistenza a 89.20". */
export function glossForStep(
  label: string | null | undefined,
  detail: string | null | undefined,
  tone: string | null | undefined,
  levels: SignalLevel[] = [],
): string | null {
  if (!label) return null;
  const L = label.toLowerCase();
  const dir = tone === "bull" ? "rialzista" : tone === "bear" ? "ribassista" : "";
  const lvlNum = levelFromDetail(detail) ?? levelFromAnnotations(tone, levels);
  const lvl = lvlNum != null ? fmtLvl(lvlNum) : null;
  const sideWord = tone === "bear" ? "della resistenza" : "del supporto";
  const actors = tone === "bear" ? "i venditori riprendono il controllo" : "i compratori riprendono il controllo";

  if (/neckline/.test(L))
    return `Rottura della neckline${lvl ? ` a ${lvl}` : ""}: conferma la figura e attiva il segnale.`;
  if (/candela|inversione|engulfing|martello|doji|reversal/.test(L))
    return `Inversione ${dir}${lvl ? ` a ridosso ${sideWord} a ${lvl}` : " su un livello tecnico"}: ${actors}.`;
  if (/breakout|rottur/.test(L))
    return `Rottura ${dir}${lvl ? ` del livello ${lvl}` : " di un livello chiave"}: forza ${tone === "bear" ? "dei venditori" : "dei compratori"} e possibile avvio di un nuovo movimento.`;
  if (/volume/.test(L))
    return "Volume in aumento: conferma che dietro il movimento ci sono scambi reali, non un falso segnale.";
  if (/triangolo|cuneo|flag|bandiera/.test(L))
    return "Figura di compressione: i prezzi si restringono prima di una rottura direzionale.";
  if (/doppio|testa e spalle/.test(L))
    return `Figura di inversione ${dir}: il prezzo respinge piu volte lo stesso livello prima di cambiare direzione.`;
  if (/52 settimane|massimo annuale/.test(L))
    return "Prezzo vicino al massimo annuale: zona di forza relativa e momentum positivo.";
  if (/divergenz/.test(L))
    return `Divergenza ${dir}: prezzo e oscillatore vanno in direzioni opposte, spesso anticipa un cambio di direzione.`;
  if (/pullback|ritracc|ripresa/.test(L))
    return "Ritracciamento dentro il trend, seguito dalla ripresa nella direzione principale.";
  if (/gap/.test(L))
    return "Salto di prezzo tra due sedute: segnala uno shock di domanda o di offerta.";
  if (/adx/.test(L))
    return "ADX elevato: misura la forza del trend in corso, non la sua direzione.";
  if (/squeeze|compress/.test(L))
    return "Volatilita compressa: di solito precede un movimento direzionale ampio.";
  if (/resistenz/.test(L))
    return `Resistenza${lvl ? ` a ${lvl}` : ""}: livello sopra il prezzo dove tende a entrare offerta.`;
  if (/supporto/.test(L))
    return `Supporto${lvl ? ` a ${lvl}` : ""}: livello sotto il prezzo dove tende a entrare domanda.`;
  if (/trend/.test(L))
    return `Direzione di fondo del prezzo (${dir || "neutra"}), che fa da contesto al segnale.`;
  if (/rsi/.test(L))
    return "RSI in zona estrema (ipercomprato o ipervenduto): possibile esaurimento del movimento.";
  if (/macd/.test(L))
    return "Segnale dal MACD: incrocio o divergenza che indica un cambio di momentum.";
  if (/earnings|utili|trimestral/.test(L))
    return "Sorpresa sugli utili: catalizzatore fondamentale dietro al movimento.";
  if (/analist|upgrade|target/.test(L))
    return "Revisione degli analisti: miglioramento del giudizio o del prezzo obiettivo.";
  if (/insider/.test(L))
    return "Acquisti di insider: segnale di fiducia da parte del management.";
  return null;
}
