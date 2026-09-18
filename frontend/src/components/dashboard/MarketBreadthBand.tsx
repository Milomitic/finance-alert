import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { CardUpdatedAt } from "@/components/stock/CardUpdatedAt";
import { formatVariazione } from "@/lib/marketNumber";
import { type MoodKey, regionMoods } from "@/lib/marketRegions";
import { cn } from "@/lib/utils";

/* ─── L'ampiezza del catalogo, dentro la fascia ───────────────────────────── *
 *
 * Questa banda ERA `MarketMoodStrip`, una scheda a se' subito sotto la fascia
 * del battito. Le due dicevano le stesse cose: percentuale sopra la EMA200,
 * avanzanti su discendenti, media, numero di titoli — quattro numeri su sei,
 * dalla stessa istantanea, a due centimetri di distanza. Un doppione non e'
 * solo spreco di spazio: sono due posti da tenere allineati, e il giorno che
 * divergono nessuno sa quale dei due crede.
 *
 * Quindi la striscia e' stata assorbita qui, e con lei la parte che aveva di
 * suo e che non va persa: le BANDIERE regionali, cioe' l'unico posto dove si
 * legge che l'America sta salendo mentre l'Asia scende.
 *
 * ⚠️ Vale per tutto quello che sta qui dentro: e' un'ISTANTANEA, presa alla
 * scansione. Sta accanto a numeri che battono ogni quindici secondi, ed e'
 * esattamente la situazione in cui un dato di dodici ore fa si legge come
 * fresco — per questo l'eta' e' scritta accanto al titolo, non in un tooltip.
 */

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
  computedAt?: string | null;
}

const UMORE: Record<MoodKey, { label: string; icona: ReactNode; classe: string }> = {
  bullish: {
    label: "Bullish",
    icona: <TrendingUp className="h-3.5 w-3.5" aria-hidden />,
    classe: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
  bearish: {
    label: "Bearish",
    icona: <TrendingDown className="h-3.5 w-3.5" aria-hidden />,
    classe: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
  },
  neutral: {
    label: "Neutrale",
    icona: <Minus className="h-3.5 w-3.5" aria-hidden />,
    classe: "bg-muted text-muted-foreground",
  },
};

function tono(v: number): string {
  if (v > 0) return "text-emerald-800 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/** Una coppia «etichetta valore». Il valore ha sempre il suo nome accanto:
 *  la versione precedente scriveva «in rialzo 639 · 348» e il 348 non aveva
 *  nome — era rosa, e basta. */
function Dato({ etichetta, children, title }: {
  etichetta: string; children: ReactNode; title?: string;
}) {
  return (
    <div className="min-w-0" title={title}>
      <span className="text-muted-foreground">{etichetta} </span>
      {children}
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

  const umore = UMORE[global.mood];
  const regioni = regionMoods(byIndex);
  const mossi = global.advancers + global.decliners;
  const quotaSu = mossi > 0 ? (global.advancers / mossi) * 100 : 0;

  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
          Umore e ampiezza
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-bold",
            umore.classe,
          )}
        >
          {umore.icona}
          {umore.label}
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

      {/* La barra avanzanti/discendenti: la stessa informazione dei due numeri,
          ma senza doverli confrontare a mente. I numeri restano, perche' una
          barra dice la proporzione e non la dimensione del campione. */}
      <div className="flex items-baseline gap-2 text-xs">
        <span className="font-semibold tabular-nums text-emerald-800 dark:text-emerald-400">
          {global.advancers} <span className="font-normal text-muted-foreground">su</span>
        </span>
        <div
          className="flex h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-muted"
          aria-hidden
          title={`${global.advancers} titoli in rialzo, ${global.decliners} in ribasso, ${global.unchanged} invariati`}
        >
          <div className="h-full bg-emerald-500" style={{ width: `${quotaSu}%` }} />
          <div className="h-full flex-1 bg-rose-500" />
        </div>
        <span className="font-semibold tabular-nums text-rose-600 dark:text-rose-400">
          <span className="font-normal text-muted-foreground">giù</span> {global.decliners}
        </span>
      </div>

      <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
        <Dato etichetta="sopra EMA200">
          <span className="font-semibold tabular-nums">
            {global.pct_above_ema200.toFixed(1).replace(".", ",")}%
          </span>
        </Dato>
        <Dato etichetta="media">
          <span className={cn("font-semibold tabular-nums", tono(global.avg_change_pct))}>
            {formatVariazione(global.avg_change_pct)}
          </span>
        </Dato>
        <Dato etichetta="titoli" title="Titoli con storico sufficiente sul totale del catalogo">
          <span className="font-semibold tabular-nums">{global.stocks_with_data}</span>
          <span className="text-muted-foreground">/{global.stocks_total}</span>
        </Dato>
        <Dato etichetta="ipercomprati" title="RSI(14) sopra 70 · sotto 30">
          <span className="font-semibold tabular-nums">{global.rsi_overbought_count}</span>
          <span className="text-muted-foreground"> · ipervenduti </span>
          <span className="font-semibold tabular-nums">{global.rsi_oversold_count}</span>
        </Dato>
        <Dato etichetta="al max 52s" title="Titoli vicini al massimo · al minimo delle ultime 52 settimane">
          <span className="font-semibold tabular-nums">{global.near_52w_high_count}</span>
          <span className="text-muted-foreground"> · al min </span>
          <span className="font-semibold tabular-nums">{global.near_52w_low_count}</span>
        </Dato>
        <Dato etichetta="sopra EMA50">
          <span className="font-semibold tabular-nums">
            {global.pct_above_ema50.toFixed(1).replace(".", ",")}%
          </span>
        </Dato>
      </div>

      {/* Le regioni, con le bandiere che la striscia assorbita aveva di suo.
          E' l'unico posto dove si legge «l'America sale mentre l'Asia scende»,
          e senza sarebbe l'unica cosa persa nella fusione. */}
      {regioni.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-1.5">
          {regioni.map(({ region, mood }) => (
            <span key={region.code} className="flex shrink-0 items-center gap-1.5">
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
              <span className="text-[0.7059rem] font-semibold">{region.label}</span>
              <span
                className="text-[0.6765rem] tabular-nums text-muted-foreground"
                title="Quota di titoli sopra la media mobile a 200 giorni"
              >
                {mood.pct_above_ema200.toFixed(0)}%
              </span>
              <span className={cn("text-[0.7059rem] font-bold tabular-nums", tono(mood.avg_change))}>
                {formatVariazione(mood.avg_change)}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
