import {
  Bitcoin, CalendarClock, Clock3, Coins, Flame, Fuel, Gem, TrendingDown, TrendingUp, Zap,
} from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type {
  IndexBreadth, IndexMover, LiveQuote, MarketGlobal, MoversBlock,
} from "@/api/types";
import type { PremarketMover } from "@/api/dashboard";
import { MarketBreadthBand } from "@/components/dashboard/MarketBreadthBand";
import { MarketStateBadge, type MarketPhase } from "@/components/dashboard/MarketStateBadge";
import { Card } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { NoValue } from "@/components/ui/no-value";
import { useCalendar } from "@/hooks/useCalendar";
import { useLiveAssets, type LiveAsset } from "@/hooks/useLiveAssets";
import { useFlipList } from "@/hooks/useFlipList";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { useLiveUniverseMovers } from "@/hooks/useLiveUniverseMovers";
import { useNowTick } from "@/hooks/useNowTick";
import { usePremarketMovers } from "@/hooks/usePremarketMovers";
import { cumulativeVolumeFraction } from "@/lib/intradayVolume";
import { formatLivello, formatVariazione, posizioneNelRange } from "@/lib/marketNumber";
import { agendaDelGiorno, agendaVuota } from "@/lib/oggiMercato";
import { sparklinePoints } from "@/lib/sparkline";
import { etToday, formatDelta, usSessionClock, type UsPhase } from "@/lib/usSession";
import { cn } from "@/lib/utils";
import { fmtVolume } from "@/lib/volumeFormat";

/* ─── MarketPulseJumbotron — PROTOTIPO ────────────────────────────────────── *
 *
 * La fascia in cima al cruscotto: dove sono i mercati ADESSO, con il
 * pre-market e la seduta americana come soggetto invece che come una delle
 * tante schede.
 *
 * Quattro cose che sembrano dettagli e sono la ragione per cui questa scheda
 * non mente:
 *
 * 1. **La fase la dicono i dati, non l'orologio.** L'orologio sa che sono le
 *    11:00 di New York; non sa che e' il Giorno del Ringraziamento. Ma il
 *    backend scambia il prezzo dell'indice con quello del future quando il
 *    cash NON e' aperto (`using_futures`), quindi tre americane tutte sui
 *    futures a mercato teoricamente aperto SONO la prova che la borsa e'
 *    chiusa. Nessun calendario scritto a mano lo saprebbe, e una lista di
 *    festivita' invecchia in silenzio esattamente quando conta.
 * 2. **Un prezzo da future non si presenta come il cash** (contrassegno FUT).
 *    ⚠️ E il TRACCIATO resta quello del cash anche allora — il backend manda
 *    di proposito solo quella storia, perche' mescolarla col future darebbe
 *    salti sulla base — quindi in quel caso l'ultimo punto della linea NON e'
 *    il numero grande sopra, e la linea lo dichiara.
 * 3. **Gli ETF a leva sono marcati, non nascosti.** Un 3× si muove del 3%
 *    quando il sottostante fa l'1%: comparire fra i movers non e'
 *    un'informazione, e' la definizione dello strumento. Toglierli in silenzio
 *    sarebbe peggio — stanno in una riga a parte, col loro nome.
 * 4. **L'ampiezza e' un'ISTANTANEA** e porta la propria eta' accanto, perche'
 *    messa vicino a numeri che battono ogni quindici secondi si legge come
 *    fresca. Vive in `MarketBreadthBand`, che ha ASSORBITO la striscia d'umore
 *    che stava qui sotto e diceva le stesse cose.
 */

interface Props {
  /** Ampiezza dell'ultima scansione. Assente finche' l'istantanea non e'
   *  arrivata: la fascia della sessione vive lo stesso, perche' non dipende da
   *  nessuna interrogazione. */
  global?: MarketGlobal;
  /** Ampiezza per indice — alimenta le regioni con le bandiere. */
  byIndex?: IndexBreadth[];
  /** I movers della SEDUTA, dall'istantanea. ⚠️ Sono il ripiego che rende
   *  questo riquadro utile a mercati chiusi: senza, fuori dalla finestra del
   *  pre-market e prima che la spazzata live si popoli il riquadro diceva
   *  «niente da mostrare» — cioe' era vuoto per la maggior parte della
   *  giornata italiana, che e' quando lo si guarda. */
  movers?: MoversBlock;
  /** `computed_at` dell'istantanea — l'eta' dell'ampiezza, dichiarata. */
  computedAt?: string | null;
}

/* I tre simboli della seduta americana, nell'ordine in cui si leggono. Sono le
 * chiavi di `LIVE_ASSET_DEFINITIONS` nel backend; il resto del paniere finisce
 * nella riga di contesto. */
const USA: readonly string[] = ["^GSPC", "^IXIC", "^DJI"];

/** Il simbolo di mercato di un indice e il CODICE con cui l'ampiezza lo
 *  chiama sono due cose diverse, e la mappa e' l'unico posto in cui si
 *  incontrano. `^GSPC` e' cio' che quota Yahoo; `SP500` e' il paniere del
 *  catalogo su cui si contano i titoli. */
const CODICE_AMPIEZZA: Record<string, string> = {
  "^GSPC": "SP500",
  "^IXIC": "NDX",
  "^DJI": "DJI",
};

/** I nomi lunghi non entrano in un riquadro da 110px su un telefono, e
 *  troncati perdono proprio la parte che li distingue. */
const NOMI_BREVI: Record<string, string> = {
  "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones", "^VIX": "VIX",
  "^N225": "Nikkei", "^STOXX50E": "Stoxx 50", "FTSEMIB.MI": "FTSE MIB",
  "^HSI": "Hang Seng", "000300.SS": "CSI 300", "GC=F": "Oro", "SI=F": "Argento",
  "CL=F": "WTI", "NG=F": "Gas", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum",
};

/** Un'icona per chi non ha una bandiera. Indici e valute hanno un paese;
 *  l'oro e il bitcoin no, e senza un segno la riga di contesto e' una fila di
 *  parole tutte uguali. Le icone sono di SIGNIFICATO, non decorative: la
 *  fiamma e' il gas, la pompa e' il petrolio, il lingotto i metalli. */
