import { CalendarClock, Clock3, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import type { PremarketMover } from "@/api/dashboard";
import { MarketBreadthBand } from "@/components/dashboard/MarketBreadthBand";
import { MarketStateBadge, type MarketPhase } from "@/components/dashboard/MarketStateBadge";
import { Card } from "@/components/ui/card";
import { NoValue } from "@/components/ui/no-value";
import { useCalendar } from "@/hooks/useCalendar";
import { useLiveAssets, type LiveAsset } from "@/hooks/useLiveAssets";
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
  /** `computed_at` dell'istantanea — l'eta' dell'ampiezza, dichiarata. */
  computedAt?: string | null;
}

/* I tre simboli della seduta americana, nell'ordine in cui si leggono. Sono le
 * chiavi di `LIVE_ASSET_DEFINITIONS` nel backend; il resto del paniere finisce
 * nella riga di contesto. */
const USA: readonly string[] = ["^GSPC", "^IXIC", "^DJI"];

/** I nomi lunghi non entrano in un riquadro da 110px su un telefono, e
 *  troncati perdono proprio la parte che li distingue. */
const NOMI_BREVI: Record<string, string> = {
  "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones", "^VIX": "VIX",
  "^N225": "Nikkei", "^STOXX50E": "Stoxx 50", "FTSEMIB.MI": "FTSE MIB",
  "^HSI": "Hang Seng", "000300.SS": "CSI 300", "GC=F": "Oro", "SI=F": "Argento",
  "CL=F": "WTI", "NG=F": "Gas", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum",
};

/** Le bandiere che esistono davvero in `public/flags/`. Una `<img>` verso un
 *  file assente lascia l'icona rotta a schermo: si rende solo cio' che c'e'. */
const BANDIERE = new Set(["us", "jp", "eu", "it", "hk", "cn", "gb", "de", "fr", "kr", "tw", "ca"]);

/** Sotto questo volume nel pre-market un movimento e' un singolo scambio, non
 *  un prezzo. Non si NASCONDE la riga — si dice che gli scambi sono sottili,
 *  cosi' il lettore giudica il +6% invece di riceverlo come un fatto. */
const VOLUME_SOTTILE = 10_000;

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

/* ─── Il riquadro grande di un indice americano ──────────────────────────── */
function IndiceTile({ asset, nome }: { asset: LiveAsset | undefined; nome: string }) {
  const q = asset?.quote;
  const cambio = q?.change_pct ?? null;
  const punti = sparklinePoints(asset?.history, 120, 26, 2);
  const live = asset?.is_live === true;
  const suFutures = asset?.using_futures === true;
  const posizione = posizioneNelRange(q?.price, q?.day_low, q?.day_high);
  const corpo = (
    <>
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-[0.7059rem] font-semibold uppercase tracking-wider text-muted-foreground">
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
        <span className="truncate text-lg font-bold tabular-nums leading-none sm:text-xl">
          {formatLivello(q?.price) ?? <NoValue hint={perche(asset, nome)} />}
        </span>
        <span className={cn("shrink-0 text-sm font-semibold tabular-nums", tono(cambio))}>
          {formatVariazione(cambio) ?? <NoValue hint={perche(asset, nome)} />}
        </span>
      </div>
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
        <div className="mt-1 hidden lg:block">
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
      {bandiera && (
        <img
          src={bandiera}
          alt=""
          width={14}
          height={10}
          style={{ width: "14px", height: "10px", objectFit: "cover" }}
          className="shrink-0 rounded-[1px] shadow-sm"
        />
      )}
      <span className="text-[0.7059rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {nome}
      </span>
      {/* Il pallino «aperto adesso» e' decorativo: il titolo del collegamento
          dice gia' a parole se il mercato e' aperto. Tredici pallini che
          pulsano sarebbero rumore, quindi questo sta fermo. */}
      {asset.is_live && (
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" aria-hidden />
      )}
      <span className="text-xs font-semibold tabular-nums">
        {formatLivello(asset.quote?.price) ?? <NoValue hint={perche(asset, nome)} />}
      </span>
      <span
        className={cn(
          "text-xs tabular-nums",
          forte ? "font-bold" : "font-semibold",
          tono(cambio),
        )}
      >
        {formatVariazione(cambio) ?? ""}
      </span>
    </Link>
  );
}

