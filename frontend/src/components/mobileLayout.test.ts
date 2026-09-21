import { describe, expect, it } from "vitest";

/* ─── I difetti di larghezza su mobile, fissati alla sorgente ─────────────
 *
 * jsdom NON fa layout: `getBoundingClientRect` restituisce zeri e nessun test
 * comportamentale di questo repo può vedere un traboccamento orizzontale. Lo
 * stesso limite che CLAUDE.md registra per axe — «senza stili calcolati non
 * vede contrasto, target touch, focus» — vale qui, quindi la verifica vera è
 * stata fatta nel browser a 375×812 e i NUMERI stanno nei commenti sotto.
 *
 * Quello che questo file può fare, e fa, è impedire che le classi che reggono
 * quelle misure spariscano in una rifattorizzazione: sono una riga ciascuna,
 * non hanno effetto visibile su desktop, e sono quindi esattamente il tipo di
 * dettaglio che qualcuno «pulisce».
 *
 * ⚠️ Ogni censimento ha un PAVIMENTO. Una regola «ogni X ha la proprietà P»
 * passa da sola quando gli X sono zero — il fallimento che CLAUDE.md registra
 * tre volte — e un glob che smette di risolvere è il modo più facile per
 * ottenerne zero senza accorgersene.
 */

const SORGENTI = import.meta.glob("/src/**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function sorgente(file: string): string {
  const chiave = Object.keys(SORGENTI).find((k) => k.endsWith(file));
  if (!chiave) throw new Error(`sorgente non trovata: ${file}`);
  return SORGENTI[chiave];
}

describe("censimento", () => {
  it("il glob risolve davvero dei file", () => {
    // Il pavimento del pavimento: senza questo ogni asserzione sotto può
    // essere vera di niente.
    expect(Object.keys(SORGENTI).length).toBeGreaterThanOrEqual(150);
  });
});

describe("traboccamento orizzontale a 375px", () => {
  /* Ogni voce è stata misurata nel browser PRIMA e DOPO la correzione. */
  const PIN: { file: string; pattern: RegExp; misura: string }[] = [
    {
      file: "components/calendar/MonthNav.tsx",
      pattern: /min-w-\[9rem\]\s+sm:min-w-\[13\.5rem\]/,
      misura: "/calendar +51px: il pavimento a 13.5rem rendeva la riga 412px",
    },
    {
      file: "pages/StocksBrowserPage.tsx",
      pattern: /flex\s+flex-wrap\s+items-center\s+gap-2\s+gap-y-1/,
      misura: "/stocks +87px: il gruppo interno della barra misurava 445px",
    },
    {
      file: "pages/MacroDetailPage.tsx",
      pattern: /flex\s+flex-row\s+flex-wrap\s+items-center\s+justify-between/,
      misura: "/macro/:id +66px: i due gruppi di toggle non andavano a capo",
    },
    {
      file: "pages/SectorDetailPage.tsx",
      pattern: /flex\s+flex-wrap\s+items-center\s+justify-between\s+gap-3/,
      misura: "/sectors/:name +84px: intestazione senza wrap, più p-6 su mobile",
    },
    {
      file: "pages/InstitutionalsPage.tsx",
      pattern: /<header className="flex flex-wrap items-center justify-between gap-3">/,
      misura: "/institutionals +201px: quattro filtri accanto al titolo",
    },
    {
      file: "components/ui/section-title.tsx",
      pattern: /justify-between gap-x-3 gap-y-1 min-w-0/,
      misura:
        "/setups +13px: senza min-w-0 la radice si pianta sulla propria " +
        "min-content (375px in un genitore di 350) e il truncate non entra " +
        "mai in funzione",
    },
    {
      file: "pages/InstitutionalDetailPage.tsx",
      pattern: /min-w-0 max-w-full rounded border bg-background/,
      misura:
        "/institutionals/:slug +15px: un <select> si dimensiona sull'opzione " +
        "più lunga, non sul contenitore",
    },
    {
      file: "components/calendar/FilterStrip.tsx",
      pattern: /inline-flex max-w-full flex-wrap/,
      misura:
        "/calendar +19px: un `inline-flex` si dimensiona sulla propria " +
        "max-content, quindi il `flex-wrap` accanto non entra mai in funzione. " +
        "Trovato dal gate e2e in CI, non dalla passata a mano.",
    },
    {
      file: "components/AlertsInsightCard.tsx",
      pattern: /flex w-full flex-wrap items-center gap-x-1\.5 gap-y-1 pl-3/,
      misura: "/alerts +9px: sei colonne a larghezza fissa più un rientro pl-6",
    },
  ];

  it("copre tutti i siti misurati", () => {
    // Se qualcuno cancella una voce invece di correggere il codice, il
    // conteggio lo dice.
    expect(PIN).toHaveLength(9);
  });

  it.each(PIN)("$file resta corretto — $misura", ({ file, pattern }) => {
    expect(sorgente(file)).toMatch(pattern);
  });
});

