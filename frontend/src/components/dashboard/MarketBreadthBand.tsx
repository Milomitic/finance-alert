import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { CardUpdatedAt } from "@/components/stock/CardUpdatedAt";
import { formatVariazione } from "@/lib/marketNumber";
import { type MoodKey, type RegionDef, type RegionMood, regionMoods } from "@/lib/marketRegions";
import { cn } from "@/lib/utils";

/* ─── L'ampiezza, una riga per continente ─────────────────────────────────── *
 *
 * Questa banda ERA `MarketMoodStrip`, una scheda a se' subito sotto la fascia
 * del battito. Le due dicevano le stesse cose — percentuale sopra la EMA200,
 * avanzanti su discendenti, media, numero di titoli — dalla stessa istantanea,
 * a due centimetri di distanza. Un doppione non e' solo spreco di spazio: sono
 * due posti da tenere allineati, e il giorno che divergono nessuno sa a quale
 * credere.
 *
 * ⚠️ E da qui in poi le regioni sono TRE RIGHE PARI, non una coda di
 * percentuali sotto un umore unico. Un solo verdetto sul catalogo intero
 * media tre mercati che quel giorno possono fare cose opposte: «Neutrale»
 * nasceva spesso da un'America ferma, un'Europa in rosso e un'Asia in verde —
 * cioe' da tre notizie, nessuna delle quali era «neutrale». Le stesse misure,
 * nello stesso ordine, su tre righe, sono l'unica forma in cui si possono
 * confrontare.
 *
 * ⚠️ E resta un'ISTANTANEA, presa alla scansione. Sta accanto a numeri che
 * battono ogni quindici secondi, ed e' esattamente la situazione in cui un
 * dato di dodici ore fa si legge come fresco — per questo l'eta' e' scritta
 * accanto al titolo, non in un suggerimento.
 */

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
  computedAt?: string | null;
}

