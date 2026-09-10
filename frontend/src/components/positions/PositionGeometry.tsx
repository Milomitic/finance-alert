import type { Position } from "@/api/types";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

/* La geometria di una posizione aperta, come barra.
 *
 * Entry, stop, target e prezzo erano quattro colonne di numeri. Quattro numeri
 * non rispondono alla sola domanda che conta su una posizione aperta — **sono
 * piu vicino allo stop o al target?** — perche rispondere richiede tre
 * sottrazioni e un confronto, per ogni riga.
 *
 * La barra e quella risposta. Le tre colonne di prezzi diventano una sola: la
 * pista, con i numeri precisi sotto. La tabella si restringe invece di
 * allargarsi, che e la direzione giusta ogni volta che si aggiunge qualcosa a
 * una griglia (vedi «quando lo spazio finisce cede l'IDENTITA» in CLAUDE.md).
 *
 * ⚠️ **E una misura geometrica, non una promessa di esecuzione.** La distanza
 * dallo stop non e la perdita massima: un gap notturno apre sotto lo stop e
 * l'ordine esegue dove trova mercato, non dove e scritto. Vale la stessa
 * regola del piano operativo, che descrive una geometria e non impartisce
 * un'istruzione.
 *
 * ⚠️ Solo per le posizioni APERTE. Su una chiusa la domanda e diversa — dove e
 * finita — e l'ha gia risposta il chip di uscita (Stop / Target / Manuale).
 * Una barra li mostrerebbe una corsa che non e piu in corso.
 */

export interface Geometry {
  /** Dove sta l'entry sulla pista stop→target, 0..1 gia limitato. */
  entryAt: number;
  /** L'entry cade FUORI dalla pista: non e un dato incoerente, e uno stop
   *  spostato oltre l'ingresso per bloccare un guadagno. Il marcatore va
   *  disegnato al bordo e detto, non nascosto. */
  entryOffTrack: boolean;
  /** Dove sta il prezzo, 0..1 limitato. Null quando il prezzo manca: la
   *  pista resta leggibile, il cursore no. */
  priceAt: number | null;
  /** Il prezzo ha superato un estremo. Su una posizione aperta significa che
   *  lo stop non e stato eseguito, o che il target e stato passato senza
   *  chiudere — in entrambi i casi e la cosa piu importante nella riga. */
  beyond: "stop" | "target" | null;
  /** Il prezzo e dal lato del guadagno rispetto all'entry. Null senza prezzo. */
  inProfit: boolean | null;
}

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** La pista va sempre dallo stop (0) al target (1), qualunque sia il lato.
 *
 *  ⚠️ La formula non ha bisogno di sapere se e long o short, ed e questo il
 *  punto: `(x - stop) / (target - stop)` ha numeratore e denominatore dello
 *  STESSO segno in entrambi i casi, perche su uno short lo stop sta sopra e il
 *  target sotto. Passare `side` sarebbe un secondo modo di sapere la stessa
 *  cosa, cioe un modo di sbagliarla quando i due non concordano.
 *
 *  Verificato su una posizione vera (ARGX.BR long, entry 830.80, stop 625.52,
 *  target 1036.08, prezzo 865.20): t = 0.584, entry a 0.50 — oltre l'ingresso,
 *  cioe in guadagno, che e quello che diceva la colonna P&L.
 *
 *  Null quando la geometria non esiste: senza stop o senza target non c'e una
 *  pista, e inventarne un estremo sarebbe un'affermazione che i dati non
 *  fanno. Lo stesso criterio con cui `money.ts` non inventa una valuta.
 */
export function geometry(p: Position): Geometry | null {
  const { stop_price: stop, target_price: target, entry_price: entry } = p;
  if (stop == null || target == null) return null;
  if (!Number.isFinite(stop) || !Number.isFinite(target)) return null;
  const span = target - stop;
  if (span === 0) return null;

  const rawEntry = (entry - stop) / span;
  const price = p.last_price;
  const rawPrice =
    price != null && Number.isFinite(price) ? (price - stop) / span : null;

  return {
    entryAt: clamp01(rawEntry),
    entryOffTrack: rawEntry < 0 || rawEntry > 1,
    priceAt: rawPrice == null ? null : clamp01(rawPrice),
    beyond:
      rawPrice == null ? null : rawPrice < 0 ? "stop" : rawPrice > 1 ? "target" : null,
    inProfit: rawPrice == null ? null : rawPrice > rawEntry,
  };
}

/** Percentuale CSS da una frazione. Sempre inline, mai in una classe: il
 *  purger di Tailwind vede solo stringhe letterali, e una classe composta a
 *  runtime sparisce dal bundle di produzione senza errori (CLAUDE.md). */
const pct = (x: number) => `${(x * 100).toFixed(2)}%`;