describe("le spiegazioni delle intestazioni sono raggiungibili al tocco", () => {
  /* `title` non si apre su un telefono: non c'è hover da produrre e il
   * long-press apre il menu del sistema. Una spiegazione di colonna lì dentro
   * è scritta e mai letta da chi usa il telefono. */
  const INTESTAZIONE = /<(?:TableHead|th)\b[^>]*\stitle=(?:"[^"]{25,}"|\{[A-Z_]{4,}\})/g;

  function siti(): string[] {
    const out: string[] = [];
    for (const [file, testo] of Object.entries(SORGENTI)) {
      if (file.includes(".test.")) continue;
      // Le intestazioni si scrivono spesso su più righe: si normalizza.
      const piatto = testo.replace(/\s+/g, " ");
      for (const m of piatto.matchAll(INTESTAZIONE)) {
        out.push(`${file}: ${m[0].slice(0, 90)}`);
      }
    }
    return out;
  }

  it("nessuna intestazione di tabella porta una spiegazione dentro `title`", () => {
    expect(siti()).toEqual([]);
  });

  it("e le spiegazioni esistono davvero, altrove", () => {
    /* Il pavimento che rende falsificabile l'asserzione sopra: senza, avrebbe
     * lo stesso identico esito se qualcuno cancellasse ogni spiegazione
     * invece di spostarla. Contate al momento della conversione: 11 in
     * AlertsTable, più Positions, RecentAlertsFeed ×2, SignalEffectiveness ×2,
     * StockBrowserTable. */
    const usi = Object.entries(SORGENTI)
      .filter(([f]) => !f.includes(".test."))
      .reduce((n, [, t]) => n + (t.match(/\bhint=|<InfoHint\b|<HintLabel\b|<HintAnchor\b/g)?.length ?? 0), 0);
    expect(usi).toBeGreaterThanOrEqual(15);
  });
});

