import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { CardUpdatedAt } from "@/components/stock/CardUpdatedAt";
import { getIndexMeta } from "@/lib/indexMeta";
import { formatVariazione } from "@/lib/marketNumber";
import { type MoodKey, type RegionDef, type RegionMood, regionMoods } from "@/lib/marketRegions";
import { cn } from "@/lib/utils";

/* ─── Umore e ampiezza: tre continenti, e sotto ognuno le sue borse ───────── *
 *
 * Questa banda ERA `MarketMoodStrip`, una scheda a se' subito sotto la fascia
 * del battito. Le due dicevano le stesse cose dalla stessa istantanea, a due
 * centimetri di distanza: un doppione e' due posti da tenere allineati, e il
 * giorno che divergono nessuno sa a quale credere.
 *
 * ⚠️ Le regioni sono TRE BLOCCHI PARI, non una coda di percentuali sotto un
 * umore unico. Un solo verdetto sul catalogo intero media tre mercati che quel
 * giorno possono fare cose opposte: «Neutrale» nasceva spesso da un'America
 * ferma, un'Europa in rosso e un'Asia in verde — tre notizie, nessuna delle
 * quali era «neutrale».
 *
 * ⚠️ E sotto ogni continente ci sono le sue BORSE (2026-09-25). Un totale
 * europeo non dice se a scendere e' Milano o Londra, e sono due notizie
 * diverse. Le righe per borsa hanno reso visibile un difetto del totale — che
 * sommava panieri sovrapposti — e il totale ora si calcola su panieri
 * disgiunti, con la sua base SCRITTA nella riga del continente: vedi
 * `lib/marketRegions`.
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

function tono(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-800 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/** ⚠️ Una griglia SOLA, dichiarata una volta e usata dall'intestazione delle
 *  colonne, dalla riga di ogni continente e da quella di ogni borsa: e' cio'
 *  che rende i numeri confrontabili in colonna invece di soltanto vicini.
 *  Righe allineate a mano divergono al primo ritocco. Letterale, perche' il
 *  purger di Tailwind legge solo stringhe intere. */
const RIGA =
  "grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_auto] items-center gap-x-3 " +
  "sm:grid-cols-[9rem_minmax(0,1fr)_6.5rem_4rem]";

/** Stesso stile delle altre intestazioni della fascia («Si muove adesso»):
 *  le due meta' della riga si leggono come una cosa sola solo se parlano con
 *  la stessa voce. */
const INTESTAZIONE = "text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground";

function Bandiera({ src, emoji }: { src: string | null; emoji?: string }) {
  if (!src) return <span className="w-3.5 shrink-0 text-center text-sm leading-none" aria-hidden>{emoji}</span>;
  return (
    <img
      src={src}
      alt=""
      width={14}
      height={10}
      style={{ width: "14px", height: "10px", objectFit: "cover" }}
      className="shrink-0 rounded-[1px] shadow-sm"
    />
  );
}

/** La barra avanzanti/discendenti, con i suoi conteggi.
 *
 *  ⚠️ I numeri restano accanto alla barra: una proporzione non dice la
 *  DIMENSIONE del campione, e 3 su 5 disegna la stessa barra di 300 su 500. */
function BarraAD({ su, giu }: { su: number; giu: number }) {
  const mossi = su + giu;
  const quota = mossi > 0 ? (su / mossi) * 100 : 0;
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="w-8 shrink-0 text-right text-[0.7059rem] font-semibold tabular-nums text-emerald-800 dark:text-emerald-400">
        {su}
      </span>
      <span className="flex h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        {mossi > 0 ? (
          <>
            <span className="h-full bg-emerald-500" style={{ width: `${quota}%` }} />
            <span className="h-full flex-1 bg-rose-500" />
          </>
        ) : null}
      </span>
      <span className="w-8 shrink-0 text-[0.7059rem] font-semibold tabular-nums text-rose-600 dark:text-rose-400">
        {giu}
      </span>
    </span>
  );
}

