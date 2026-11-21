import { useQuery } from "@tanstack/react-query";
import { Briefcase, Gavel, Newspaper, Star } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { dashboard, type AnalystAction } from "@/api/dashboard";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { QueryError } from "@/components/ui/query-error";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";
import { formatMoney } from "@/lib/money";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";

/* Genuine rating CHANGES only — the card used to be dominated by
 * "Maintain"/"Reiterate" rows (a firm reaffirming, no change) which are
 * noise. We keep upgrades, downgrades and coverage initiations and drop
 * the maintains, matching the card's own description. */
const CHANGE_ACTIONS = new Set(["up", "down", "init"]);

/* A price target is only meaningful when strictly positive. yfinance /
 * the news extractor sometimes return 0 (or null) when a firm moved the
 * rating but didn't publish a number → treat non-positive as "no number". */
function posTarget(v: number | null | undefined): number | null {
  return v != null && v > 0 ? v : null;
}

/* Grade → buy/hold/sell tone bucket. Mirrors AnalystTargetCard.gradeTone
 * so the dashboard feed and the stock-detail "Analyst" card share the
 * exact same rating vocabulary + colors. */
function gradeTone(grade: string | null | undefined): "buy" | "hold" | "sell" | "neutral" {
  const g = (grade ?? "").toLowerCase();
  if (/buy|outperform|overweight|positive|accumulate/.test(g)) return "buy";
  if (/sell|underperform|underweight|negative|reduce/.test(g)) return "sell";
  if (/hold|neutral|equal|market perform|sector weight|in-line|peer perform/.test(g))
    return "hold";
  return "neutral";
}

/* Literal class strings (not composed) so Tailwind's purger keeps them.
 * Same palette as AnalystTargetCard's TONE_CLASSES. */
const TONE_CLASSES: Record<ReturnType<typeof gradeTone>, string> = {
  buy: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200",
  hold: "bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200",
  sell: "bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200",
  neutral: "bg-muted text-muted-foreground",
};

/* The rating itself, as a tone-classed chip (the new row "label" — the
 * Upgrade/Maintain action chip was removed). The full from→to transition
 * lives on hover for context. */
function GradeChip({
  from,
  to,
}: {
  from?: string | null;
  to?: string | null;
}) {
  const grade = to || from || "—";
  return (
    <span
      className={cn(
        "px-1.5 py-0.5 rounded text-[0.7059rem] font-semibold shrink-0",
        TONE_CLASSES[gradeTone(grade)],
      )}
      title={from && to && from !== to ? `${from} → ${to}` : grade}
    >
      {grade}
    </span>
  );
}

/* Price-target chip — arrow (direction of the target move) + the new
 * dollar figure, colored by `price_target_action`. Same inline style as
 * AnalystTargetCard.PriceTargetChip. Renders nothing when there's no
 * usable number (the date still anchors the row). */
function priceTargetTone(action: string | null | undefined): { cls: string; arrow: string } {
  switch (action) {
    case "Raises":
      return { cls: TESTO_SU, arrow: "↑" };
    case "Lowers":
      return { cls: TESTO_GIU, arrow: "↓" };
    case "Initiates":
      return { cls: "text-blue-700 dark:text-blue-300", arrow: "✦" };
    case "Maintains":
    default:
      return { cls: "text-muted-foreground", arrow: "→" };
  }
}

function PriceTargetChip({ a }: { a: AnalystAction }) {
  const cur = posTarget(a.current_price_target);
  if (cur == null) return null;
  const prior = posTarget(a.prior_price_target);
  const tone = priceTargetTone(a.price_target_action);
  // La valuta del titolo, non un simbolo fisso (C-20): un target su un
  // titolo di Londra o di Hong Kong usciva in dollari.
  const fmt = formatMoney(cur, a.currency, { decimals: Number.isInteger(cur) ? 0 : 2 });
  const tondo = (v: number) => formatMoney(v, a.currency, { decimals: 0 });
  const title =
    prior != null && prior !== cur
      ? `Target: ${tondo(prior)} → ${tondo(cur)}`
      : `Target: ${tondo(cur)}`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 tabular-nums font-bold shrink-0 text-[0.7647rem]",
        tone.cls,
      )}
      title={title}
    >
      <span>{tone.arrow}</span>
      <span>{fmt}</span>
    </span>
  );
}

