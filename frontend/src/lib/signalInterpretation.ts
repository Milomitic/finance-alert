/* Short plain-language gloss for a chain-step label, matched by keyword. Adds
   a "what this event means" line under the detector detail so a non-expert can
   read the chain. Returns null when no keyword matches. */
const STEP_GLOSS: { re: RegExp; text: string }[] = [
  { re: /neckline/i, text: "Linea di collo della figura: la sua rottura conferma il pattern e ne attiva il segnale." },
  { re: /breakout|rottur/i, text: "Superamento di un livello chiave: indica forza dei compratori e il possibile avvio di un nuovo movimento." },
  { re: /volume/i, text: "Volume in aumento: conferma che dietro il movimento ci sono scambi reali e non un falso segnale." },
  { re: /triangolo|cuneo|flag|bandiera/i, text: "Figura di compressione: i prezzi si restringono prima di una rottura direzionale." },
  { re: /doppio minimo|doppio massimo|testa e spalle/i, text: "Figura di inversione: il prezzo respinge piu volte lo stesso livello prima di cambiare direzione." },
  { re: /52 settimane|massimo annuale/i, text: "Prezzo vicino al massimo annuale: zona di forza relativa e di momentum positivo." },
  { re: /divergenz/i, text: "Prezzo e oscillatore vanno in direzioni opposte: spesso anticipa un cambio di direzione." },
  { re: /pullback|ritracc|ripresa/i, text: "Ritracciamento dentro un trend, seguito dalla ripresa nella direzione principale." },
  { re: /gap/i, text: "Salto di prezzo tra due sedute: segnala uno shock di domanda o di offerta." },
  { re: /adx/i, text: "ADX elevato: misura la forza del trend in corso, non la sua direzione." },
  { re: /squeeze|compress/i, text: "Volatilita compressa: di solito precede un movimento direzionale ampio." },
  { re: /reversal|inversione/i, text: "Tentativo di inversione a ridosso di un livello tecnico rilevante." },
  { re: /trend/i, text: "Direzione di fondo del prezzo, che fa da contesto al segnale." },
  { re: /supporto/i, text: "Livello sotto il prezzo dove tende a entrare domanda." },
  { re: /resistenz/i, text: "Livello sopra il prezzo dove tende a entrare offerta." },
  { re: /rsi/i, text: "RSI in zona estrema (ipercomprato o ipervenduto): possibile esaurimento del movimento." },
  { re: /macd/i, text: "Segnale dal MACD: incrocio o divergenza che indica un cambio di momentum." },
  { re: /candela|martello|engulfing|doji/i, text: "Configurazione a candele tipica di inversione di breve." },
  { re: /earnings|utili|trimestral/i, text: "Sorpresa sugli utili: catalizzatore fondamentale dietro al movimento." },
  { re: /analist|upgrade|target/i, text: "Revisione degli analisti: miglioramento del giudizio o del prezzo obiettivo." },
  { re: /insider/i, text: "Acquisti di insider: segnale di fiducia da parte del management." },
];

export function glossForStep(label: string | undefined | null): string | null {
  if (!label) return null;
  for (const g of STEP_GLOSS) {
    if (g.re.test(label)) return g.text;
  }
  return null;
}

export interface SignalConclusion {
  headline: string;
  detail: string;
}

/* Derive a plain-language conclusion from the signal snapshot: what the chain
   amounts to and what it means. Descriptive, not a trade recommendation. */
export function concludeSignal(opts: {
  tone: "bull" | "bear" | "neutral";
  confidence: number | null;
  invalidationLevel: number | null;
}): SignalConclusion {
  const { tone, confidence, invalidationLevel } = opts;
  const dir = tone === "bull" ? "rialzista" : tone === "bear" ? "ribassista" : "neutra";
  const conf = confidence != null ? ` (confidenza ${confidence}%)` : "";
  const headline = `Esito: lettura ${dir}${conf}`;

  let detail: string;
  if (tone === "bull") {
    detail =
      "Nel complesso la catena conferma un setup rialzista: i compratori hanno preso il controllo e il quadro favorisce la continuazione al rialzo nel breve termine.";
  } else if (tone === "bear") {
    detail =
      "Nel complesso la catena conferma un setup ribassista: i venditori hanno preso il controllo e il quadro favorisce la prosecuzione al ribasso nel breve termine.";
  } else {
    detail = "Nel complesso la catena delinea un quadro tecnico senza una direzione netta.";
  }

  if (invalidationLevel != null) {
    const side = tone === "bear" ? "sopra" : "sotto";
    detail += ` Il segnale resta valido fino a quando il prezzo non va ${side} ${invalidationLevel.toFixed(2)}: oltre quel livello la lettura decade.`;
  }

  return { headline, detail };
}