const UMORE: Record<MoodKey, { label: string; icona: ReactNode; classe: string }> = {
  bullish: {
    label: "Bullish",
    icona: <TrendingUp className="h-3 w-3" aria-hidden />,
    classe: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  bearish: {
    label: "Bearish",
    icona: <TrendingDown className="h-3 w-3" aria-hidden />,
    classe: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
  },
  neutral: {
    label: "Neutrale",
    icona: <Minus className="h-3 w-3" aria-hidden />,
    classe: "bg-muted text-muted-foreground",
  },
};

function tono(v: number): string {
  if (v > 0) return "text-emerald-800 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/** ⚠️ Una griglia SOLA, dichiarata una volta e usata dall'intestazione e da
 *  ogni riga: e' cio' che rende le tre regioni confrontabili invece di
 *  soltanto vicine. Tre righe allineate a mano divergono al primo ritocco —
 *  e' il difetto che la tabella dei setup aveva chiuso dichiarando il
 *  template in un posto solo. Letterale, perche' il purger di Tailwind legge
 *  solo stringhe intere. */
const RIGA = "grid grid-cols-[86px_minmax(0,1fr)_auto] items-center gap-x-2 sm:grid-cols-[92px_minmax(0,1fr)_104px_52px]";

/** La barra avanzanti/discendenti di una regione, con i suoi conteggi.
 *
 *  ⚠️ I numeri restano accanto alla barra: una proporzione non dice la
 *  DIMENSIONE del campione, e 3 su 5 disegna la stessa barra di 300 su 500. */
function BarraAD({ su, giu }: { su: number; giu: number }) {
  const mossi = su + giu;
  const quota = mossi > 0 ? (su / mossi) * 100 : 0;
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="w-8 shrink-0 text-right text-[0.6765rem] font-semibold tabular-nums text-emerald-800 dark:text-emerald-400">
        {su}
      </span>
      <span
        className="flex h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted"
        aria-hidden
        title={`${su} titoli in rialzo, ${giu} in ribasso`}
      >
        {mossi > 0 ? (
          <>
            <span className="h-full bg-emerald-500" style={{ width: `${quota}%` }} />
            <span className="h-full flex-1 bg-rose-500" />
          </>
        ) : null}
      </span>
      <span className="w-8 shrink-0 text-[0.6765rem] font-semibold tabular-nums text-rose-600 dark:text-rose-400">
        {giu}
      </span>
    </span>
  );
}

function RigaRegione({ region, mood }: { region: RegionDef; mood: RegionMood }) {
  const umore = UMORE[mood.mood];
  /* ⚠️ Zero titoli misurati non e' un mercato neutrale: e' l'assenza di una
     misura. La riga lo DICE invece di disegnare una barra vuota accanto a un
     «Neutrale», che si legge come un verdetto. */
  const misurata = mood.total_stocks > 0;
  return (
    <div className={cn(RIGA, "py-0.5")}>
      <span className="flex min-w-0 items-center gap-1.5">
        {region.flagSrc ? (
          <img
            src={region.flagSrc}
            alt=""
            width={16}
            height={11}
            style={{ width: "16px", height: "11px", objectFit: "cover" }}
            className="shrink-0 rounded-[1px] shadow-sm"
          />
        ) : (
          <span className="shrink-0 text-sm" aria-hidden>{region.emoji}</span>
        )}
        <span className="truncate text-xs font-semibold">{region.label}</span>
      </span>

      {misurata ? (
        <BarraAD su={mood.advancers} giu={mood.decliners} />
      ) : (
        <span className="text-[0.6765rem] text-muted-foreground">nessun titolo misurato</span>
      )}

      {misurata ? (
        <span
          className="hidden text-[0.6765rem] tabular-nums text-muted-foreground sm:block"
          title="Quota di titoli sopra la media mobile a 200 giorni e a 50 giorni"
        >
          EMA200 <span className="font-semibold text-foreground">{mood.pct_above_ema200.toFixed(0)}%</span>
          {" · 50 "}
          <span className="font-semibold text-foreground">{mood.pct_above_ema50.toFixed(0)}%</span>
        </span>
      ) : (
        <span className="hidden sm:block" />
      )}

      <span
        className={cn(
          "justify-self-end text-xs font-bold tabular-nums",
          misurata ? tono(mood.avg_change) : "text-muted-foreground",
        )}
        title="Variazione media dei titoli della regione nell'ultima seduta"
      >
        {misurata ? formatVariazione(mood.avg_change) : "—"}
      </span>

      {/* L'umore sta SOTTO il nome e non in una colonna propria: e' una
          conclusione derivata dai numeri accanto, non un quinto dato. */}
      <span
        className={cn(
          "col-start-1 inline-flex w-fit items-center gap-1 rounded px-1 py-0 text-[0.6176rem] font-bold",
          umore.classe,
        )}
      >
        {umore.icona}
        {misurata ? umore.label : "n/d"}
      </span>
    </div>
  );
}

export function MarketBreadthBand({ global, byIndex, computedAt }: Props) {
  /* Zero titoli misurati non e' un mercato neutrale: e' l'assenza di una
   * misura. La striscia che questa banda sostituisce aveva gia' questa
   * guardia e va conservata — «Neutrale · 0,0% > EMA200 · A/D 0/0» e' un
   * verdetto di mercato scritto sul nulla, nel testo piu' grande della
   * pagina. */
  if (!global.stocks_with_data) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Minus className="h-4 w-4 shrink-0" aria-hidden />
        Nessun dato di ampiezza: non c'è nessuna lettura di mercato da mostrare.
      </div>
    );
  }

  const regioni = regionMoods(byIndex);

  return (
    <div className="min-w-0">
      <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
          Umore e ampiezza per continente
        </span>
        {/* ⚠️ L'eta' RELATIVA, non l'orario: «istantanea delle 23:54» letto
            alle 10:34 del mattino dopo si legge come recente, e quel dato ha
            undici ore. «11h fa» non si puo' fraintendere. */}
        <CardUpdatedAt updatedAt={computedAt} className="text-[0.6765rem]" />
        <a
          href="#breadth"
          className="ml-auto text-[0.6765rem] text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          dettaglio per indice
        </a>
      </div>

      <div className="divide-y divide-border/40">
        {regioni.map(({ region, mood }) => (
          <RigaRegione key={region.code} region={region} mood={mood} />
        ))}
      </div>

      {/* Il catalogo intero, sotto e in piccolo. ⚠️ Queste tre misure NON
          hanno un equivalente per regione con la stessa definizione — i
          conteggi 52 settimane del globale contano i titoli VICINI
          all'estremo, quelli per indice i NUOVI estremi — e spacchettarle a
          occhio produrrebbe due numeri con lo stesso nome e due significati.
          Restano dove sono, dichiarate per quello che sono. */}
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 border-t pt-1 text-[0.6765rem] text-muted-foreground">
        <span title="Titoli con storico sufficiente sul totale del catalogo">
          catalogo <span className="font-semibold tabular-nums text-foreground">{global.stocks_with_data}</span>
          /{global.stocks_total}
        </span>
        <span title="RSI(14) sopra 70 · sotto 30, su tutto il catalogo">
          ipercomprati <span className="font-semibold tabular-nums text-foreground">{global.rsi_overbought_count}</span>
          {" · ipervenduti "}
          <span className="font-semibold tabular-nums text-foreground">{global.rsi_oversold_count}</span>
        </span>
        <span title="Titoli VICINI al massimo · al minimo delle ultime 52 settimane, su tutto il catalogo">
          al max 52s <span className="font-semibold tabular-nums text-foreground">{global.near_52w_high_count}</span>
          {" · al min "}
          <span className="font-semibold tabular-nums text-foreground">{global.near_52w_low_count}</span>
        </span>
      </div>
    </div>
  );
}
