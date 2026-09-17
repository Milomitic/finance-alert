import { Activity, Clock3, Flame, Snowflake, Sunrise, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { MarketGlobal } from "@/api/types";
import { MarketStateBadge, type MarketPhase } from "@/components/dashboard/MarketStateBadge";
import { Card } from "@/components/ui/card";
import { NoValue } from "@/components/ui/no-value";
import { useLiveAssets, type LiveAsset } from "@/hooks/useLiveAssets";
import { useLiveUniverseMovers } from "@/hooks/useLiveUniverseMovers";
import { useNowTick } from "@/hooks/useNowTick";
import { usePremarketMovers } from "@/hooks/usePremarketMovers";
import { cumulativeVolumeFraction } from "@/lib/intradayVolume";
import { sparklinePoints } from "@/lib/sparkline";
import { formatDelta, usSessionClock, type UsPhase } from "@/lib/usSession";
import { cn } from "@/lib/utils";
import { fmtVolume } from "@/lib/volumeFormat";

/* ─── MarketPulseJumbotron — PROTOTIPO ────────────────────────────────────── *
 *
 * La fascia in cima al cruscotto: dove sono i mercati ADESSO, con il
 * pre-market e la seduta americana come soggetto invece che come una delle
 * tante schede. Tutto quello che mostra arriva da interrogazioni che la pagina
 * fa GIA' — `live-assets` e' la stessa del nastro scorrevole, `live-movers`
 * quella dei Top movers, `premarket-movers` quella del binario eventi — e
 * TanStack le condivide per chiave: nessuna richiesta in piu'.
 *
 * Tre cose che sembrano dettagli e sono la ragione per cui questa scheda non
 * mente:
 *
 * 1. **La fase la dicono i dati, non l'orologio.** L'orologio sa che sono le
 *    11:00 di New York; non sa che e' il Giorno del Ringraziamento. Ma il
 *    backend scambia il prezzo dell'indice con quello del future quando il
 *    cash NON e' aperto (`using_futures`), quindi tre americane tutte sui
 *    futures a mercato teoricamente aperto SONO la prova che la borsa e'
 *    chiusa. Nessun calendario scritto a mano lo saprebbe, e una lista di
 *    festivita' invecchia in silenzio esattamente quando conta.
 * 2. **Un prezzo da future non si presenta come il cash.** Ogni riquadro porta
 *    il suo contrassegno FUT, che nel pre-market e' l'informazione piu' utile
 *    che ci sia: prima delle 09:30 il livello dell'indice e' fermo a ieri e
 *    quello che si muove e' il contratto.
 * 3. **L'ampiezza e' un'ISTANTANEA, non un dato live**, e lo dichiara con
 *    l'ora della scansione. Metterla accanto a numeri che battono ogni 15 s e'
 *    esattamente il modo in cui un numero vecchio si legge come nuovo.
 */

interface Props {
  /** Ampiezza dell'ultima scansione. Assente finche' l'istantanea non e'
   *  arrivata: la fascia della sessione vive lo stesso, perche' non dipende da
   *  nessuna interrogazione. */
  global?: MarketGlobal;
  /** `computed_at` dell'istantanea — l'eta' dell'ampiezza, dichiarata. */
  computedAt?: string | null;
}

/* I tre simboli della seduta americana, nell'ordine in cui si leggono. Sono le
 * chiavi di `LIVE_ASSET_DEFINITIONS` nel backend; il resto del paniere
 * (Europa, Asia, materie prime, cripto) finisce nella riga di contesto. */
const USA: readonly string[] = ["^GSPC", "^IXIC", "^DJI"];

/** I nomi lunghi non entrano in un riquadro da 110px su un telefono, e
 *  troncati perdono proprio la parte che li distingue. */
const NOMI_BREVI: Record<string, string> = {
  "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones", "^VIX": "VIX",
  "^N225": "Nikkei", "^STOXX50E": "Stoxx 50", "FTSEMIB.MI": "FTSE MIB",
  "^HSI": "Hang Seng", "000300.SS": "CSI 300", "GC=F": "Oro", "SI=F": "Argento",
  "CL=F": "WTI", "NG=F": "Gas", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum",
};

function nomeBreve(a: LiveAsset): string {
  return NOMI_BREVI[a.symbol] ?? a.name;
}

function tono(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-800 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

function pct(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function prezzo(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  if (abs >= 1) return v.toFixed(2);
  return v.toFixed(4);
}

/** Perche' un numero non c'e'. L'errore della fonte quando esiste, altrimenti
 *  la verita' piu' semplice: non e' ancora arrivato. Un trattino muto manda a
 *  cercare un guasto; questo dice dove guardare. */
function perche(a: LiveAsset | undefined, nome: string): string {
  if (!a) return `${nome}: simbolo non presente nel paniere live`;
  if (a.quote?.error) return `${nome}: quotazione non disponibile (${a.quote.error})`;
  return `${nome}: quotazione non ancora ricevuta`;
}

/* ─── Il riquadro grande di un indice americano ──────────────────────────── */
function IndiceTile({ asset, nome }: { asset: LiveAsset | undefined; nome: string }) {
  const q = asset?.quote;
  const cambio = q?.change_pct ?? null;
  const punti = sparklinePoints(asset?.history, 120, 26, 2);
  const live = asset?.is_live === true;
  const corpo = (
    <>
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="truncate text-[0.7059rem] font-semibold uppercase tracking-wider text-muted-foreground">
          {nome}
        </span>
        {asset?.using_futures ? (
          <span
            className="shrink-0 rounded bg-amber-100 px-1 text-[0.6471rem] font-bold uppercase tracking-wider text-amber-800 dark:bg-amber-900/60 dark:text-amber-200"
            title="Cash chiuso — il prezzo viene dal contratto futures, che e' quello che si muove prima dell'apertura"
          >
            FUT
          </span>
        ) : live ? (
          /* ⚠️ `role="img"` non e' decorazione: un `aria-label` su uno span
             senza ruolo e' un attributo PROIBITO per axe (`aria-prohibited-attr`,
             lo stesso rilievo che /calendar porta in linea di base). Le due
             schede movers hanno la stessa forma e oggi passano solo perche' il
             gate gira senza rete e il pallino non viene mai reso. */
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
          significherebbe tagliare proprio la cifra. Si impilano sotto `sm` e
          tornano in riga dove c'e' spazio. */}
      <div className="mt-0.5 flex min-w-0 flex-col sm:flex-row sm:items-baseline sm:gap-2">
        <span className="truncate text-lg font-bold tabular-nums leading-none sm:text-xl">
          {prezzo(q?.price) ?? <NoValue hint={perche(asset, nome)} />}
        </span>
        <span className={cn("shrink-0 text-sm font-semibold tabular-nums", tono(cambio))}>
          {pct(cambio) ?? <NoValue hint={perche(asset, nome)} />}
        </span>
      </div>
      {/* Il tracciato e' decorativo: la variazione qui sopra e' gia' il numero,
          e una polilinea non ha niente da annunciare a chi non la vede. */}
      {punti && (
        <svg
          viewBox="0 0 120 26"
          preserveAspectRatio="none"
          className="mt-1 hidden h-[26px] w-full sm:block"
          aria-hidden
        >
          <polyline
            points={punti}
            fill="none"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
            className={cambio != null && cambio < 0 ? "stroke-rose-500" : "stroke-emerald-500"}
          />
        </svg>
      )}
      {q?.day_low != null && q?.day_high != null && (
        <div className="mt-0.5 hidden text-[0.6765rem] tabular-nums text-muted-foreground lg:block">
          {prezzo(q.day_low)} – {prezzo(q.day_high)}
          <span className="ml-1 opacity-70">giornata</span>
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
  return (
    <Link
      to={`/markets/${encodeURIComponent(asset.symbol)}`}
      className="inline-flex min-w-0 items-baseline gap-1.5 rounded px-1 py-0.5 hover:bg-accent/40"
      title={`${asset.name}${asset.using_futures ? " · prezzo dal future" : ""} — apri il dettaglio`}
    >
      <span className="text-[0.7059rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {nome}
      </span>
      <span className="text-xs font-semibold tabular-nums">
        {prezzo(asset.quote?.price) ?? <NoValue hint={perche(asset, nome)} />}
      </span>
      <span className={cn("text-xs font-semibold tabular-nums", tono(cambio))}>
        {pct(cambio) ?? ""}
      </span>
    </Link>
  );
}

/* ─── Una riga della classifica «si muove adesso» ────────────────────────── */
function RigaMover({
  ticker, nome, cambio, prezzoOra, volume,
}: {
  ticker: string;
  nome: string | null;
  cambio: number;
  prezzoOra: number | null;
  /** Volume scambiato nel pre-market. Assente sui movers live, dove la
   *  spazzata porta solo prezzo e variazione. */
  volume?: number | null;
}) {
  return (
    <Link
      to={`/stocks/${encodeURIComponent(ticker)}`}
      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 rounded px-1 py-0.5 hover:bg-accent/40"
      title={[
        nome ?? ticker,
        prezzoOra != null ? prezzo(prezzoOra) : null,
        volume != null ? `${volume.toLocaleString("it-IT")} share` : null,
      ].filter(Boolean).join(" · ")}
    >
      <span className="truncate text-xs">
        <span className="font-bold tabular-nums">{ticker}</span>
        {nome && <span className="ml-1.5 text-muted-foreground">{nome}</span>}
      </span>
      <span className="flex shrink-0 items-baseline gap-2">
        {volume != null && (
          <span className="hidden text-[0.6765rem] tabular-nums text-muted-foreground lg:inline">
            {fmtVolume(volume)}
          </span>
        )}
        <span className={cn("w-[58px] text-right text-xs font-semibold tabular-nums", tono(cambio))}>
          {pct(cambio)}
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

/** Intestazione di una delle due colonne basse: il titolo e, accanto, da dove
 *  viene il dato. Senza la provenienza sono due liste che sembrano la stessa
 *  cosa e non lo sono. */
function Intestazione({ titolo, fonte }: { titolo: string; fonte?: string | null }) {
  return (
    <div className="mb-1 flex flex-wrap items-baseline gap-x-2 text-[0.6765rem] font-bold uppercase tracking-[0.14em] text-muted-foreground">
      {titolo}
      {fonte && <span className="font-normal normal-case tracking-normal">{fonte}</span>}
    </div>
  );
}

/* ─── La fascia ─────────────────────────────────────────────────────────── */
export function MarketPulseJumbotron({ global, computedAt }: Props) {
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

  const badge: MarketPhase = fase === "open" ? "open" : fase === "pre" ? "pre" : "closed";
  const TITOLO: Record<UsPhase, string> = {
    pre: "Pre-market USA",
    open: "Wall Street aperta",
    after: "After hours USA",
    closed: festivo ? "Borsa USA chiusa — non e' un giorno di seduta" : "Mercati USA chiusi",
  };
  const Icona = { pre: Sunrise, open: Flame, after: Activity, closed: Snowflake }[fase];

  // L'ora di Roma accanto a quella di New York: l'utente guarda da qui, e la
  // distanza fra le due e' meta' del motivo per cui questa fascia esiste.
  const oraLocale = new Date(ora).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const frazioneVolume = fase === "open" ? cumulativeVolumeFraction(new Date(ora)) : null;

  const vix = perSimbolo.get("^VIX");
  const contesto = assets.filter((a) => !USA.includes(a.symbol) && a.symbol !== "^VIX");

  const mostraPre = !!pre?.available && (pre.gainers.length > 0 || pre.losers.length > 0);
  const mostraLive =
    fase === "open" && !!liveMovers && (liveMovers.gainers.length > 0 || liveMovers.losers.length > 0);

  return (
    <Card className="overflow-hidden bg-gradient-to-br from-slate-50 via-card to-card dark:from-slate-900/60 dark:via-card dark:to-card">
      <div className="flex flex-col gap-3 p-3 sm:p-4">
        {/* Fascia 1: la sessione a sinistra, le tre americane a destra. */}
        <div className="grid gap-3 dense-3:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <Icona className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="text-base font-bold tracking-tight sm:text-lg">{TITOLO[fase]}</span>
              <MarketStateBadge phase={badge} />
            </div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              <span className="tabular-nums" title="Ora di New York, cambi d'ora compresi">
                <Clock3 className="mr-1 inline h-3 w-3" aria-hidden />
                {sessione.etLabel} New York
              </span>
              <span className="tabular-nums">{oraLocale} qui</span>
            </div>
            {/* Il conto alla rovescia. ⚠️ E' TEORICO: le festivita' non sono
                modellate di proposito, e quando i dati lo smentiscono e' il
                titolo qui sopra a dirlo — non questa riga. */}
            <div className="mt-1.5 text-sm">
              {sessione.minutesToNext != null ? (
                <span>
                  <span className="text-muted-foreground">{sessione.nextLabel} fra </span>
                  <span className="font-bold tabular-nums">{formatDelta(sessione.minutesToNext)}</span>
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {sessione.nextLabel}{" "}
                  <span className="font-semibold text-foreground">{sessione.nextDayLabel}</span>
                </span>
              )}
            </div>
            {sessione.progress != null && (
              <div
                className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted"
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
            )}
            <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[0.7059rem] text-muted-foreground">
              {frazioneVolume != null && (
                <span title="Quota del volume di una giornata tipica gia' scambiata a quest'ora, dalla stessa curva intraday che proietta i volumi delle schede sotto">
                  volume tipico gia' scambiato ≈{" "}
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
                <span title="VIX — volatilita' attesa a 30 giorni sull'S&P 500. Sale quando il mercato compra protezione.">
                  VIX{" "}
                  <span className="font-semibold tabular-nums text-foreground">
                    {prezzo(vix.quote?.price) ?? <NoValue hint={perche(vix, "VIX")} />}
                  </span>
                  {pct(vix.quote?.change_pct) && (
                    <span className="ml-1 tabular-nums">{pct(vix.quote?.change_pct)}</span>
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

        {/* Fascia 2: il resto del mondo, in una riga che va a capo. */}
        {contesto.length > 0 && (
          <div className="flex flex-wrap items-baseline gap-x-1 gap-y-0.5 border-t pt-2">
            {contesto.map((a) => (
              <Chip key={a.symbol} asset={a} />
            ))}
          </div>
        )}

        {/* Fascia 3: chi si muove adesso, e l'ampiezza in cui leggerlo. */}
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
              <div className="grid gap-x-4 gap-y-1 xl:grid-cols-2">
                <Colonna titolo="Su" icona={TrendingUp}>
                  {pre.gainers.slice(0, 4).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} volume={m.volume} />
                  ))}
                </Colonna>
                <Colonna titolo="Giù" icona={TrendingDown}>
                  {pre.losers.slice(0, 4).map((m) => (
                    <RigaMover key={m.ticker} ticker={m.ticker} nome={m.name} cambio={m.change_pct}
                      prezzoOra={m.price} volume={m.volume} />
                  ))}
                </Colonna>
              </div>
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
                      ? "Il pre-market si popola dalle 04:00 di New York; l'ultimo calcolo non e' ancora arrivato."
                      : "Fuori dalla finestra del pre-market: niente da mostrare in tempo reale."}
              </div>
            )}
          </div>

          {/* L'ampiezza: ISTANTANEA, e lo dice. Sta qui perche' e' il contesto
              in cui si leggono i movimenti di sopra, non perche' sia live. */}
          <div className="min-w-0">
            <Intestazione
              titolo="Ampiezza del catalogo"
              fonte={
                computedAt
                  ? `istantanea delle ${new Date(computedAt).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`
                  : "istantanea"
              }
            />
            {global && global.stocks_with_data > 0 ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                <div className="min-w-0">
                  <span className="text-muted-foreground">in rialzo </span>
                  <span className="font-semibold tabular-nums text-emerald-800 dark:text-emerald-400">
                    {global.advancers}
                  </span>
                  <span className="text-muted-foreground"> · </span>
                  <span className="font-semibold tabular-nums text-rose-600 dark:text-rose-400">
                    {global.decliners}
                  </span>
                </div>
                <div className="min-w-0">
                  <span className="text-muted-foreground">sopra EMA200 </span>
                  <span className="font-semibold tabular-nums">{global.pct_above_ema200.toFixed(1)}%</span>
                </div>
                <div className="min-w-0">
                  <span className="text-muted-foreground">media </span>
                  <span className={cn("font-semibold tabular-nums", tono(global.avg_change_pct))}>
                    {pct(global.avg_change_pct)}
                  </span>
                </div>
                <div className="min-w-0">
                  <span className="text-muted-foreground">ipercomprati </span>
                  <span className="font-semibold tabular-nums">{global.rsi_overbought_count}</span>
                  <span className="text-muted-foreground"> · ipervenduti </span>
                  <span className="font-semibold tabular-nums">{global.rsi_oversold_count}</span>
                </div>
                <div className="min-w-0">
                  <span className="text-muted-foreground">al max 52s </span>
                  <span className="font-semibold tabular-nums">{global.near_52w_high_count}</span>
                  <span className="text-muted-foreground"> · al min </span>
                  <span className="font-semibold tabular-nums">{global.near_52w_low_count}</span>
                </div>
                <div className="min-w-0">
                  <span className="text-muted-foreground">titoli </span>
                  <span className="font-semibold tabular-nums">{global.stocks_with_data}</span>
                  <span className="text-muted-foreground">/{global.stocks_total}</span>
                </div>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground">
                Nessuna istantanea di ampiezza: non c'e' nessuna lettura da mostrare.
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