/** EMA200 in chiaro, EMA50 un gradino sotto: e' la stessa colonna per
 *  continente e borsa, e l'intestazione dice quale e' quale. */
function Ema({ e200, e50 }: { e200: number | null; e50: number | null }) {
  return (
    <span className="hidden text-right text-[0.7059rem] tabular-nums sm:block">
      <span className="font-semibold text-foreground">{e200 != null ? `${e200.toFixed(0)}%` : "—"}</span>
      <span className="text-muted-foreground"> · {e50 != null ? `${e50.toFixed(0)}%` : "—"}</span>
    </span>
  );
}

/** La riga del continente: il verdetto, la BASE su cui e' calcolato, e i
 *  numeri del totale. ⚠️ La base sta a schermo e non in un suggerimento: sotto
 *  ci sono righe di borse, e senza dirlo il totale si leggerebbe come la loro
 *  somma — che non e', quando i panieri si sovrappongono. */
function RigaContinente({ region, mood }: { region: RegionDef; mood: RegionMood }) {
  const umore = UMORE[mood.mood];
  /* ⚠️ Zero titoli misurati non e' un mercato neutrale: e' l'assenza di una
     misura. La riga lo DICE invece di disegnare una barra vuota accanto a un
     «Neutrale», che si legge come un verdetto. */
  const misurata = mood.total_stocks > 0;
  const base = region.indexCodes.map((c) => getIndexMeta(c).shortName).join(" + ");
  return (
    <div
      className={cn(RIGA, "rounded bg-muted/50 px-1 py-0.5")}
      title={misurata
        ? `${region.label}: umore calcolato su ${base}, ${mood.total_stocks} titoli. Bullish sopra il 60% di partecipazione (media di EMA200 ed EMA50) con piu' rialzi che ribassi, bearish sotto il 40% con piu' ribassi.`
        : undefined}
    >
      <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5">
        <Bandiera src={region.flagSrc} emoji={region.emoji} />
        <span className="text-sm font-bold">{region.label}</span>
        <span
          className={cn(
            "inline-flex items-center gap-0.5 rounded px-1 text-[0.6176rem] font-bold leading-4",
            umore.classe,
          )}
        >
          {umore.icona}
          {misurata ? umore.label : "n/d"}
        </span>
      </span>
      <span className="truncate text-[0.7059rem] text-muted-foreground">
        {misurata ? `totale su ${base}` : "nessun titolo misurato"}
      </span>
      {misurata ? <Ema e200={mood.pct_above_ema200} e50={mood.pct_above_ema50} /> : <span className="hidden sm:block" />}
      <span className={cn("justify-self-end text-sm font-bold tabular-nums", misurata ? tono(mood.avg_change) : "text-muted-foreground")}>
        {misurata ? formatVariazione(mood.avg_change) : "—"}
      </span>
    </div>
  );
}

/** Una borsa: porta alla lista dei suoi titoli, come la tabella completa. */
function RigaBorsa({ index, inTotal }: { index: IndexBreadth; inTotal: boolean }) {
  const meta = getIndexMeta(index.code);
  return (
    <Link
      to={`/stocks?index=${encodeURIComponent(index.code)}`}
      className={cn(RIGA, "rounded px-1 py-0.5 hover:bg-accent/40")}
      title={[
        `${meta.fullName} · ${index.n} titoli nel catalogo`,
        `${index.advancers} in rialzo, ${index.decliners} in ribasso`,
        inTotal ? null : "fuori dal totale del continente: i suoi titoli maggiori sono gia' contati in un altro indice",
        "apri i titoli dell'indice",
      ].filter(Boolean).join(" · ")}
    >
      <span className="flex min-w-0 items-center gap-1.5 pl-3">
        <Bandiera src={meta.countryCode ? `/flags/${meta.countryCode}.svg` : null} />
        <span className="truncate text-sm">{meta.shortName}</span>
        {!inTotal && (
          <sup className="shrink-0 text-[0.6176rem] text-muted-foreground">
            1<span className="sr-only"> fuori dal totale del continente</span>
          </sup>
        )}
      </span>
      <BarraAD su={index.advancers} giu={index.decliners} />
      <Ema e200={index.pct_above_ema200} e50={index.pct_above_ema50} />
      <span className={cn("justify-self-end text-sm font-semibold tabular-nums", tono(index.avg_change_pct))}>
        {formatVariazione(index.avg_change_pct) ?? "—"}
      </span>
    </Link>
  );
}