const ICONA_ASSET: Record<string, { icona: typeof Coins; classe: string }> = {
  "GC=F": { icona: Coins, classe: "text-amber-500" },
  "SI=F": { icona: Coins, classe: "text-slate-400" },
  "CL=F": { icona: Fuel, classe: "text-stone-500 dark:text-stone-400" },
  "NG=F": { icona: Flame, classe: "text-orange-500" },
  "BTC-USD": { icona: Bitcoin, classe: "text-amber-500" },
  "ETH-USD": { icona: Gem, classe: "text-indigo-400" },
};

/* ⚠️ Questi colori NON sono la palette direzionale. In questa app rosa e verde
 * dicono se un prezzo sale o scende; qui l'ambra e' l'oro, l'arancio la fiamma
 * del gas, l'indaco il rombo di Ethereum — dicono DI COSA si parla, non come
 * sta andando. Vivono su icone `aria-hidden`, quindi nessuna regola di
 * contrasto le tocca: il valore accanto resta il colore del testo. */

/* ─── Il paniere a leva ───────────────────────────────────────────────────
 *
 * ETF a leva e inversi: si muovono di due o tre punti quando il sottostante ne
 * fa uno. Stanno in un gruppo LORO e non fra gli indici, per la stessa ragione
 * per cui sono usciti dalla lista dei movers del pre-market — comparire in cima
 * a una classifica di variazioni non e' una notizia, e' la definizione dello
 * strumento. Qui invece sono il soggetto: chi li guarda li guarda apposta.
 *
 * ⚠️ Sono titoli di CATALOGO, non simboli del paniere live: le quotazioni
 * arrivano da `/api/stocks/quotes`, che filtra sui titoli in catalogo. YINN ha
 * una riga solo da quando il seme scelto a mano gira all'avvio — prima non si
 * trovava nemmeno dalla barra di ricerca. Un ticker assente dal catalogo
 * compare qui come «n/d» invece di sparire in silenzio: l'assenza si vede.
 */
const ETF_LEVA: readonly string[] = ["YINN", "NUGT", "SOXL", "TQQQ", "TNA", "LABU"];

/** Le bandiere che esistono davvero in `public/flags/`. Una `<img>` verso un
 *  file assente lascia l'icona rotta a schermo: si rende solo cio' che c'e'. */
const BANDIERE = new Set(["us", "jp", "eu", "it", "hk", "cn", "gb", "de", "fr", "kr", "tw", "ca"]);

/** Sotto questo volume nel pre-market un movimento e' un singolo scambio, non
 *  un prezzo. Non si NASCONDE la riga — si dice che gli scambi sono sottili,
 *  cosi' il lettore giudica il +6% invece di riceverlo come un fatto. */
const VOLUME_SOTTILE = 10_000;

/** Righe per colonna in «si muove adesso». Dieci per lato, come la scheda Top
 *  movers: con quattro si vedeva solo la coda estrema, che e' quasi sempre un
 *  titolo sottile, e il movimento vero del giorno restava sotto il taglio. */
const RIGHE_MOVERS = 10;

/** Un movimento grosso in un contesto per lo piu' calmo va notato a colpo
 *  d'occhio: sotto questa soglia le voci della riga di contesto restano tutte
 *  della stessa taglia, come devono. */
const CONTESTO_RILEVANTE = 2.0;

function nomeBreve(a: LiveAsset): string {
  return NOMI_BREVI[a.symbol] ?? a.name;
}

