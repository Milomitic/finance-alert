import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import type { OhlcvBar, Stock, StockKpis } from "@/api/types";
import { MarketStateBadge } from "@/components/dashboard/MarketStateBadge";
import { EtfMembershipStrip } from "@/components/stock/EtfMembershipChips";
import { EtoroMarchio } from "@/components/stock/EtoroMarchio";
import { IndexMembershipChips } from "@/components/stock/IndexMembershipChips";
import { NotaTitolo } from "@/components/stock/NotaTitolo";
import { StellaPreferito } from "@/components/stock/StellaPreferito";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { useLiveQuote } from "@/hooks/useLiveQuote";
import { useNowTick } from "@/hooks/useNowTick";
import { formatMoney, formatMoneySigned } from "@/lib/money";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";
import { GIU, SU } from "@/lib/coloriGrafico";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

/** Una sola forma per le etichette sotto il nome: borsa, indici, settore,
 *  sotto-settore e fondi si leggono come la stessa famiglia. */
const ETICHETTA =
  "inline-flex items-center gap-1.5 rounded-md bg-muted/70 dark:bg-muted/40 hover:bg-muted px-2 py-0.5 text-xs sm:px-2.5 sm:py-1 sm:text-sm font-medium transition-colors";

interface Props {
  stock: Stock;
  kpis: StockKpis;
  /** Optional OHLCV history — drawn as a faded sparkline background. */
  ohlcv?: OhlcvBar[];
  /** Contenuto da mostrare SOTTO identita' e prezzo, dentro questa card e
   *  quindi in sovrimpressione allo sparkline.
   *
   *  ⚠️ Uno slot e non un import diretto del profilo: questa scheda non deve
   *  sapere che cosa le si mette sotto, o diventerebbe la scheda del profilo
   *  con un prezzo in cima. Chi compone la pagina decide, e sotto il Full HD
   *  non passa nulla — a quelle larghezze il profilo ha una riga sua. */
  sotto?: React.ReactNode;
  /** Negoziabile su eToro (FA-126): arriva col dettaglio, quindi il marchio
   *  accanto al ticker c'e' dal primo disegno. */
  suEtoro?: boolean;
}

/**
 * Faded sparkline background. Renders absolute inset-0 behind the header
 * content so the page hero feels like a "ticker tape" — the price-trend
 * shape is always visible at a glance, but never competes with the foreground
 * text. Color follows the day's % change (green up / red down).
 */