/* ─── Una riga della classifica «si muove adesso» ────────────────────────── */
function RigaMover({ ticker, nome, cambio, prezzoOra, volume, etf }: {
  ticker: string;
  nome: string | null;
  cambio: number;
  prezzoOra: number | null;
  /** Volume scambiato nel pre-market. Assente sui movers live, dove la
   *  spazzata porta solo prezzo e variazione. */
  volume?: number | null;
  etf?: boolean;
}) {
  const sottile = volume != null && volume < VOLUME_SOTTILE;
  return (
    <Link
      to={`/stocks/${encodeURIComponent(ticker)}`}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 rounded px-1 py-0.5 hover:bg-accent/40"
      title={[
        nome ?? ticker,
        prezzoOra != null ? formatLivello(prezzoOra) : null,
        volume != null ? `${volume.toLocaleString("it-IT")} azioni scambiate nel pre-market` : null,
        etf ? "ETF: molti sono a leva o inversi, quindi si muovono per costruzione" : null,
      ].filter(Boolean).join(" · ")}
    >
      <span className="truncate text-xs">
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
              "text-[0.6765rem] tabular-nums",
              sottile ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground",
            )}
            title={sottile ? "Scambi sottili: il prezzo lo fa un pugno di ordini" : undefined}
          >
            {fmtVolume(volume)}
          </span>
        )}
        <span className={cn("w-[62px] text-right text-xs font-semibold tabular-nums", tono(cambio))}>
          {formatVariazione(cambio)}
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
      <div className="mb-0.5 flex items-center gap-1 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
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
    <div className="mb-1 flex flex-wrap items-baseline gap-x-2 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
      {titolo}
      {fonte && <span className="font-normal normal-case tracking-normal">{fonte}</span>}
    </div>
  );
}

/* ─── La fascia ─────────────────────────────────────────────────────────── */
export function MarketPulseJumbotron({ global, byIndex, computedAt }: Props) {
  // Un battito al minuto: il conto alla rovescia si legge in minuti, e un
  // timer al secondo su una scheda sempre a schermo e' lavoro sprecato.
  const ora = useNowTick(60_000);
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

  const vix = perSimbolo.get("^VIX");
  const vixValore = vix?.quote?.price ?? null;
  const contesto = assets.filter((a) => !USA.includes(a.symbol) && a.symbol !== "^VIX");
  const gruppi: [string, LiveAsset[]][] = [
    ["Indici", contesto.filter((a) => a.category === "index")],
    ["Materie prime", contesto.filter((a) => a.category === "commodity")],
    ["Cripto", contesto.filter((a) => a.category === "crypto")],
  ];

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
        <div className="grid gap-3 dense-3:grid-cols-[minmax(0,268px)_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {/* Nessuna icona accanto al titolo: la pastiglia qui a fianco
                  porta gia' il suo glifo per la fase, e le due erano lo stesso
                  sole che sorge, due volte. */}
              <span className="text-base font-bold tracking-tight sm:text-lg">{TITOLO[fase]}</span>
              <MarketStateBadge phase={badge} />
            </div>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
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
                  <div className="text-[0.6765rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
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
            <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[0.7059rem] text-muted-foreground">
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
              <IndiceTile key={s} asset={perSimbolo.get(s)} nome={NOMI_BREVI[s]} />
            ))}
          </div>
        </div>

        {/* Fascia 2: il resto del mondo, raggruppato. Prima era una fila
            indistinta di undici voci: indici, metalli, energia e cripto tutti
            della stessa taglia e senza un confine. */}
        {contesto.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2">
            {gruppi.map(([titolo, voci], i) =>
              voci.length === 0 ? null : (
                <span key={titolo} className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-1">
                  {i > 0 && <span className="mr-1 hidden h-4 w-px bg-border lg:block" aria-hidden />}
                  <span className="mr-0.5 text-[0.6471rem] font-bold uppercase tracking-[0.14em] text-muted-foreground/70">
                    {titolo}
                  </span>
                  {voci.map((a) => (
                    <Chip key={a.symbol} asset={a} />
                  ))}
                </span>
              ),
            )}
          </div>
        )}

        {/* Fascia 3: che cosa esce oggi. In pre-market e' la domanda che viene
            subito dopo «dove sono i futures», e un dato macro alle 08:30 di New
            York muove l'apertura piu' di qualunque movimento di stanotte. */}
        {!agendaVuota(agenda) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 text-xs">
            <span className="flex shrink-0 items-center gap-1 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              <CalendarClock className="h-3 w-3" aria-hidden />
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
              titolo={mostraPre ? "Si muove nel pre-market" : "Si muove adesso"}
              fonte={
                mostraPre && pre?.as_of
                  ? `seduta ${pre.as_of}`
                  : mostraLive && liveMovers
                    ? `su ${liveMovers.swept} titoli con quotazione fresca`
                    : null
              }
            />
            {mostraPre && pre ? (
              <>
                <div className="grid gap-x-4 gap-y-1 xl:grid-cols-2">
                  <Colonna titolo="Su" icona={TrendingUp}>
                    {equity(pre.gainers).slice(0, 4).map((m) => (
                      <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                        prezzoOra={m.price} volume={m.volume} />
                    ))}
                  </Colonna>
                  <Colonna titolo="Giù" icona={TrendingDown}>
                    {equity(pre.losers).slice(0, 4).map((m) => (
                      <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                        prezzoOra={m.price} volume={m.volume} />
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
                  {liveMovers.gainers.slice(0, 4).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} />
                  ))}
                </Colonna>
                <Colonna titolo="Giù" icona={TrendingDown}>
                  {liveMovers.losers.slice(0, 4).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} />
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
                    : fase === "pre"
                      ? "Il pre-market si popola dalle 04:00 di New York; l'ultimo calcolo non è ancora arrivato."
                      : "Fuori dalla finestra del pre-market: niente da mostrare in tempo reale."}
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