export function PositionGeometry({ p }: { p: Position }) {
  const g = geometry(p);

  if (!g) {
    // Senza stop o senza target la pista non esiste. Restano i numeri che ci
    // sono, e il posto vuoto dice che manca un estremo.
    return (
      <div className="min-w-[13rem]">
        <PriceRow p={p} />
        <div className="mt-0.5 text-[0.6765rem] text-muted-foreground">
          {p.stop_price == null && p.target_price == null
            ? "Nessuno stop, nessun target"
            : p.stop_price == null
              ? "Nessuno stop"
              : "Nessun target"}
        </div>
      </div>
    );
  }

  const lo = g.priceAt == null ? g.entryAt : Math.min(g.entryAt, g.priceAt);
  const hi = g.priceAt == null ? g.entryAt : Math.max(g.entryAt, g.priceAt);

  return (
    <div className="min-w-[13rem]">
      <div
        className="relative h-1.5 w-full rounded-full bg-muted"
        role="img"
        aria-label={ariaLabel(p, g)}
      >
        {/* Il tratto percorso dall'ingresso a qui, del colore della direzione. */}
        {g.priceAt != null && (
          <div
            className={cn(
              "absolute inset-y-0 rounded-full",
              g.inProfit
                ? "bg-emerald-500 dark:bg-emerald-400"
                : "bg-rose-500 dark:bg-rose-400",
            )}
            style={{ left: pct(lo), width: pct(hi - lo) }}
          />
        )}

        {/* L'ingresso: l'origine da cui si misura il guadagno. */}
        <div
          className={cn(
            "absolute -top-0.5 -bottom-0.5 w-px",
            g.entryOffTrack ? "bg-foreground/30" : "bg-foreground/70",
          )}
          style={{ left: pct(g.entryAt) }}
          title={
            g.entryOffTrack
              ? `Ingresso ${formatMoney(p.entry_price, p.currency)} — fuori dalla pista: lo stop e stato spostato oltre l'ingresso`
              : `Ingresso ${formatMoney(p.entry_price, p.currency)}`
          }
        />

        {/* Il prezzo. Al bordo quando ha superato un estremo, e lo dice. */}
        {g.priceAt != null && (
          <div
            className={cn(
              "absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background",
              g.beyond === "stop"
                ? "bg-rose-600 ring-2 ring-rose-500/40"
                : g.beyond === "target"
                  ? "bg-emerald-600 ring-2 ring-emerald-500/40"
                  : g.inProfit
                    ? "bg-emerald-600 dark:bg-emerald-400"
                    : "bg-rose-600 dark:bg-rose-400",
            )}
            style={{ left: pct(g.priceAt) }}
            title={beyondTitle(p, g)}
          />
        )}
      </div>

      <PriceRow p={p} />
    </div>
  );
}

/** I tre prezzi sotto la pista, ognuno sotto il proprio estremo.
 *
 *  ⚠️ Ogni numero porta la propria valuta. Sono tutti nella stessa e la
 *  colonna Prezzo la dichiara gia, ma un numero nudo accanto a uno vestito e
 *  esattamente la classe di difetto che questa tranche ha chiuso quattro
 *  volte: l'unita che c'e nel dato e non arriva a schermo. */
function PriceRow({ p }: { p: Position }) {
  return (
    <div className="mt-1 flex items-baseline justify-between gap-2 text-[0.6765rem] tabular-nums leading-none">
      <span
        className="text-rose-600 dark:text-rose-400"
        title={`Stop ${formatMoney(p.stop_price, p.currency)}`}
      >
        <span className="opacity-60">S</span> {formatMoney(p.stop_price, p.currency)}
      </span>
      <span
        className="text-muted-foreground"
        title={`Ingresso ${formatMoney(p.entry_price, p.currency)}`}
      >
        <span className="opacity-60">E</span> {formatMoney(p.entry_price, p.currency)}
      </span>
      <span
        className="text-emerald-800 dark:text-emerald-400"
        title={`Target ${formatMoney(p.target_price, p.currency)}`}
      >
        <span className="opacity-60">T</span> {formatMoney(p.target_price, p.currency)}
      </span>
    </div>
  );
}

/** ⚠️ La barra e un `role="img"`, quindi per chi non la vede esiste SOLO
 *  questa frase. Deve contenere la risposta, non descrivere il disegno. */
export function ariaLabel(p: Position, g: Geometry): string {
  const money = (v: number | null) => formatMoney(v, p.currency);
  const dove =
    g.priceAt == null
      ? "prezzo non disponibile"
      : g.beyond === "stop"
        ? `prezzo ${money(p.last_price)}, oltre lo stop`
        : g.beyond === "target"
          ? `prezzo ${money(p.last_price)}, oltre il target`
          : `prezzo ${money(p.last_price)}, al ${Math.round(g.priceAt * 100)}% della corsa`;
  return `Da stop ${money(p.stop_price)} a target ${money(p.target_price)}, ingresso ${money(p.entry_price)}: ${dove}.`;
}

function beyondTitle(p: Position, g: Geometry): string {
  const price = formatMoney(p.last_price, p.currency);
  if (g.beyond === "stop") {
    return `${price} — oltre lo stop, e la posizione risulta ancora aperta`;
  }
  if (g.beyond === "target") {
    return `${price} — oltre il target, e la posizione risulta ancora aperta`;
  }
  return `Prezzo ${price}`;
}