/* Target upside vs current price: (target / current − 1). Shown immediately
 * right of the target chip so the user reads "where the target sits relative
 * to today" without mental math. Colored by sign (green above price, red
 * below). Renders nothing when either number is missing/non-positive. */
function TargetUpsideChip({ a }: { a: AnalystAction }) {
  const target = posTarget(a.current_price_target);
  const cur = a.current_price;
  if (target == null || cur == null || cur <= 0) return null;
  const pct = (target / cur - 1) * 100;
  const up = pct >= 0;
  return (
    <span
      className={cn(
        "shrink-0 w-[52px] text-right tabular-nums text-[0.7059rem] font-semibold",
        up ? TESTO_SU : TESTO_GIU,
      )}
      title={`Target ${up ? "sopra" : "sotto"} il prezzo attuale (${formatMoney(cur, a.currency, { decimals: 2 })}) del ${Math.abs(pct).toFixed(1)}%`}
    >
      {up ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

/** Il segno di un titolo seguito (FA-113), sull'angolo del logo.
 *
 *  ⚠️ Non accanto al ticker: la riga misura gia' 7px rimasti alla banca a
 *  certe larghezze (vedi sotto), e un'icona `shrink-0` in piu' li toglierebbe
 *  proprio al nome — l'identita' cede e la decorazione sopravvive. Sull'angolo
 *  del logo non occupa larghezza.
 *
 *  Solo visivo: il testo per gli assistivi sta DOPO il ticker (`TestoRilevanza`).
 *  Messo qui, prima del ticker, il nome del collegamento diventava
 *  «in posizioneADBE»: il calcolo del nome accessibile non mette spazi fra
 *  elementi in linea. */
export function SegnoRilevanza({ rilevanza }: { rilevanza?: string | null }) {
  if (rilevanza !== "posizione" && rilevanza !== "preferito") return null;
  return (
    <span className="absolute -bottom-1 -right-1 rounded-full bg-card p-px leading-none" aria-hidden>
      {rilevanza === "posizione" ? (
        <Briefcase className="h-2.5 w-2.5 text-muted-foreground" />
      ) : (
        <Star className="h-2.5 w-2.5 fill-amber-400 text-amber-700 dark:fill-amber-300 dark:text-amber-300" />
      )}
    </span>
  );
}

/** «, in posizione» dopo il ticker, per gli assistivi. La virgola separa le
 *  due parole anche dove gli spazi si perdono. */
export function TestoRilevanza({ rilevanza }: { rilevanza?: string | null }) {
  if (rilevanza !== "posizione" && rilevanza !== "preferito") return null;
  return <span className="sr-only">, {rilevanza === "posizione" ? "in posizione" : "preferito"}</span>;
}

export function ActionRow({ a }: { a: AnalystAction }) {
  return (
    <li className="border-b border-border/40 last:border-b-0 min-w-0">
      <Link
        to={`/stocks/${encodeURIComponent(a.ticker)}`}
        className="flex items-center gap-2.5 px-3 py-2 hover:bg-accent/30 transition-colors min-w-0"
        title={a.name ?? a.ticker}
      >
        {/* Compact identity: logo + ticker (company name → row tooltip). */}
        <span className="relative shrink-0 inline-flex">
          <StockLogo ticker={a.ticker} size="xs" />
          <SegnoRilevanza rilevanza={a.rilevanza} />
        </span>
        <span className="shrink-0 w-[40px] text-[0.7647rem] font-bold tabular-nums leading-none truncate">
          {a.ticker}
          <TestoRilevanza rilevanza={a.rilevanza} />
        </span>

        {/* Firm — flexes + truncates first when the row gets tight. */}
        <span
          className="flex-1 min-w-0 text-[0.7059rem] text-muted-foreground truncate"
          title={a.firm}
        >
          {a.firm || "—"}
        </span>
        {a.from_news && (
          <span
            className="inline-flex items-center gap-0.5 text-[0.6471rem] text-muted-foreground shrink-0"
            title="Estratto da una notizia (non dal feed strutturato)"
          >
            <Newspaper className="h-2.5 w-2.5" /> news
          </span>
        )}

        {/* The new "label": rating (valutazione) + price target, in the
            stock-detail Analyst card's style. */}
        <GradeChip from={a.from_grade} to={a.to_grade} />
        <PriceTargetChip a={a} />
        {/* Upside and date step aside until dense-4. Measured on this row at a
            1920px viewport: 287px of shrink-0 children plus 64px of gaps in a
            383px row, so the firm — the only flexible cell — was left 7px and
            rendered as nothing. These two are the ones to drop: the upside is
            derivable from the price target beside it, and the date is the
            least urgent field in a "who said what" list. Dropping both returns
            ~148px to the firm. */}
        <span className="hidden dense-4:contents">
          <TargetUpsideChip a={a} />
        </span>

        <span className="hidden dense-4:block shrink-0 w-10 text-right text-[0.6765rem] text-muted-foreground tabular-nums whitespace-nowrap">
          {fmtDate(a.date)}
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-3 py-2">
      <div className="flex items-center gap-2.5">
        <div className="h-7 w-7 rounded-full bg-muted/60 animate-pulse" />
        <div className="h-3 w-10 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 flex-1 rounded bg-muted/40 animate-pulse" />
        <div className="h-4 w-12 rounded bg-muted/40 animate-pulse" />
      </div>
    </li>
  );
}

export function AnalystActionsCard() {
  const q = useQuery({
    queryKey: ["analyst-actions"],
    queryFn: ({ signal }) => dashboard.analystActions(40, signal),
    // Analyst actions only change when fundamentals are re-fetched
    // (weekly TTL). A 5-min client cache avoids re-pinging on every
    // dashboard revisit while staying fresh enough.
    staleTime: 5 * 60_000,
  });
  // FA-149: per difetto i tuoi titoli. Il server include sempre le loro
  // azioni, anche oltre il tetto di 40, quindi il filtro qui non perde niente.
  const [vista, setVista] = useState<"miei" | "tutti">("miei");
  // Show only genuine rating changes — hide the Maintain/Reiterate rows.
  const cambi = (q.data ?? []).filter((a) => CHANGE_ACTIONS.has(a.action));
  const items = vista === "miei" ? cambi.filter((a) => a.rilevanza) : cambi;
  const isEmpty = !q.isLoading && items.length === 0;

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Gavel}
            label="Valutazioni analisti"
            right={
              <div className="flex rounded-md border border-border text-xs" role="group" aria-label="Quali titoli">
                {(["miei", "tutti"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    aria-pressed={vista === v}
                    onClick={() => setVista(v)}
                    className={cn(
                      "min-h-6 px-2 first:rounded-l-md last:rounded-r-md",
                      vista === v ? "bg-muted font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {v === "miei" ? "I miei" : "Tutti"}
                  </button>
                ))}
              </div>
            }
          />
        </div>
        {q.isLoading ? (
          <ul className="relative flex-1 min-h-0 overflow-y-auto">
            {Array.from({ length: 10 }).map((_, i) => (
              <RowSkeleton key={i} />
            ))}
          </ul>
        ) : q.isError ? (
          /* Un errore diceva "nessun upgrade/downgrade recente": una
             affermazione sul mercato, fatta quando la fetch non e' arrivata. */
          <div className="p-4">
            <QueryError message="delle azioni analisti" onRetry={q.refetch} isRetrying={q.isFetching} />
          </div>
        ) : isEmpty && vista === "miei" ? (
          <div className="flex-1 min-h-0 flex items-center justify-center px-4 text-center">
            <div className="text-xs text-muted-foreground">
              Nessun cambio di rating sui tuoi titoli negli ultimi 90 giorni.
              <br />
              <button type="button" className="mt-1 underline underline-offset-2 text-foreground" onClick={() => setVista("tutti")}>
                Mostra tutto il catalogo
              </button>
            </div>
          </div>
        ) : isEmpty ? (
          <div className="flex-1 min-h-0 flex items-center justify-center px-4 text-center">
            <div className="text-xs text-muted-foreground">
              Nessun upgrade/downgrade recente.
              <br />
              <span className="text-muted-foreground">
                Compaiono qui i cambi di rating (upgrade / downgrade /
                initiation) degli ultimi 90 giorni man mano che i
                fondamentali vengono aggiornati.
              </span>
            </div>
          </div>
        ) : (
          <ul className="relative flex-1 min-h-0 overflow-y-auto">
            {items.map((a, i) => (
              <ActionRow key={`${a.ticker}-${a.date}-${a.firm}-${i}`} a={a} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
