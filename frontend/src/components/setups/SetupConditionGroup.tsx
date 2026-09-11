import { CalendarClock, Clock, TrendingDown, TrendingUp } from "lucide-react";

import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { waitingDays, type Setup } from "@/hooks/useSetups";
import { daysUntil, earningsProximityDays } from "@/lib/earningsProximity";
import type { ConditionGroup } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

/* ─── One condition, stated once, then who is waiting for it ─────────────── *
 *
 * The page used to render one card per setup, each repeating the full
 * condition sentence. Measured on a live payload: fifty cards carried five
 * distinct sentences. Here the sentence is the heading and the rows carry only
 * what actually differs — the stock, the trigger level, the priority, the wait.
 *
 * The heading is the point of the layout, not decoration: "twenty positions
 * are waiting for the price to cross back over the EMA50" is a fact about the
 * market the card grid could not express at all.
 */

/** Priority as a bar. Deliberately NOT a percentage and never given the visual
 *  weight of one: `convenience` is an attention score for ordering, none of
 *  the engine's calibration applies to it, and this page's whole premise is
 *  that setups make no forecast. Scaled 65-90 because the live range is
 *  71.8-84.3 — on a 0-100 axis every bar would look the same. */
function PriorityBar({ value }: { value: number }) {
  const pct = Math.max(4, Math.min(100, ((value - 65) / 25) * 100));
  return (
    <span className="flex items-center gap-2" title="Priorità: ordina la lista, non è una probabilità">
      <span className="h-1.5 w-10 shrink-0 rounded-full bg-muted overflow-hidden">
        <span className="block h-full rounded-full bg-amber-500" style={{ width: `${pct}%` }} />
      </span>
      <span className="tabular-nums text-xs font-semibold">{Math.round(value)}</span>
    </span>
  );
}

/** Ticker and name on ONE line, unlike the shared StockIdentity which stacks
 *  them and stands 66px tall. Measured: at fifty rows that stack alone was
 *  3300px — most of a five-screen page, spent on a second line per row that
 *  says nothing the tooltip cannot. StockIdentity is left alone because the
 *  pages that use it show a handful of rows, where the stack reads better. */
function InlineIdentity({ ticker, name }: { ticker: string; name: string | null }) {
  return (
    // items-center, not items-baseline: a logo has no baseline to sit on, and
    // aligning the row on one leaves it floating above the text.
    <span className="flex items-center gap-2 min-w-0">
      <StockLogo ticker={ticker} size="xs" />
      <span className="text-sm font-bold tabular-nums shrink-0">{ticker}</span>
      {name && (
        <span className="text-xs text-muted-foreground truncate" title={name}>
          {name}
        </span>
      )}
    </span>
  );
}

/** The column template, declared once so the header and every row cannot drift
 *  apart — the failure mode of hand-aligned "tables" built out of divs. */
/* Una colonna vuota per OGNI riga del gruppo non va renderizzata.
 *
 * Alcune famiglie di condizione non hanno un livello di prezzo da attraversare
 * — lo dice gia il tooltip di `DistanceCell`: "questo innesco non e un
 * attraversamento di prezzo" — quindi per quei gruppi «Livello d'innesco» e
 * «Distanza» mostrano un trattino su tutte le righe. Due colonne che occupano
 * larghezza per non dire nulla, su una tabella che gia taglia «Attesa» a
 * destra.
 *
 * ⚠️ I quattro template sono LETTERALI e non composti a runtime. Il purger di
 * Tailwind legge solo stringhe letterali: un
 * `` `sm:grid-cols-[${cols.join("_")}]` `` verrebbe eliminato dal bundle di
 * produzione e il difetto sarebbe invisibile in sviluppo. E la stessa regola
 * che CLAUDE.md impone alle mappe di tono.
 *
 * ⚠️ E la decisione e per GRUPPO, non globale: dove la colonna porta un dato
 * resta. Nascondere una colonna perche' una riga non la riempie sarebbe il
 * difetto opposto. */
const BASE = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3";

const COLS = {
  levelAndDistance: `${BASE} sm:grid-cols-[minmax(0,1fr)_132px_88px_92px_64px]`,
  levelOnly: `${BASE} sm:grid-cols-[minmax(0,1fr)_132px_88px_64px]`,
  distanceOnly: `${BASE} sm:grid-cols-[minmax(0,1fr)_88px_92px_64px]`,
  neither: `${BASE} sm:grid-cols-[minmax(0,1fr)_88px_64px]`,
} as const;

