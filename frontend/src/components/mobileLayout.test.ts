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
      file: "components/AlertsInsightCard.tsx",
      pattern: /flex w-full flex-wrap items-center gap-x-1\.5 gap-y-1 pl-3/,
      misura: "/alerts +9px: sei colonne a larghezza fissa più un rientro pl-6",
    },
  ];

  it("copre tutti gli otto siti misurati", () => {
    // Se qualcuno cancella una voce invece di correggere il codice, il
    // conteggio lo dice.
    expect(PIN).toHaveLength(8);
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
      .reduce((n, [, t]) => n + (t.match(/\bhint=|<InfoHint\b/g)?.length ?? 0), 0);
    expect(usi).toBeGreaterThanOrEqual(15);
  });
});