function tono(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-800 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/** Perche' un numero non c'e'. L'errore della fonte quando esiste, altrimenti
 *  la verita' piu' semplice: non e' ancora arrivato. Un trattino muto manda a
 *  cercare un guasto; questo dice dove guardare. */
function perche(a: LiveAsset | undefined, nome: string): string {
  if (!a) return `${nome}: simbolo non presente nel paniere live`;
  if (a.quote?.error) return `${nome}: quotazione non disponibile (${a.quote.error})`;
  return `${nome}: quotazione non ancora ricevuta`;
}

/** La lettura convenzionale dei livelli del VIX. Non e' una previsione ed e'
 *  per questo che le soglie sono scritte nel suggerimento: chi legge «teso»
 *  deve poter vedere da dove viene. */
function bandaVix(v: number): string {
  if (v < 15) return "calmo";
  if (v < 20) return "normale";
  if (v < 30) return "teso";
  return "stress";
}

/** Chi tira e chi frena un indice, tre per lato.
 *
 * ⚠️ Perimetro INDICE, non catalogo, ed e' tutta la differenza. I Top movers
 * ordinano i mille titoli: i primi posti sono quasi sempre micro-cap ed ETF a
 * leva, che si muovono del 15% per costruzione e non dicono niente su come sta
 * andando l'S&P 500. Dentro il paniere, invece, «chi lo tira» e' una risposta
 * vera — sono i titoli che quella percentuale grande la fanno.
 *
 * ⚠️ Una colonna VUOTA resta vuota. In una seduta tutta in rosso prendere «i
 * primi tre» qualunque siano riempirebbe la colonna «su» col meno peggio dei
 * ribassi: una riga che dice il contrario di cio' che e' successo, con l'aria
 * di un dato. Il backend li filtra per segno; qui si rende cio' che arriva.
 */
function EstremiIndice({ ampiezza }: { ampiezza: IndexBreadth | undefined }) {
  const su = ampiezza?.top_gainers ?? [];
  const giu = ampiezza?.top_losers ?? [];
  if (su.length === 0 && giu.length === 0) return null;
  const riga = (voci: IndexMover[], verso: "su" | "giu") =>
    voci.map((v) => (
      <Link
        key={v.ticker}
        to={`/stocks/${encodeURIComponent(v.ticker)}`}
        className="inline-flex items-baseline gap-1 rounded px-0.5 hover:bg-accent/40"
        title={`${v.name} · ${formatVariazione(v.change_pct)}`}
      >
        <span className="font-bold tabular-nums">{v.ticker}</span>
        <span className={cn("tabular-nums", tono(verso === "su" ? 1 : -1))}>
          {formatVariazione(v.change_pct)}
        </span>
      </Link>
    ));
  /* ⚠️ Vengono dall'ISTANTANEA, non dal battito live che sta due righe
     sopra nella stessa piastrella. Un ticker con una percentuale accanto a un
     prezzo che si aggiorna ogni quindici secondi si legge come live: il
     suggerimento lo nega a parole, che e' l'unico posto dove ci sta. */
  const daIstantanea = "Dall'ultima istantanea di mercato, come i numeri di ampiezza — non dal prezzo live qui sopra";
  return (
    <div className="mt-2 hidden border-t pt-1 text-[0.6471rem] leading-tight lg:block">
      {su.length > 0 && (
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5">
          <span className="shrink-0 font-bold uppercase tracking-wider text-muted-foreground" title={daIstantanea}>su</span>
          {riga(su, "su")}
        </div>
      )}
      {giu.length > 0 && (
        <div className="mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-1.5">
          <span className="shrink-0 font-bold uppercase tracking-wider text-muted-foreground" title={daIstantanea}>giù</span>
          {riga(giu, "giu")}
        </div>
      )}
    </div>
  );
}

/* ─── Il riquadro grande di un indice americano ──────────────────────────── */
function IndiceTile({ asset, nome, ampiezza }: {
  asset: LiveAsset | undefined;
  nome: string;
  /** La riga di ampiezza di QUESTO indice, per gli estremi in fondo. */
  ampiezza: IndexBreadth | undefined;
}) {
  const q = asset?.quote;
  const cambio = q?.change_pct ?? null;
  const punti = sparklinePoints(asset?.history, 120, 26, 2);
  const live = asset?.is_live === true;
  const suFutures = asset?.using_futures === true;
  const posizione = posizioneNelRange(q?.price, q?.day_low, q?.day_high);
  const corpo = (
    <>
      <div className="flex min-w-0 items-center gap-1.5">
        {/* La bandiera dice a colpo d'occhio che le tre grandi sono americane,
            come gia' fanno le voci della riga di contesto qui sotto. */}
        <img
          src="/flags/us.svg"
          alt=""
          width={14}
          height={10}
          style={{ width: "14px", height: "10px", objectFit: "cover" }}
          className="shrink-0 rounded-[1px] shadow-sm"
        />
        <span className="truncate text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {nome}
        </span>
        {suFutures ? (
          <span
            className="shrink-0 rounded bg-amber-100 px-1 text-[0.6471rem] font-bold uppercase tracking-wider text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
            title="Cash chiuso — il prezzo viene dal contratto futures, che e' quello che si muove prima dell'apertura"
          >
            FUT
          </span>
        ) : live ? (
          /* ⚠️ `role="img"` non e' decorazione: un `aria-label` su uno span
             senza ruolo e' un attributo PROIBITO per axe
             (`aria-prohibited-attr`, lo stesso rilievo che /calendar porta in
             linea di base). */
          <span
            role="img"
            className="relative inline-flex h-1.5 w-1.5 shrink-0"
            title="Prezzo in aggiornamento ogni 15 secondi"
            aria-label="prezzo live"
          >
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
        ) : null}
      </div>
      {/* Su un telefono il riquadro vale ~87px di contenuto: prezzo e
          variazione affiancati non ci stanno, e affidarsi a `truncate`
          significherebbe tagliare proprio la cifra. Si impilano sotto `sm`. */}
      <div className="mt-0.5 flex min-w-0 flex-col sm:flex-row sm:items-baseline sm:gap-2">
        {/* Effetto tape: a ogni battito il valore lampeggia verde o rosso nel
            verso del movimento. `noTween` perche' su una fascia con una
            ventina di numeri l'interpolazione simultanea costa piu' di quanto
            renda. */}
        <span className="truncate text-lg font-bold tabular-nums leading-none sm:text-xl">
          {q?.price != null
            ? <FlashValue value={q.price} format={(v) => formatLivello(v) ?? "—"} noTween />
            : <NoValue hint={perche(asset, nome)} />}
        </span>
        <span className={cn("shrink-0 text-sm font-semibold tabular-nums", tono(cambio))}>
          {cambio != null
            ? <FlashValue value={cambio} format={(v) => formatVariazione(v) ?? "—"} noTween showArrow />
            : <NoValue hint={perche(asset, nome)} />}
        </span>
      </div>
      {/* Due informazioni che il riquadro aveva sotto mano e non diceva: di
          quanti PUNTI si e' mosso (una percentuale su un indice a cinque cifre
          non da' la misura del movimento) e da dove era partito stamattina —
          un indice sopra la sua apertura e uno sotto raccontano sedute
          diverse a parita' di segno. */}
      {(q?.change_abs != null || q?.day_open != null) && (
        <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-[0.6765rem] tabular-nums text-muted-foreground">
          {q?.change_abs != null && (
            <span title="Variazione in punti indice rispetto alla chiusura precedente">
              {q.change_abs >= 0 ? "+" : "−"}
              {formatLivello(Math.abs(q.change_abs))} pt
            </span>
          )}
          {q?.day_open != null && (
            <span title="Apertura della sessione">ap. {formatLivello(q.day_open)}</span>
          )}
        </div>
      )}
      {punti && (
        <div className="mt-1 hidden sm:block">
          {/* Il tracciato e' decorativo: la variazione qui sopra e' gia' il
              numero, e una polilinea non ha niente da annunciare a chi non la
              vede. */}
          <svg viewBox="0 0 120 26" preserveAspectRatio="none" className="h-[26px] w-full" aria-hidden>
            <polyline
              points={punti}
              fill="none"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
              className={cambio != null && cambio < 0 ? "stroke-rose-500" : "stroke-emerald-500"}
            />
          </svg>
          {/* ⚠️ Con FUT acceso il prezzo viene dal future e questa linea no:
              il backend manda solo la storia del cash, quindi l'ultimo punto
              NON e' il numero grande sopra. Dirlo costa quattro parole. */}
          <div className="text-[0.6471rem] leading-none text-muted-foreground">
            30 giorni{suFutures ? " · indice cash, non il future" : ""}
          </div>
        </div>
      )}
      {q?.day_low != null && q?.day_high != null && (
        /* `mt-5`: la barra dell'intervallo stava appiccicata al tracciato e le
           due si leggevano come un unico disegno — l'etichetta «30 giorni»
           sembrava riferita al minimo e massimo, che sono di GIORNATA. Era
           `mt-3` e non bastava: fra i due c'e' gia' una riga di testo, quindi
           lo stacco che si vede e' quello che avanza dopo di essa. */
        <div className="mt-5 hidden lg:block">
          {/* Il minimo e il massimo da soli non dicono DOVE sta il prezzo. Il
              marcatore lo dice senza far fare il conto. */}
          <div
            className="relative h-1 w-full rounded-full bg-muted"
            aria-hidden
            title={`Minimo e massimo della sessione${suFutures ? " del future" : ""}`}
          >
            {posizione != null && (
              <span
                className="absolute top-1/2 h-2.5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-sm bg-foreground/70"
                style={{ left: `${posizione * 100}%` }}
              />
            )}
          </div>
          <div className="mt-0.5 flex justify-between text-[0.6471rem] tabular-nums leading-none text-muted-foreground">
            <span>{formatLivello(q.day_low)}</span>
            <span>{formatLivello(q.day_high)}</span>
          </div>
        </div>
      )}
      <EstremiIndice ampiezza={ampiezza} />
    </>
  );
  return asset ? (
    <Link
      to={`/markets/${encodeURIComponent(asset.symbol)}`}
      className="min-w-0 rounded-md border bg-card/70 p-2 transition-colors hover:bg-accent/40"
      title={`${nome} — apri il dettaglio`}
    >
      {corpo}
    </Link>
  ) : (
    <div className="min-w-0 rounded-md border bg-card/70 p-2">{corpo}</div>
  );
}

/* ─── Una voce della riga di contesto ────────────────────────────────────── */
function Chip({ asset }: { asset: LiveAsset }) {
  const cambio = asset.quote?.change_pct ?? null;
  const nome = nomeBreve(asset);
  const bandiera = asset.flag && BANDIERE.has(asset.flag) ? `/flags/${asset.flag}.svg` : null;
  const segno = ICONA_ASSET[asset.symbol];
  const forte = cambio != null && Math.abs(cambio) >= CONTESTO_RILEVANTE;
  return (
    <Link
      to={`/markets/${encodeURIComponent(asset.symbol)}`}
      className="inline-flex min-w-0 items-center gap-1.5 rounded px-1 py-0.5 hover:bg-accent/40"
      title={[
        asset.name,
        asset.using_futures ? "prezzo dal future" : null,
        asset.is_live ? "mercato aperto adesso" : "mercato chiuso — ultimo prezzo",
      ].filter(Boolean).join(" · ")}
    >
      {bandiera ? (
        <img
          src={bandiera}
          alt=""
          width={14}
          height={10}
          style={{ width: "14px", height: "10px", objectFit: "cover" }}
          className="shrink-0 rounded-[1px] shadow-sm"
        />
      ) : segno ? (
        <segno.icona className={cn("h-3.5 w-3.5 shrink-0", segno.classe)} aria-hidden />
      ) : null}
      {/* ⚠️ Stessa taglia del prezzo. Il nome e' l'IDENTITA' della voce e il
          prezzo il suo valore: renderlo piu' piccolo del numero fa leggere la
          riga come una fila di cifre in cerca di un'etichetta. E' la stessa
          regola che questo progetto applica allo spazio che finisce — quando
          manca, cede la decorazione, non l'etichetta. */}
      <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {nome}
      </span>
      {/* Il pallino «aperto adesso» e' decorativo: il titolo del collegamento
          dice gia' a parole se il mercato e' aperto. Tredici pallini che
          pulsano sarebbero rumore, quindi questo sta fermo. */}
      {asset.is_live && (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" aria-hidden />
      )}
      <span className="text-sm font-semibold tabular-nums">
        {asset.quote?.price != null
          ? <FlashValue value={asset.quote.price} format={(v) => formatLivello(v) ?? "—"} noTween />
          : <NoValue hint={perche(asset, nome)} />}
      </span>
      {/* La variazione un gradino SOTTO nome e prezzo: in una riga da venti
          voci tre corpi uguali non hanno gerarchia, e la percentuale e' il
          contorno di un prezzo, non un terzo dato indipendente. Il neretto
          oltre la soglia di rilevanza resta: e' li' che serve l'occhio. */}
      <span
        className={cn(
          "text-xs tabular-nums",
          forte ? "font-bold" : "font-semibold",
          tono(cambio),
        )}
      >
        {cambio != null
          ? <FlashValue value={cambio} format={(v) => formatVariazione(v) ?? "—"} noTween />
          : ""}
      </span>
    </Link>
  );
}

/** Una voce del paniere a leva. Stessa grammatica delle altre — nome,
 *  prezzo, variazione — ma il collegamento porta alla scheda del TITOLO,
 *  perche' questi sono titoli di catalogo e non simboli di mercato. */
function ChipLeva({ ticker, quote }: { ticker: string; quote: LiveQuote | undefined }) {
  const cambio = quote?.change_pct ?? null;
  const forte = cambio != null && Math.abs(cambio) >= CONTESTO_RILEVANTE;
  return (
    <Link
      to={`/stocks/${encodeURIComponent(ticker)}`}
      className="inline-flex min-w-0 items-center gap-1.5 rounded px-1 py-0.5 hover:bg-accent/40"
      title={
        quote
          ? `${ticker} — ETF a leva, apri la scheda`
          : `${ticker}: nessuna quotazione. Se manca anche dalla ricerca, il titolo non e' in catalogo.`
      }
    >
      <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {ticker}
      </span>
      <span className="text-sm font-semibold tabular-nums">
        {quote?.price != null
          ? <FlashValue value={quote.price} format={(v) => formatLivello(v) ?? "—"} noTween />
          : <NoValue hint={`${ticker}: quotazione non disponibile`} />}
      </span>
      <span className={cn("text-xs tabular-nums", forte ? "font-bold" : "font-semibold", tono(cambio))}>
        {cambio != null
          ? <FlashValue value={cambio} format={(v) => formatVariazione(v) ?? "—"} noTween />
          : ""}
      </span>
    </Link>
  );
}

/* ─── Una riga della classifica «si muove adesso» ────────────────────────── */
function RigaMover({ ticker, nome, cambio, prezzoOra, volume, etf, flipRef }: {
  ticker: string;
  nome: string | null;
  cambio: number;
  prezzoOra: number | null;
  /** Volume scambiato nel pre-market. Assente sui movers live, dove la
   *  spazzata porta solo prezzo e variazione. */
  volume?: number | null;
  etf?: boolean;
  /** Registro FLIP: la riga SCIVOLA alla nuova posizione quando il rango
   *  cambia, invece di teletrasportarsi. E' la stessa animazione della scheda
   *  Top movers piu' in basso — senza, con dieci righe che si riordinano ogni
   *  quindici secondi non si capisce chi ha superato chi. */
  flipRef?: (el: HTMLElement | null) => void;
}) {
  const sottile = volume != null && volume < VOLUME_SOTTILE;
  return (
    <Link
      ref={flipRef}
      to={`/stocks/${encodeURIComponent(ticker)}`}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 rounded px-1 py-0.5 hover:bg-accent/40"
      title={[
        nome ?? ticker,
        prezzoOra != null ? formatLivello(prezzoOra) : null,
        volume != null ? `${volume.toLocaleString("it-IT")} azioni scambiate nel pre-market` : null,
        etf ? "ETF: molti sono a leva o inversi, quindi si muovono per costruzione" : null,
      ].filter(Boolean).join(" · ")}
    >
      <span className="truncate text-sm">
        <span className="font-bold tabular-nums">{ticker}</span>
        {etf && (
          <span className="ml-1 rounded bg-muted px-1 text-[0.6471rem] font-bold uppercase tracking-wide text-muted-foreground">
            ETF
          </span>
        )}
        {nome && <span className="ml-1.5 text-muted-foreground">{nome}</span>}
      </span>
      <span className="flex shrink-0 items-baseline gap-2">
        {volume != null && (
          <span
            className={cn(
              "hidden text-[0.7059rem] tabular-nums lg:inline",
              sottile ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground",
            )}
            title={sottile ? "Scambi sottili: il prezzo lo fa un pugno di ordini" : undefined}
          >
            {fmtVolume(volume)}
          </span>
        )}
        {/* Il PREZZO accanto alla variazione, come nella scheda Top movers: un
            +9% su un titolo da 2 dollari e uno su un titolo da 400 non sono la
            stessa notizia, e senza il prezzo la riga non lo dice. */}
        {prezzoOra != null && (
          <span className="hidden w-[64px] text-right text-[0.7059rem] tabular-nums text-foreground/80 sm:inline">
            <FlashValue value={prezzoOra} format={(v) => formatLivello(v) ?? "—"} noTween />
          </span>
        )}
        <span className={cn("w-[66px] text-right text-sm font-semibold tabular-nums", tono(cambio))}>
          <FlashValue value={cambio} format={(v) => formatVariazione(v) ?? "—"} noTween />
        </span>
      </span>
    </Link>
  );
}

function Colonna({ titolo, icona: Icona, children }: {
  titolo: string;
  icona: typeof TrendingUp;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <div className="mb-0.5 flex items-center gap-1 text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">
        <Icona className="h-3 w-3" aria-hidden />
        {titolo}
      </div>
      {children}
    </div>
  );
}

/** Intestazione di una banda: il titolo e, accanto, da dove viene il dato.
 *  Senza la provenienza due liste sembrano la stessa cosa e non lo sono. */
function Intestazione({ titolo, fonte }: { titolo: string; fonte?: ReactNode }) {
  return (
    <div className="mb-1 flex flex-wrap items-baseline gap-x-2 text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">
      {titolo}
      {fonte && <span className="font-normal normal-case tracking-normal">{fonte}</span>}
    </div>
  );
}

/* ─── La fascia ─────────────────────────────────────────────────────────── */
export function MarketPulseJumbotron({ global, byIndex, computedAt, movers }: Props) {
  // Un battito al minuto: il conto alla rovescia si legge in minuti, e un
  // timer al secondo su una scheda sempre a schermo e' lavoro sprecato.
  const ora = useNowTick(60_000);
  /* Registro per l'animazione di rango delle righe «si muove adesso»: una
   * chiave per riga, con il PREFISSO della colonna — lo stesso titolo puo'
   * comparire in due liste diverse e due chiavi uguali farebbero scivolare la
   * riga sbagliata. */
  const registraFlip = useFlipList();
  const sessione = useMemo(() => usSessionClock(new Date(ora)), [ora]);

  const assetsQ = useLiveAssets();
  const assets = useMemo(() => assetsQ.data?.assets ?? [], [assetsQ.data]);
  const perSimbolo = useMemo(() => new Map(assets.map((a) => [a.symbol, a])), [assets]);

  /* ⚠️ La prova che la borsa e' chiusa quando l'orologio dice il contrario.
   * Il backend scambia il cash col future SOLO quando il cash non e' OPEN,
   * quindi tre americane tutte in `using_futures` durante la seduta significa
   * giorno di festa — e l'orologio, da solo, direbbe «aperta». */
  const americane = USA.map((s) => perSimbolo.get(s)).filter((a): a is LiveAsset => !!a);
  const tutteSuiFutures = americane.length > 0 && americane.every((a) => a.using_futures === true);
  const festivo = sessione.phase === "open" && tutteSuiFutures;
  const fase: UsPhase = festivo ? "closed" : sessione.phase;

  const preQ = usePremarketMovers();
  const pre = preQ.data;
  const liveQ = useLiveUniverseMovers(fase === "open");
  const liveMovers = liveQ.data;

  /* L'agenda del giorno. E' l'unica interrogazione NUOVA di questa fascia — le
   * altre tre le fanno gia' il nastro, i Top movers e il binario eventi — ed e'
   * una finestra di UN giorno solo, con cinque minuti di validita'. Il giorno
   * e' quello di New York: alle 01:00 italiane a Wall Street e' ancora ieri. */
  const giornoET = useMemo(() => etToday(new Date(ora)), [ora]);
  const calendarioQ = useCalendar({ from: giornoET, to: giornoET, kinds: ["macro", "earnings"] });
  const agenda = useMemo(
    () => agendaDelGiorno(calendarioQ.data?.events, giornoET),
    [calendarioQ.data, giornoET],
  );

  const badge: MarketPhase = fase === "open" ? "open" : fase === "pre" ? "pre" : "closed";
  const TITOLO: Record<UsPhase, string> = {
    pre: "Pre-market USA",
    open: "Wall Street aperta",
    after: "After hours USA",
    closed: festivo ? "Borsa USA chiusa — non e' un giorno di seduta" : "Mercati USA chiusi",
  };

  // L'ora di Roma accanto a quella di New York: l'utente guarda da qui, e la
  // distanza fra le due e' meta' del motivo per cui questa fascia esiste.
  const oraLocale = new Date(ora).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const frazioneVolume = fase === "open" ? cumulativeVolumeFraction(new Date(ora)) : null;
  const bordiFinestra = sessione.phase === "pre"
    ? ["04:00", "09:30"]
    : sessione.phase === "open"
      ? ["09:30", "16:00"]
      : ["16:00", "20:00"];

  /* Le quotazioni del paniere a leva. Stessa cadenza delle altre schede live
   * (15 s, cache di 10 s lato server), e la chiave della query e' la lista
   * ordinata: chi altro chiede gli stessi ticker condivide la risposta. */
  const levaQ = useLiveQuotes(ETF_LEVA as string[]);
  const perTicker = useMemo(() => {
    const m = new Map<string, LiveQuote>();
    for (const q of levaQ.data?.quotes ?? []) m.set(q.ticker, q);
    return m;
  }, [levaQ.data]);

  const vix = perSimbolo.get("^VIX");
  const vixValore = vix?.quote?.price ?? null;
  const contesto = assets.filter((a) => !USA.includes(a.symbol) && a.symbol !== "^VIX");
  const gruppi: [string, LiveAsset[]][] = [
    ["Indici", contesto.filter((a) => a.category === "index")],
    ["Materie prime", contesto.filter((a) => a.category === "commodity")],
    ["Cripto", contesto.filter((a) => a.category === "crypto")],
  ];

  /* I movers della SEDUTA, dall'istantanea: il ripiego sempre disponibile.
   * ⚠️ Tagliati alle stesse dieci righe delle altre due liste, cosi' il
   * riquadro non cambia altezza passando da una fonte all'altra — una fascia
   * che si allunga di duecento pixel quando apre Wall Street sposta tutto
   * quello che sta sotto. */
  const sedutaSu = (movers?.gainers ?? []).slice(0, RIGHE_MOVERS);
  const sedutaGiu = (movers?.losers ?? []).slice(0, RIGHE_MOVERS);

  const mostraPre = !!pre?.available && (pre.gainers.length > 0 || pre.losers.length > 0);
  const mostraLive =
    fase === "open" && !!liveMovers && (liveMovers.gainers.length > 0 || liveMovers.losers.length > 0);
  /* Gli ETF escono dalla lista principale e vanno in una riga loro: su otto
   * righe misurate a schermo, QUATTRO erano fondi a leva 3× — SOXL, SOXS,
   * SQQQ, EDZ — cioe' strumenti che si muovono di tre punti quando il
   * sottostante ne fa uno. Non e' una notizia, e' la loro definizione. */
  const equity = (righe: PremarketMover[]) => righe.filter((r) => r.instrument_type !== "etf");
  const fondi = (righe: PremarketMover[]) => righe.filter((r) => r.instrument_type === "etf");
  const etfInMovimento = pre
    ? [...fondi(pre.gainers), ...fondi(pre.losers)]
      .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
      .slice(0, 5)
    : [];

  return (
    <Card className="overflow-hidden bg-gradient-to-br from-slate-50 via-card to-card dark:from-slate-900/60 dark:via-card dark:to-card">
      <div className="flex flex-col gap-3 p-3 sm:p-4">
        {/* Fascia 1: la sessione a sinistra, le tre americane a destra. */}
        {/* 268px -> 330px: la colonna della sessione porta il titolo, due
            orologi, il conto alla rovescia grande, la barra della finestra, il
            volume tipico e il VIX, e li stava incastrando in meno di un quinto
            della fascia. I tre riquadri perdono ~60px in tre e non se ne
            accorgono: il loro contenuto e' numerico e corto. */}
        <div className="grid gap-3 dense-3:grid-cols-[minmax(0,330px)_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {/* Nessuna icona accanto al titolo: la pastiglia qui a fianco
                  porta gia' il suo glifo per la fase, e le due erano lo stesso
                  sole che sorge, due volte. */}
              <span className="text-lg font-bold tracking-tight sm:text-xl">{TITOLO[fase]}</span>
              <MarketStateBadge phase={badge} />
            </div>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
              <span className="tabular-nums" title="Ora di New York, cambi d'ora compresi">
                <Clock3 className="mr-1 inline h-3 w-3" aria-hidden />
                {sessione.etLabel} New York
              </span>
              <span className="tabular-nums">{oraLocale} qui</span>
            </div>
            {/* IL numero della colonna: quanto manca. Prima era della stessa
                taglia di tutto il resto, cioe' il soggetto della fascia pesava
                meno di un prezzo qualsiasi.
                ⚠️ E' TEORICO: le festivita' non sono modellate di proposito, e
                quando i dati lo smentiscono e' il titolo qui sopra a dirlo. */}
            <div className="mt-1.5">
              {sessione.minutesToNext != null ? (
                <>
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                    {sessione.nextLabel} fra
                  </div>
                  <div className="text-2xl font-bold leading-none tabular-nums">
                    {formatDelta(sessione.minutesToNext)}
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted-foreground">
                  {sessione.nextLabel}{" "}
                  <span className="font-semibold text-foreground">{sessione.nextDayLabel}</span>
                </div>
              )}
            </div>
            {sessione.progress != null && (
              <div className="mt-1.5">
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                  aria-hidden
                  title={`${Math.round(sessione.progress * 100)}% della finestra in corso`}
                >
                  <div
                    className={cn(
                      "h-full rounded-full",
                      fase === "pre" ? "bg-amber-500" : fase === "open" ? "bg-emerald-500" : "bg-slate-400",
                    )}
                    style={{ width: `${Math.round(sessione.progress * 100)}%` }}
                  />
                </div>
                {/* Una barra senza estremi non dice fra cosa e cosa. */}
                <div className="mt-0.5 flex justify-between text-[0.6471rem] tabular-nums leading-none text-muted-foreground">
                  <span>{bordiFinestra[0]}</span>
                  <span>{bordiFinestra[1]} New York</span>
                </div>
              </div>
            )}
            <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              {frazioneVolume != null && (
                <span title="Quota del volume di una giornata tipica gia' scambiata a quest'ora, dalla stessa curva intraday che proietta i volumi delle schede sotto">
                  volume tipico già scambiato ≈{" "}
                  <span className="font-semibold tabular-nums text-foreground">
                    {Math.round(frazioneVolume * 100)}%
                  </span>
                </span>
              )}
              {vix && (
                /* ⚠️ Il VIX resta NEUTRO di proposito: in questa app rosa e
                 * verde dicono la direzione di un PREZZO, e un VIX in rialzo
                 * colorato di verde si leggerebbe come «bene» mentre significa
                 * che il mercato si sta coprendo. */
                <span title="VIX — volatilita' attesa a 30 giorni sull'S&P 500. Sotto 15 calmo, 15-20 normale, 20-30 teso, sopra 30 stress. Sale quando il mercato compra protezione.">
                  VIX{" "}
                  <span className="font-semibold tabular-nums text-foreground">
                    {formatLivello(vixValore) ?? <NoValue hint={perche(vix, "VIX")} />}
                  </span>
                  {formatVariazione(vix.quote?.change_pct) && (
                    <span className="ml-1 tabular-nums">{formatVariazione(vix.quote?.change_pct)}</span>
                  )}
                  {vixValore != null && (
                    <span className="ml-1 rounded bg-muted px-1 text-[0.6471rem] font-semibold">
                      {bandaVix(vixValore)}
                    </span>
                  )}
                </span>
              )}
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-3 gap-2">
            {USA.map((s) => (
              <IndiceTile
                key={s}
                asset={perSimbolo.get(s)}
                nome={NOMI_BREVI[s]}
                ampiezza={(byIndex ?? []).find((i) => i.code === CODICE_AMPIEZZA[s])}
              />
            ))}
          </div>
        </div>

        {/* Fascia 2: il resto del mondo, raggruppato. Prima era una fila
            indistinta di undici voci: indici, metalli, energia e cripto tutti
            della stessa taglia e senza un confine.
            ⚠️ La riga si rende SEMPRE, non solo quando il paniere live ha
            risposto: il gruppo a leva viene da un'altra interrogazione
            (`/api/stocks/quotes`), e legarlo alla presenza degli indici lo
            faceva sparire insieme a loro quando quella query taceva. */}
        {(
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 border-t pt-2">
            {gruppi.map(([titolo, voci]) =>
              voci.length === 0 ? null : (
                /* `gap-x-3` dentro il gruppo e `gap-x-5` fra i gruppi: prima
                   erano rispettivamente 1 e 3, e undici voci attaccate si
                   leggevano come una sola stringa lunga. */
                /* ⚠️ Niente separatore verticale fra i gruppi. Ce n'era uno
                   davanti a ogni gruppo tranne il primo, e quando la riga
                   andava A CAPO il gruppo che apriva la riga nuova se lo
                   portava dietro: «CRIPTO» partiva qualche pixel piu' a destra
                   di «INDICI», per un tratto che li' non separava niente. Il
                   CSS non sa dove cade il ritorno a capo, quindi l'unica forma
                   che regge e' non averlo — lo spazio fra i gruppi lo fa
                   `gap-x-6`, che e' il doppio di quello interno. */
                <span key={titolo} className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground/70">
                    {titolo}
                  </span>
                  {voci.map((a) => (
                    <Chip key={a.symbol} asset={a} />
                  ))}
                </span>
              ),
            )}
            {/* Il paniere a leva, in coda alle materie prime e alle cripto:
                e' l'ultimo gruppo perche' e' il piu' specialistico, non il
                meno importante. */}
            <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <span className="flex items-center gap-1 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground/70">
                <Zap className="h-3 w-3" aria-hidden />
                Leva
              </span>
              {ETF_LEVA.map((t) => (
                <ChipLeva key={t} ticker={t} quote={perTicker.get(t)} />
              ))}
            </span>
          </div>
        )}

        {/* Fascia 3: che cosa esce oggi. In pre-market e' la domanda che viene
            subito dopo «dove sono i futures», e un dato macro alle 08:30 di New
            York muove l'apertura piu' di qualunque movimento di stanotte. */}
        {!agendaVuota(agenda) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 text-sm">
            <span className="flex shrink-0 items-center gap-1 text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">
              <CalendarClock className="h-3.5 w-3.5" aria-hidden />
              Oggi
            </span>
            {agenda.macro.slice(0, 4).map((m) => (
              <span key={`${m.etichetta}-${m.oraET}`} className="flex min-w-0 items-baseline gap-1">
                {m.oraET ? (
                  <span className="shrink-0 font-semibold tabular-nums">{m.oraET}</span>
                ) : (
                  <span className="shrink-0 text-muted-foreground" title="Orario di rilascio non pubblicato">
                    ora n/d
                  </span>
                )}
                <span
                  className={cn(
                    "truncate",
                    m.importanza === "high" ? "font-semibold text-foreground" : "text-muted-foreground",
                  )}
                  title={`${m.etichetta} · ${m.regione} · importanza ${m.importanza}`}
                >
                  {m.etichetta}
                </span>
              </span>
            ))}
            {agenda.primaDellApertura.length > 0 && (
              <span className="min-w-0 text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {agenda.primaDellApertura.length}
                </span>{" "}
                trimestrali prima dell'apertura
                <span className="ml-1">
                  ({agenda.primaDellApertura.slice(0, 3).map((e) => e.ticker).join(", ")}
                  {agenda.primaDellApertura.length > 3 ? "…" : ""})
                </span>
              </span>
            )}
            {agenda.dopoLaChiusura.length > 0 && (
              <span className="text-muted-foreground">
                <span className="font-semibold text-foreground">{agenda.dopoLaChiusura.length}</span>{" "}
                dopo la chiusura
              </span>
            )}
            <Link
              to="/calendar"
              className="ml-auto shrink-0 text-[0.6765rem] text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              calendario
            </Link>
          </div>
        )}

        {/* Fascia 4: chi si muove adesso, e l'ampiezza in cui leggerlo. */}
        <div className="grid gap-3 border-t pt-2 md:grid-cols-2">
          <div className="min-w-0">
            <Intestazione
              /* ⚠️ Il titolo segue CIO' CHE C'E' SOTTO, e l'ultimo ramo non
                 e' una ripetizione: senza, il riquadro annunciava «Top della
                 seduta» sopra un messaggio che dice che l'istantanea non e'
                 ancora arrivata — un'intestazione che promette righe che non
                 esistono. Trovato da un test, non a occhio. */
              titolo={
                mostraPre
                  ? "Si muove nel pre-market"
                  : mostraLive && liveMovers
                    ? "Si muove adesso"
                    : sedutaSu.length > 0 || sedutaGiu.length > 0
                      ? "Top della seduta"
                      : "Si muove adesso"
              }
              fonte={
                mostraPre && pre?.as_of
                  ? `seduta ${pre.as_of}`
                  : mostraLive && liveMovers
                    ? `su ${liveMovers.swept} titoli con quotazione fresca`
                    : sedutaSu.length > 0
                      ? "ultima chiusura dell'istantanea"
                      : null
              }
            />
            {mostraPre && pre ? (
              <>
                <div className="grid gap-x-4 gap-y-1 xl:grid-cols-2">
                  <Colonna titolo="Su" icona={TrendingUp}>
                    {equity(pre.gainers).slice(0, RIGHE_MOVERS).map((m) => (
                      <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                        prezzoOra={m.price} volume={m.volume}
                        flipRef={registraFlip(`pre-su:${m.ticker}`)} />
                    ))}
                  </Colonna>
                  <Colonna titolo="Giù" icona={TrendingDown}>
                    {equity(pre.losers).slice(0, RIGHE_MOVERS).map((m) => (
                      <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                        prezzoOra={m.price} volume={m.volume}
                        flipRef={registraFlip(`pre-giu:${m.ticker}`)} />
                    ))}
                  </Colonna>
                </div>
                {etfInMovimento.length > 0 && (
                  <div className="mt-1 border-t pt-1">
                    <div
                      className="text-[0.6471rem] font-bold uppercase tracking-[0.14em] text-muted-foreground"
                      title="Molti di questi fondi sono a leva o inversi: si muovono di piu' del mercato per costruzione, non perche' stia succedendo qualcosa di loro"
                    >
                      ETF
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                      {etfInMovimento.map((m) => (
                        <Link
                          key={m.ticker}
                          to={`/stocks/${encodeURIComponent(m.ticker)}`}
                          className="inline-flex items-baseline gap-1 rounded px-1 text-xs hover:bg-accent/40"
                          title={m.name ?? m.ticker}
                        >
                          <span className="font-bold tabular-nums">{m.ticker}</span>
                          <span className={cn("font-semibold tabular-nums", tono(m.change_pct))}>
                            {formatVariazione(m.change_pct)}
                          </span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : mostraLive && liveMovers ? (
              <div className="grid gap-x-4 gap-y-1 xl:grid-cols-2">
                <Colonna titolo="Su" icona={TrendingUp}>
                  {liveMovers.gainers.slice(0, RIGHE_MOVERS).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} flipRef={registraFlip(`live-su:${m.ticker}`)} />
                  ))}
                </Colonna>
                <Colonna titolo="Giù" icona={TrendingDown}>
                  {liveMovers.losers.slice(0, RIGHE_MOVERS).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} flipRef={registraFlip(`live-giu:${m.ticker}`)} />
                  ))}
                </Colonna>
              </div>
            ) : sedutaSu.length > 0 || sedutaGiu.length > 0 ? (
              /* ⚠️ Il ripiego che rende questo riquadro utile per la maggior
                 parte della giornata italiana. Prima, fuori dalla finestra del
                 pre-market, diceva «niente da mostrare in tempo reale» — vero
                 e inutile: i movers della SEDUTA erano nell'istantanea che la
                 pagina aveva gia' scaricato, due schede piu' in basso.

                 La fonte lo dichiara («ultima chiusura dell'istantanea»),
                 perche' un dato di chiusura accanto a numeri che battono ogni
                 quindici secondi si legge come live se nessuno dice che non
                 lo e'. */
              <div className="grid gap-x-4 gap-y-1 xl:grid-cols-2">
                <Colonna titolo="Su" icona={TrendingUp}>
                  {sedutaSu.map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name}
                      cambio={m.change_pct ?? 0} prezzoOra={m.last_close}
                      flipRef={registraFlip(`seduta-su:${m.ticker}`)} />
                  ))}
                </Colonna>
                <Colonna titolo="Giù" icona={TrendingDown}>
                  {sedutaGiu.map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name}
                      cambio={m.change_pct ?? 0} prezzoOra={m.last_close}
                      flipRef={registraFlip(`seduta-giu:${m.ticker}`)} />
                  ))}
                </Colonna>
              </div>
            ) : (
              /* PERCHE' non c'e' niente. «Nessun dato» manda a cercare un
                 guasto che non esiste: il pre-market si calcola solo nella sua
                 finestra, e a mercato aperto la spazzata live parte vuota. */
              <div className="text-xs text-muted-foreground">
                {pre?.refreshing
                  ? `Pre-market in aggiornamento — ${pre.progress_pct}%`
                  : fase === "open"
                    ? "Nessuna quotazione fresca ancora: la spazzata live ruota sull'universo e si popola nei primi minuti."
                    : "L'istantanea dei movers non è ancora arrivata: compaiono dopo la prima scansione."}
              </div>
            )}
          </div>

          {global ? (
            <MarketBreadthBand global={global} byIndex={byIndex ?? []} computedAt={computedAt} />
          ) : (
            <div className="min-w-0 text-xs text-muted-foreground">
              Ampiezza del catalogo: istantanea non ancora arrivata.
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