/** Quali colonne opzionali questo gruppo ha davvero da mostrare. */
export interface GroupColumns {
  level: boolean;
  distance: boolean;
  cols: string;
}

export function columnsFor(setups: Setup[]): GroupColumns {
  const level = setups.some((x) => x.annotations?.levels?.[0] != null);
  const distance = setups.some((x) => x.distance_atr != null);
  const cols = level
    ? distance
      ? COLS.levelAndDistance
      : COLS.levelOnly
    : distance
      ? COLS.distanceOnly
      : COLS.neither;
  return { level, distance, cols };
}

/** Distance to the trigger, in ATR. Colour is the reading, not decoration:
 *  under a quarter of an average session's range is a genuinely different
 *  situation from three sessions away, and the number alone does not say so
 *  to anyone who has not internalised what an ATR is. */
function DistanceCell({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <span
        className="hidden sm:block text-xs text-muted-foreground tabular-nums"
        title="Questo innesco non è un attraversamento di prezzo: non c'è un livello da cui misurare"
      >
        —
      </span>
    );
  }
  const tone =
    value <= 0.25
      ? "text-emerald-800 dark:text-emerald-400 font-semibold"
      : value <= 1
        ? "text-foreground"
        : "text-muted-foreground";
  return (
    <span
      className={cn("hidden sm:block text-xs tabular-nums", tone)}
      title={`${value.toFixed(2)} volte l'ATR: ${
        value <= 0.25
          ? "a portata di una sessione normale"
          : value <= 1
            ? "circa una giornata di movimento tipico"
            : "servono più sedute nella direzione giusta"
      }`}
    >
      {value.toFixed(2)}×
    </span>
  );
}

/** La trimestrale cade dentro la finestra di attesa di questo setup.
 *
 * Risponde alla sola domanda che *In formazione* e il calendario non possono
 * porre da sole: **il setup si risolve prima o dopo la trimestrale?** Una
 * trimestrale sovrascrive la tesi tecnica, quindi un setup che scade dopo di
 * essa e un oggetto diverso da uno che scade prima.
 *
 * ⚠️ Solo un'icona, e il resto nel titolo accessibile. La cella dell'attesa
 * porta gia un numero di giorni («da quanto aspetta»), e affiancargliene un
 * secondo («fra quanto pubblica») produrrebbe due numeri che si leggono
 * uguali e significano cose opposte — il difetto di unita che l'audit del 10
 * settembre ha trovato quattro volte.
 *
 * ⚠️ Ambra, non rosa/smeraldo. In questo progetto quella tavolozza significa
 * direzione di mercato; una trimestrale in arrivo non ha direzione, e ambra e
 * gia il colore che il badge sugli alert usa per la stessa cosa.
 *
 * ⚠️ Vive nella cella dell'attesa, non accanto al ticker. Un elemento
 * `shrink-0` messo dentro l'identita toglierebbe larghezza al NOME, che e
 * l'unica traccia flessibile della riga: e la forma esatta del difetto che
 * CLAUDE.md registra tre volte in un pomeriggio — cede l'etichetta e
 * sopravvive la decorazione. Il costo accettato e che sotto `sm` sparisce
 * insieme all'attesa che qualifica.
 */
function EarningsMarker({ setup }: { setup: Setup }) {
  const gg = earningsProximityDays(setup.next_earnings_date, daysUntil(setup.pending_until));
  if (gg === null) return null;
  const quando = gg === 0 ? "oggi" : gg === 1 ? "fra 1 giorno" : `fra ${gg} giorni`;
  const label = `Trimestrale il ${setup.next_earnings_date?.slice(0, 10)}, ${quando}: cade dentro la finestra di attesa del setup`;
  return (
    <CalendarClock
      data-testid="setup-earnings-marker"
      role="img"
      aria-label={label}
      className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400"
    />
  );
}