export function MarketBreadthBand({ global, byIndex, computedAt }: Props) {
  /* Zero titoli misurati non e' un mercato neutrale: e' l'assenza di una
   * misura. «Neutrale · 0,0% > EMA200 · A/D 0/0» e' un verdetto di mercato
   * scritto sul nulla, nel testo piu' grande della pagina. */
  if (!global.stocks_with_data) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Minus className="h-4 w-4 shrink-0" aria-hidden />
        Nessun dato di ampiezza: non c'è nessuna lettura di mercato da mostrare.
      </div>
    );
  }

  const regioni = regionMoods(byIndex);
  const qualcunaFuori = regioni.some((r) => r.indices.some((i) => !i.inTotal));

  return (
    <div className="min-w-0">
      <div className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className={INTESTAZIONE}>Umore e ampiezza</span>
        {/* ⚠️ L'eta' RELATIVA, non l'orario: «istantanea delle 23:54» letto
            alle 10:34 del mattino dopo si legge come recente, e quel dato ha
            undici ore. «11h fa» non si puo' fraintendere. */}
        <CardUpdatedAt updatedAt={computedAt} className="text-xs" />
        <a
          href="#breadth"
          className="ml-auto text-[0.6765rem] text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          tabella completa
        </a>
      </div>

      {/* Le intestazioni delle colonne, sulla stessa griglia delle righe.
          Sotto `sm` la colonna EMA non c'e', e con lei la sua etichetta. */}
      <div className={cn(RIGA, "px-1 pb-0.5 text-[0.6471rem] uppercase tracking-wider text-muted-foreground")}>
        <span />
        {/* Sul telefono la colonna vale ~120px e l'etichetta intera ne occupa
            ~155: sconfinerebbe sopra «media». Il testo corto dice la stessa
            cosa, e il colore dei due numeri sotto fa il resto. */}
        <span className="truncate text-center">
          <span className="sm:hidden">su · giù</span>
          <span className="hidden sm:inline">in rialzo · in ribasso</span>
        </span>
        <span className="hidden text-right sm:block" title="Quota di titoli sopra la media mobile a 200 e a 50 giorni">
          EMA200 · 50
        </span>
        <span className="justify-self-end" title="Variazione media dei titoli nell'ultima seduta">media</span>
      </div>

      <div className="space-y-1.5">
        {regioni.map(({ region, mood, indices }) => (
          <section key={region.code} aria-label={region.label}>
            <RigaContinente region={region} mood={mood} />
            {indices.map(({ index, inTotal }) => (
              <RigaBorsa key={index.code} index={index} inTotal={inTotal} />
            ))}
          </section>
        ))}
      </div>

      {/* Il catalogo intero, sotto e in piccolo. ⚠️ Queste misure NON hanno un
          equivalente per regione con la stessa definizione — i conteggi 52
          settimane del globale contano i titoli VICINI all'estremo, quelli per
          indice i NUOVI estremi — e spacchettarle a occhio produrrebbe due
          numeri con lo stesso nome e due significati. */}
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 border-t pt-1 text-[0.6765rem] text-muted-foreground">
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
        {qualcunaFuori && (
          <span>
            <sup>1</sup> fuori dal totale del continente: i suoi titoli maggiori sono già contati in un altro indice
          </span>
        )}
      </div>
    </div>
  );
}
