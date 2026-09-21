import { Radar } from "lucide-react";
import { Link } from "react-router-dom";

import type { Mover, MoversBlock, VolumeSpike } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { cn } from "@/lib/utils";

/* ─── MarketEventsRail — the deliberately thin one ──────────────────────── *
 *
 * Due flussi di eventi (massimi/minimi a 52 settimane, volume spike) in una
 * colonna stretta, ogni riga ridotta a ticker piu' un numero.
 *
 * ⚠️ Erano TRE: il pre-market e' uscito di qui quando la fascia in cima alla
 * pagina l'ha preso come soggetto, con la sua finestra, i volumi e la
 * distinzione fra aziende e fondi a leva. Tre righe per lato senza contesto
 * erano la stessa informazione detta peggio, in un secondo posto da tenere
 * allineato.
 *
 * IL NOME DELL'AZIENDA C'E'. Per un periodo non c'era, e la ragione era
 * buona: quando la riga delle attivita' erano quattro card uguali, a 1280px
 * ognuna aveva ~230px contro colonne numeriche che ne volevano gia' 241, e la
 * colonna del nome si riduceva a 0px — l'informazione non veniva ridotta,
 * spariva in silenzio, e solo su alcuni schermi.
 *
 * Quel vincolo non c'e' piu': questa card occupa una colonna sua o l'intera
 * larghezza sotto le altre due, quindi lo spazio c'e'. Le righe usano
 * `StockIdentity`, lo STESSO componente di Top movers e Volumi — cosi' il
 * carattere e' uniforme per costruzione invece che per copia, e il logo aiuta
 * a riconoscere un titolo prima di leggerne il codice.
 *
 * Everything here stays visible at every width — nothing hides behind a tab,
 * which is the property that made this preferable to folding the four cards
 * into a segmented control.
 */

interface Props {
  movers: MoversBlock;
}

function RailHeader({ label, count }: { label: string; count?: number }) {
  return (
    <div className="px-3 py-1 border-y bg-muted/40 shrink-0 flex items-baseline justify-between gap-2">
      <span className="text-[0.6765rem] uppercase tracking-[0.16em] font-bold text-muted-foreground truncate">
        {label}
      </span>
      {count != null && (
        <span className="text-[0.6765rem] tabular-nums text-muted-foreground shrink-0">{count}</span>
      )}
    </div>
  );
}

/** One rail row: ticker on the left, a single value on the right.
 *  `min-w-0` on the ticker and `shrink-0` on the value is the whole layout
 *  contract — the ticker truncates, the number never does. */
function RailRow({
  ticker,
  name,
  value,
  tone,
  title,
}: {
  ticker: string;
  name: string | null;
  value: string;
  tone: "pos" | "neg" | "warn" | "mute";
  title: string;
}) {
  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(ticker)}`}
        title={title}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors"
      >
        <StockIdentity ticker={ticker} name={name} forma="riga" />
        <span
          className={cn(
            "ml-auto shrink-0 text-[0.7647rem] font-semibold tabular-nums",
            tone === "pos" && "text-emerald-800 dark:text-emerald-400",
            tone === "neg" && "text-rose-600 dark:text-rose-400",
            tone === "warn" && "text-amber-700 dark:text-amber-400",
            tone === "mute" && "text-muted-foreground",
          )}
        >
          {value}
        </span>
      </Link>
    </li>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="px-3 py-2 text-[0.7059rem] text-muted-foreground">{label}</div>;
}

export function MarketEventsRail({ movers }: Props) {
  /* ⚠️ La terza sezione era il PRE-MARKET, ed e' stata tolta: il pre-market e'
   * il soggetto della fascia in cima alla pagina, dove ha la sua finestra, i
   * volumi, la distinzione fra aziende e fondi a leva e il perche' di un
   * eventuale vuoto. Qui erano tre righe per lato senza contesto — e due posti
   * che dicono la stessa cosa sono due posti da tenere allineati. */
  const highs = movers.new_52w_high.slice(0, 5);
  const lows = movers.new_52w_low.slice(0, 3);
  const spikes = movers.volume_spikes.slice(0, 5);

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle icon={Radar} label="Sintesi eventi" />
        </div>

        {/* Two orientations, because this card occupies two different slots.
            At dense-3+ it is the narrow third column beside two taller cards,
            so the sections stack and it scrolls internally rather than setting
            the row height. Between md and dense-3 the row only fits two cards,
            so this one spans the full width underneath them — and there the
            same three sections read far better side by side than as one very
            long column. `dense-3:grid-cols-1` comes last so the wider
            breakpoint wins. */}
        <div className="flex-1 min-h-0 overflow-y-auto grid grid-cols-1 md:grid-cols-2 dense-3:grid-cols-1 md:divide-x dense-3:divide-x-0 divide-border/40 [&>*]:min-w-0">
          <section className="min-w-0">
            <RailHeader
              label="52 settimane"
              count={movers.new_52w_high.length + movers.new_52w_low.length}
            />
            {highs.length === 0 && lows.length === 0 ? (
              <Empty label="Nessun evento" />
            ) : (
              <ul>
                {highs.map((m: Mover) => (
                  <RailRow
                    key={`h-${m.ticker}`}
                    ticker={m.ticker}
                    name={m.name}
                    value={`$${m.last_close.toFixed(2)}`}
                    tone="pos"
                    title={`${m.name} — nuovo massimo 52 settimane`}
                  />
                ))}
                {lows.map((m: Mover) => (
                  <RailRow
                    key={`l-${m.ticker}`}
                    ticker={m.ticker}
                    name={m.name}
                    value={`$${m.last_close.toFixed(2)}`}
                    tone="neg"
                    title={`${m.name} — nuovo minimo 52 settimane`}
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="min-w-0">
            <RailHeader label="Volume spike" count={movers.volume_spikes.length} />
            {spikes.length === 0 ? (
              <Empty label="Nessuno spike" />
            ) : (
              <ul>
                {spikes.map((m: VolumeSpike) => (
                  <RailRow
                    key={m.ticker}
                    ticker={m.ticker}
                    name={m.name}
                    value={`${m.vol_ratio.toFixed(1)}×`}
                    tone="warn"
                    title={`${m.name} — ${m.vol_ratio.toFixed(1)}× il volume medio a 20 giorni`}
                  />
                ))}
              </ul>
            )}
          </section>

        </div>
      </CardContent>
    </Card>
  );
}