function GroupHeaderRow({ columns }: { columns: GroupColumns }) {
  return (
    <li className={cn(columns.cols, "px-3 py-1 border-b bg-muted/20")}>
      <span className="text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground">Titolo</span>
      {columns.level && (
      <span className="hidden sm:block text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground">
        Livello d'innesco
      </span>
      )}
      <span className="text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground justify-self-end sm:justify-self-start">
        Priorità
      </span>
      {columns.distance && (
      <span
        className="hidden sm:block text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground"
        title="Distanza dal livello d'innesco, in multipli dell'ATR del titolo"
      >
        Distanza
      </span>
      )}
      <span className="hidden sm:block text-[0.6765rem] uppercase tracking-[0.14em] text-muted-foreground justify-self-end">
        Attesa
      </span>
    </li>
  );
}

function SetupLine({
  setup,
  onOpen,
  columns,
}: {
  setup: Setup;
  onOpen: (s: Setup) => void;
  columns: GroupColumns;
}) {
  const days = waitingDays(setup);
  const level = setup.annotations?.levels?.[0];
  return (
    <li>
      {/* A button, not a Link. The row used to navigate straight to the stock
          page, which answers "what is this company" rather than "why is this
          here" — the question a row in this list actually raises. The ticker
          inside is still a link for when the stock page IS what you want. */}
      <button
        type="button"
        onClick={() => onOpen(setup)}
        className={cn(columns.cols, "w-full text-left px-3 py-1 hover:bg-accent/30 transition-colors")}
      >
        <InlineIdentity ticker={setup.ticker} name={setup.name} />

        {/* The trigger level is what you would actually set an alert on, so it
            sits next to the name rather than in a footnote. */}
        {columns.level && (
          <span className="hidden sm:block text-xs text-muted-foreground tabular-nums truncate">
            {level ? `${level.label} ${level.price.toFixed(2)}` : "—"}
          </span>
        )}

        <span className="justify-self-end sm:justify-self-start">
          <PriorityBar value={setup.convenience} />
        </span>

        {columns.distance && <DistanceCell value={setup.distance_atr} />}

        <span className="hidden sm:flex items-center gap-1 justify-self-end text-xs text-muted-foreground whitespace-nowrap">
          <EarningsMarker setup={setup} />
          <Clock className="h-3 w-3" aria-hidden />
          {days === null ? "—" : days === 0 ? "oggi" : `${days}g`}
        </span>
      </button>
    </li>
  );
}

export function SetupConditionGroup({
  group,
  onOpen,
}: {
  group: ConditionGroup;
  onOpen: (s: Setup) => void;
}) {
  const bull = group.tone === "bull";
  // Calcolato sul gruppo, non sulla singola riga: una colonna sparisce solo
  // se NESSUN setup del gruppo la riempie.
  const columns = columnsFor(group.setups);
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="px-3 py-2 border-b bg-muted/30 flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 font-semibold text-sm",
              bull ? "text-emerald-800 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
            )}
          >
            {bull ? (
              <TrendingUp className="h-4 w-4 shrink-0" aria-hidden />
            ) : (
              <TrendingDown className="h-4 w-4 shrink-0" aria-hidden />
            )}
            {group.title}
          </span>
          <span className="text-xs text-muted-foreground">{group.hint}</span>
          <span className="ml-auto text-xs text-muted-foreground whitespace-nowrap">
            <b className="text-foreground tabular-nums">{group.setups.length}</b>{" "}
            {group.setups.length === 1 ? "titolo" : "titoli"}
            {" · "}
            {/* Stated once per group, and labelled for what it is. It counts
                how much of the detector's fixed gate chain is satisfied, so it
                is the same number for every setup of that detector at the same
                stage — measured live at ONE distinct value across 20 setups.
                A per-row bar implied a variation that does not exist. */}
            <span title="Quota della catena di condizioni del detector già soddisfatta — è una proprietà del detector, uguale per tutti i suoi setup allo stesso stadio">
              catena {group.proximitySpread
                ? `${Math.round(group.proximitySpread[0] * 100)}–${Math.round(group.proximitySpread[1] * 100)}%`
                : `${Math.round(group.proximityMedian * 100)}%`}
            </span>
          </span>
        </div>

        <ul className="divide-y divide-border/40">
          {/* Column names, per group. They were missing entirely: the rows
              carried four unlabelled values and the reader had to infer which
              number was a price, which a score and which a count. */}
          <GroupHeaderRow columns={columns} />
          {group.setups.map((s) => (
            <SetupLine key={s.id} setup={s} onOpen={onOpen} columns={columns} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