describe("le intestazioni di tabella non portano l'icona «i»", () => {
  /* L'icona allargava ogni colonna che ne aveva una, su tutte le righe della
   * tabella, per una spiegazione che si legge una volta. Nelle intestazioni
   * il grilletto è ora la parola stessa, sottolineata a tratti
   * (`HintLabel` / `HintAnchor` in `ui/info-hint.tsx`). Fuori dalle tabelle —
   * tessere, schede, dialog — l'icona resta: lì non costa una colonna. */
  const CELLA = /<(th|TableHead)\b[^>]*>([\s\S]*?)<\/\1>/g;

  function offensori(testo: string): string[] {
    const out: string[] = [];
    for (const m of testo.matchAll(CELLA)) {
      if (/<InfoHint\b/.test(m[2])) out.push(m[0].replace(/\s+/g, " ").slice(0, 90));
    }
    return out;
  }

  it("il rilevatore vede il difetto (controllo negativo)", () => {
    // Senza, un'espressione che non trova mai niente renderebbe verde il test
    // qui sotto per sempre.
    expect(offensori('<th className="x">Prob.<InfoHint label="Prob." text="t" /></th>')).toHaveLength(1);
    expect(offensori("<TableHead>Prob.</TableHead>")).toEqual([]);
  });

  it("nessuna <th> o <TableHead> contiene un InfoHint", () => {
    const siti = Object.entries(SORGENTI)
      .filter(([f]) => !f.includes(".test."))
      .flatMap(([f, t]) => offensori(t).map((o) => `${f}: ${o}`));
    expect(siti).toEqual([]);
  });

  it("neanche le intestazioni fatte a griglia, che il rilevatore sopra non vede", () => {
    for (const f of ["alert/SignalOutcomeList.tsx", "dashboard/AlertsCompactPanel.tsx"]) {
      expect(sorgente(f), f).not.toMatch(/<InfoHint\b/);
    }
  });

  it("`TableHead hint=` monta l'etichetta sottolineata, non l'icona", () => {
    const t = sorgente("components/ui/table.tsx");
    expect(t).toMatch(/<HintLabel\b/);
    expect(t).not.toMatch(/InfoHint/);
  });

  it("e le spiegazioni ci sono ancora: il pavimento", () => {
    // 23 alla conversione, senza i `TableHead hint=` che passano da
    // `table.tsx`: se qualcuno le cancellasse invece di spostarle, il
    // censimento qui sopra resterebbe verde.
    const usi = Object.entries(SORGENTI)
      .filter(([f]) => !f.includes(".test.") && !f.endsWith("ui/info-hint.tsx"))
      .reduce((n, [, t]) => n + (t.match(/<HintLabel\b|<HintAnchor\b/g)?.length ?? 0), 0);
    expect(usi).toBeGreaterThanOrEqual(20);
  });
});

describe("le card della home: una riga per titolo, e niente nome su telefono", () => {
  /* Richiesta del 2026-09-21: ticker e nome sulla STESSA riga su desktop,
   * per una vista piu' densa, e il nome mai su telefono. Le card la prendono
   * da `StockIdentity forma="riga"`, un proprietario solo: se una card torna
   * alla forma impilata, questa lista lo dice. */
  const CARD = [
    "dashboard/ConfluenceCard.tsx",
    "dashboard/LiveVolumeMoversCard.tsx",
    "dashboard/MarketEventsRail.tsx",
    "dashboard/RecentAlertsFeed.tsx",
    "dashboard/TopMoversCard.tsx",
    "dashboard/TopPicksCard.tsx",
    "dashboard/TopStocksTable.tsx",
  ];

  it.each(CARD)("%s usa l'identita' in riga", (f) => {
    const t = sorgente(f);
    // Uno spazio dopo il nome: un commento che cita `<StockIdentity>` non e'
    // un uso.
    const usi = t.match(/<StockIdentity\s[^>]*>/g) ?? [];
    // Il pavimento: una card che smettesse di usare StockIdentity passerebbe
    // l'asserzione sotto senza averne nessuna.
    expect(usi.length).toBeGreaterThan(0);
    for (const u of usi) expect(u, f).toContain('forma="riga"');
  });

  it("il pannello Segnali ha tre colonne: «Per indice» e' stato tolto", () => {
    const t = sorgente("dashboard/AlertsCompactPanel.tsx");
    // Il CODICE, non la prosa: il commento che racconta la rimozione nomina
    // ancora la colonna, ed e' giusto che lo faccia.
    expect(t).not.toMatch(/key: "byindex"|AlertsByIndexBars/);
    for (const k of ["confluence", "top", "feed"]) expect(t).toContain(`key: "${k}"`);
    expect(t).toMatch(/row-full:grid-cols-3/);
  });
});