export function HeaderSparkline({ closes, up }: { closes: number[]; up: boolean }) {
  if (closes.length < 2) return null;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const W = 100;
  const H = 30;
  const points = closes
    .map((v, i) => {
      const x = (i / (closes.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  // Fill area under the line for stronger background presence
  const areaPath = `M0,${H} L${points} L${W},${H} Z`;
  // Emerald/rose come il resto dell'app per la direzione: il rosso
  // `#dc2626` e' quello dei guasti (CLAUDE.md, una palette per significato).
  const stroke = up ? SU : GIU;
  return (
    <svg
      // Solo il terzo inferiore della scheda (A-48): a tutta altezza l'area
      // colorata era alta ~350px, la superficie piu' grande della pagina, e
      // dipingeva il «giu'» dietro nome e prezzo. Il grafico vero ora sta
      // subito sotto: questo resta un accenno di forma, non un grafico.
      className="absolute inset-x-0 bottom-0 h-1/3 w-full pointer-events-none opacity-50 sm:opacity-70"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        {/* V3.3 area gradient: la zona sopra la linea resta totalmente
            trasparente (non disegnata); la zona sotto la linea (il
            "fill di integrale") parte dalla linea con opacità medio-
            alta e dissolve verso il basso del grafico. Effetto
            classico delle dashboard finanziarie tipo Robinhood/eToro:
            la linea ha una scia colorata che si fonde col background. */}
        <linearGradient id="hdr-spark-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.40} />
          <stop offset="60%" stopColor={stroke} stopOpacity={0.12} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
        <linearGradient id="hdr-spark-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0.85} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#hdr-spark-area)" />
      <polyline
        points={points}
        fill="none"
        stroke="url(#hdr-spark-line)"
        strokeWidth={1.2}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function StockHeader({ stock, kpis, ohlcv, sotto, suEtoro }: Props) {
  const flag = getStockFlagCode(stock.country, stock.ticker);

  // Live quote — polls every 15s. Falls back to the kpis snapshot (last
  // close from the daily scan) when the live fetch hasn't returned yet,
  // when it errored (e.g. yfinance breaker open), or when the live price
  // isn't available (e.g. delisted ticker).
  const live = useLiveQuote(stock.ticker);
  const now = useNowTick();
  const liveOk = live.data && live.data.price != null && live.data.error == null;
  const isMarketOpen = liveOk && live.data!.market_state === "OPEN";
  // US pre-market: the live price is a pre-open quote and `change_pct` is the
  // pre-open move vs yesterday's close. Without flagging this, the price block
  // would read "Ultima chiusura" over a live pre-market figure — exactly the
  // ambiguity the PRE badge resolves on the dashboard cards.
  const isPremarket = liveOk && live.data!.market_state === "PRE";
  // "STALE" = the backend served a RESTORED snapshot because it could not
  // refresh the quote (breaker open, batch deadline, or a cold cache right
  // after a restart). The price is real and useful, it is just not live —
  // so it must not sit under a LIVE chip, and it must not silently look like
  // a normal market close either.
  const isStale = liveOk && live.data!.market_state === "STALE";
  // FA-180: finche' la prima quotazione non e' arrivata, l'ultima chiusura NON
  // si presenta come prezzo: in pre-market sarebbe un numero di ieri sotto
  // l'etichetta di oggi, sostituito qualche secondo dopo. Al suo posto uno
  // spazio riservato della stessa altezza. Su un errore si torna alla
  // chiusura, che e' meglio di niente e lo dice.
  const inAttesa = live.isLoading && !live.data;
  const displayPrice = liveOk ? live.data!.price! : inAttesa ? null : kpis.last_close;
  const change = liveOk ? (live.data!.change_pct ?? null) : inAttesa ? null : kpis.change_pct;
  const changeAbs = liveOk ? live.data!.change_abs : null;
  const liveAge = liveOk ? now / 1000 - live.data!.fetched_at : null;

  // Tone: stripe on left + text accent. Card background stays neutral
  // (`bg-card`) so only the SVG sparkline's area gradient colors the
  // pixels UNDER the chart line — the area ABOVE the line (where the
  // ticker / name / price text sits) stays clean white. The previous
  // `bg-emerald-50/50` tint covered the whole card uniformly,
  // contradicting the gradient's "fade only beneath the line" intent.
  const tone =
    change == null
      ? { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" }
      : change > 0
        ? { bg: "bg-card", stripe: "bg-emerald-500", text: TESTO_SU, arrow: "▲" }
        : change < 0
          ? { bg: "bg-card", stripe: "bg-rose-500", text: TESTO_GIU, arrow: "▼" }
          : { bg: "bg-card", stripe: "bg-slate-300 dark:bg-slate-600", text: "text-muted-foreground", arrow: "" };

  const closes = (ohlcv ?? []).map((b) => b.close).filter((c) => Number.isFinite(c));
  const sparkUp = (change ?? 0) >= 0;

  return (
    <Card className={cn("relative overflow-hidden border-border/60", tone.bg)}>
      {/* Sparkline behind everything */}
      <HeaderSparkline closes={closes} up={sparkUp} />
      <div className={cn("absolute left-0 top-0 bottom-0 w-1.5 z-10", tone.stripe)} aria-hidden />
      {/* Smaller padding now that the KPI strip is gone */}
      {/* Contenuto centrato verticalmente SEMPRE, anche col profilo sotto
          (richiesta dell'utente, 2026-09-21). Prima si centrava solo la sola
          identita', per il timore che due blocchi finissero schiacciati: non
          succede, perche' `gap-4` resta fra loro e `justify-center`
          distribuisce solo lo spazio AVANZATO, sopra e sotto in parti uguali.
          Allineati in alto lasciavano tutto il vuoto in fondo, sopra lo
          sparkline. */}
      <CardContent className="relative z-10 flex h-full flex-col justify-center gap-4 p-4 pl-7">
        {/* Su telefono: identita', prezzo, poi i tag (richiesta del 2026-11-22:
            il prezzo stava sotto tre righe di etichette). Da sm: identita' e tag
            a sinistra, prezzo a destra centrato sulle due righe, come prima. */}
        <div className="grid grid-cols-1 items-center gap-x-12 gap-y-3 sm:grid-cols-[minmax(0,auto)_auto] sm:justify-start">
          {/* Identity column: logo aligned + vertically centered with the
              ticker/name on one row; the exchange/sector tags sit BELOW. */}
          <div className="min-w-0">
            <div className="flex items-center gap-4">
              {/* Logo (flag lives inside the exchange tag below) */}
              <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-border/60 p-2 shadow-sm shrink-0">
                <StockLogo ticker={stock.ticker} size="md" />
              </div>
              {/* Ticker + name */}
              <div className="min-w-0 flex flex-col gap-1">
                <span className="flex items-center gap-1">
                  <span className="text-3xl sm:text-4xl font-bold tracking-tight tabular-nums leading-none">
                    {stock.ticker}
                  </span>
                  <StellaPreferito ticker={stock.ticker} />
                  <NotaTitolo ticker={stock.ticker} />
                  <EtoroMarchio su={suEtoro} />
                </span>
                <span className="text-xl text-foreground/80 font-medium truncate" title={stock.name}>
                  {stock.name}
                </span>
              </div>
            </div>
          </div>

          {/* Price block — moved next to the identity (left-aligned), both
              vertically centered via the row's items-center. Extra left margin
              gives a bit more breathing room between the name and the price. */}
          <div className="text-left tabular-nums flex flex-col gap-1 items-start sm:col-start-2 sm:row-span-2 sm:row-start-1">
            {inAttesa && (
              <div role="status" aria-label="Quotazione in arrivo" className="flex flex-col gap-1 items-start">
                <span className="text-sm uppercase tracking-wide text-muted-foreground font-semibold">Quotazione…</span>
                <span aria-hidden className="block h-[1.875rem] w-32 sm:h-12 sm:w-52 rounded-md bg-muted animate-pulse" />
                <span aria-hidden className="block h-7 w-24 sm:h-8 sm:w-32 mt-1 rounded-md bg-muted animate-pulse" />
              </div>
            )}
            {displayPrice != null && (
              <>
                <div className="flex items-center gap-1.5 text-sm uppercase tracking-wide">
                  {isMarketOpen ? (
                    <MarketStateBadge
                      phase="open"
                      size="md"
                      title={
                        liveAge != null
                          ? `Mercato aperto · prezzo ${Math.round(liveAge)}s fa (cache 10s + polling 15s)`
                          : "Prezzo live"
                      }
                    />
                  ) : isPremarket ? (
                    <MarketStateBadge
                      phase="pre"
                      size="md"
                      title={
                        liveAge != null
                          ? `Pre-market USA · la variazione è il movimento pre-apertura vs chiusura di ieri · ${Math.round(liveAge)}s fa`
                          : "Pre-market USA — la variazione mostrata è il movimento pre-apertura rispetto alla chiusura di ieri"
                      }
                    />
                  ) : isStale ? (
                    <MarketStateBadge
                      phase="stale"
                      size="md"
                      title={
                        liveAge != null && liveAge > 90
                          ? `Quotazione non aggiornabile ora — ultimo prezzo salvato ${Math.round(liveAge / 60)} min fa`
                          : "Quotazione non aggiornabile ora — mostro l'ultimo prezzo salvato, non è un valore live"
                      }
                    />
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-muted-foreground font-semibold"
                      title={
                        liveOk
                          ? "Mercato chiuso — il prezzo mostrato è l'ultima chiusura"
                          : "Live quote non disponibile — mostra l'ultima chiusura giornaliera"
                      }
                    >
                      Ultima chiusura
                    </span>
                  )}
                </div>
                {/* La valuta e quella di QUOTAZIONE, non il dollaro: 312 titoli su
                    1010 non sono in dollari e questo era il numero piu grande
                    della pagina con il simbolo sbagliato sopra. */}
                <FlashValue
                  value={displayPrice}
                  format={(v) => formatMoney(v, stock.currency)}
                  className="text-3xl sm:text-5xl font-bold leading-none"
                />
              </>
            )}
            {change != null && (
              <div className={cn("inline-flex items-baseline gap-1.5 text-lg sm:text-2xl font-bold mt-1", tone.text)}>
                <span className="text-lg">{tone.arrow}</span>
                {changeAbs != null && (
                  <span className="text-base font-semibold opacity-80">
                    {formatMoneySigned(changeAbs, stock.currency)}
                  </span>
                )}
                <span>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span>
              </div>
            )}
            {/* V3.3: quando il mercato è aperto (o in pre-market) e il
                prezzo "live" differisce dalla chiusura precedente, mostra
                la previous close come contesto. La variazione % è già
                coperta sopra; questa caption fornisce il prezzo di
                riferimento da cui si calcola il movimento. In pre-market
                è la base del movimento pre-apertura; intraday è il prezzo
                di partenza della giornata. Nascosto a mercato chiuso (in
                quel caso il prezzo mostrato È già la chiusura). */}
            {/* FA-158: col breaker di Yahoo aperto il prezzo viene da Finnhub,
                e si dice. */}
            {liveOk && live.data!.source === "finnhub" && (
              <div className="text-[0.7059rem] uppercase tracking-wider text-muted-foreground">
                Prezzo da Finnhub (Yahoo non risponde)
              </div>
            )}
            {(isMarketOpen || isPremarket) && live.data?.prev_close != null && (
              <div
                className="text-[0.7059rem] uppercase tracking-wider text-muted-foreground mt-0.5"
                title={
                  isPremarket
                    ? "Chiusura di ieri — riferimento da cui si calcola il movimento pre-apertura"
                    : "Chiusura della sessione di trading precedente — riferimento da cui calcolare la variazione intraday"
                }
              >
                Prev close:{" "}
                <span className="text-foreground/80 font-semibold tabular-nums">
                  {formatMoney(live.data.prev_close, stock.currency)}
                </span>
              </div>
            )}
          </div>
            {/* Le etichette in tre righe, ciascuna una domanda (2026-10-12):
                dove si quota e in quali indici sta; in che settore e
                sotto-settore; quanti fondi lo detengono. Prima erano una riga
                sola che andava a capo dove capitava, e un indice finiva
                accanto al settore come se fossero la stessa cosa. */}
            <div className="flex min-w-0 flex-col items-start gap-1.5 sm:col-start-1 sm:row-start-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {/* Exchange: cliccabile, porta allo screener filtrato per questa
                    borsa. La bandiera vive dentro il tag (il listing e'
                    proprieta' dell'exchange). */}
                <Link
                  to={`/stocks?exchange=${encodeURIComponent(stock.exchange)}`}
                  title={`Vedi i titoli su ${stock.exchange}`}
                  className={ETICHETTA}
                >
                  {flag && (
                    <img
                      src={`/flags/${flag}.svg`}
                      alt={stock.country ?? ""}
                      width={18}
                      height={12}
                      style={{ width: "18px", height: "12px", objectFit: "cover" }}
                      className="rounded-sm shadow-sm"
                      aria-hidden
                    />
                  )}
                  {stock.exchange}
                </Link>
                {/* Gli INDICI: appartenenza completa, non "fra i primi 25" come
                    le chip ETF. */}
                <IndexMembershipChips ticker={stock.ticker} indices={stock.in_indices} />
              </div>
              {(stock.sector || stock.industry) && (
                <div className="flex flex-wrap items-center gap-1.5">
                  {stock.sector && (
                    <Link
                      to={`/sectors/${encodeURIComponent(stock.sector)}`}
                      title={`Vedi il settore ${stock.sector}`}
                      className={ETICHETTA}
                    >
                      {stock.sector}
                    </Link>
                  )}
                  {stock.industry && (
                    <Link
                      to={`/stocks?industry=${encodeURIComponent(stock.industry)}`}
                      title={`Vedi i titoli del sotto-settore ${stock.industry}`}
                      className={cn(ETICHETTA, "text-foreground/80")}
                    >
                      {stock.industry}
                    </Link>
                  )}
                </div>
              )}
              {/* I fondi tracciati che lo detengono (13F / superinvestor): lo
                  stesso numero del badge dello screener. Porta all'elenco dei
                  detentori. Zero non si mostra: un titolo senza fondi non ha
                  bisogno di un'etichetta che lo dica. */}
              {stock.fondi_detentori ? (
                <a href="#fondi-detentori" className={ETICHETTA}>
                  <Building2 className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                  {stock.fondi_detentori} {stock.fondi_detentori === 1 ? "fondo lo detiene" : "fondi lo detengono"}
                </a>
              ) : null}
            </div>
        </div>

        <EtfMembershipStrip ticker={stock.ticker} funds={stock.in_etfs} />

        {/* ⚠️ Il divisore e' `border-border/40` e non pieno: sotto c'e' lo
            sparkline, e una riga netta lo taglierebbe a meta' invece di
            separare due blocchi che condividono lo stesso sfondo. */}
        {sotto && (
          <div className="min-w-0 border-t border-border/40 pt-3">{sotto}</div>
        )}
      </CardContent>
    </Card>
  );
}
