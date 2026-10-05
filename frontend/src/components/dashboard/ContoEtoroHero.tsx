import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { EtoroAndamento, EtoroStrumentoOggi, EtoroVivo } from "@/api/etoro";
import { FlashValue } from "@/components/ui/FlashValue";
import { InfoHint } from "@/components/ui/info-hint";
import { useEtoroAndamento } from "@/hooks/useEtoro";
import { fmtPct } from "@/lib/etoroPortafoglio";
import { formatMoneyGrouped as formatMoney, formatMoneyGroupedSigned as formatMoneySigned } from "@/lib/money";
import {
  INTERVALLI,
  type Intervallo,
  periodoDi,
  piuVicino,
  serieDi,
  tracciato,
  verso,
} from "@/lib/patrimonio";
import { cn } from "@/lib/utils";

/* ─── Il conto eToro in cima alla home (FA-127) ───────────────────────────
 *
 * La prima cosa che si vede aprendo l'app: quanto vale il conto adesso e
 * come si e' mosso. Tre zone, che sotto i 1024px si impilano:
 *
 *   saldo        il numero grande (lampeggia quando cambia), il giorno in
 *                dollari e in %, e le quattro grandezze di un conto a leva:
 *                P/L aperto, margine usato, esposizione con la leva
 *                effettiva, cassa.
 *   curva        il valore nel tempo, Oggi / 1S / 1M / 3M / 1A, e sotto il
 *                rendimento del periodo SENZA versamenti (`generato`).
 *   movimenti    chi muove il conto oggi: il guadagno del giorno per
 *                strumento, calcolato da eToro.
 *
 * ⚠️ Altezza FISSA per ogni larghezza (gate CLS 0,1, FA-106): la home
 * aspetta questi dati prima di disegnarsi (`HomePage`), e qui dentro cio' che
 * arriva dopo — la curva — ha gia' il suo riquadro. Le classi sono letterali.
 *
 * ⚠️ La curva del VALORE comprende versamenti e prelievi: misurato, il conto
 * va da 17.800 a 2.250 USD e risale a 8.660 con l'investito che triplica. Per
 * questo il numero sotto la curva e' il P/L generato, e la curva lo dice.
 */

const ALTEZZA = "h-[700px] lg:h-[300px]";

function tono(v: number | null | undefined): string {
  if (v == null || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
}

function ora(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

const USD = (v: number) => formatMoney(v, "USD");

function Tessera({ etichetta, children, sotto, className }: {
  etichetta: string; children: React.ReactNode; sotto?: React.ReactNode; className?: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border/50 bg-background/60 px-2.5 py-1.5 backdrop-blur-sm">
      <div className="truncate text-[0.6471rem] font-semibold uppercase tracking-wider text-muted-foreground">{etichetta}</div>
      <div className={cn("truncate text-sm font-semibold tabular-nums", className)}>{children}</div>
      {sotto && <div className="truncate text-[0.6471rem] text-muted-foreground tabular-nums">{sotto}</div>}
    </div>
  );
}

function Saldo({ v }: { v: EtoroVivo }) {
  const Freccia = !v.guadagno_giorno ? Minus : v.guadagno_giorno > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="flex min-h-0 flex-col justify-between gap-3 p-4">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[0.6765rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Conto eToro</span>
          <span className="inline-flex items-center gap-1.5 text-[0.6471rem] text-muted-foreground">
            <span
              aria-hidden
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                v.in_ritardo ? "bg-amber-500" : "animate-pulse bg-emerald-500",
              )}
            />
            {v.in_ritardo ? `in ritardo · ${ora(v.aggiornato_il)}` : `dal vivo · ${ora(v.aggiornato_il)}`}
          </span>
        </div>
        <FlashValue
          value={v.valore}
          format={USD}
          className="mt-1 block text-[2.35rem] font-bold leading-none tracking-tight tabular-nums lg:text-[2.6rem]"
        />
        <div className={cn("mt-2 flex items-center gap-1.5 text-sm font-semibold tabular-nums", tono(v.guadagno_giorno))}>
          <Freccia className="h-4 w-4 shrink-0" aria-hidden />
          <span>{formatMoneySigned(v.guadagno_giorno, "USD")}</span>
          <span className="text-xs">({fmtPct(v.guadagno_giorno_pct, 2)})</span>
          <span className="font-normal text-muted-foreground">oggi</span>
        </div>
        {v.valore_ieri != null && (
          <div className="text-[0.6471rem] text-muted-foreground tabular-nums">chiusura di ieri {USD(v.valore_ieri)}</div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <Tessera etichetta="P/L aperto" className={tono(v.pnl_aperto)}>
          {formatMoneySigned(v.pnl_aperto, "USD")}
        </Tessera>
        <Tessera etichetta="Margine usato" sotto={`${v.posizioni} posizioni`}>
          {formatMoney(v.margine_usato, "USD")}
        </Tessera>
        <Tessera
          etichetta="Esposizione"
          sotto={v.leva_effettiva != null ? `leva effettiva ×${v.leva_effettiva.toFixed(1)}` : undefined}
        >
          {formatMoney(v.esposizione, "USD")}
        </Tessera>
        <Tessera etichetta="Cassa disponibile">{formatMoney(v.cassa, "USD")}</Tessera>
      </div>
    </div>
  );
}

function Curva({ v, a, inAttesa }: { v: EtoroVivo; a: EtoroAndamento | undefined; inAttesa: boolean }) {
  const [intervallo, setIntervallo] = useState<Intervallo>("1M");
  const [cursore, setCursore] = useState<number | null>(null);
  const riquadro = useRef<HTMLDivElement>(null);
  const serie = useMemo(() => serieDi(intervallo, a, v), [intervallo, a, v]);
  const t = useMemo(() => tracciato(serie, 1000, 300), [serie]);
  const periodo = periodoDi(intervallo, a);
  const dir = verso(serie);
  const colore = dir === "giu" ? "rgb(225 29 72)" : "rgb(5 150 105)";
  const punto = t && cursore != null ? piuVicino(t, cursore) : null;
  const etichetta = INTERVALLI.find((i) => i.chiave === intervallo)!.etichetta;
  const descrizione = t
    ? `Valore del conto, intervallo ${etichetta}: da ${USD(serie.punti[0].v)} a ${USD(serie.punti[serie.punti.length - 1].v)}`
    : `Valore del conto, intervallo ${etichetta}: dati insufficienti`;

  return (
    <div className="flex min-h-0 flex-col p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-[0.6765rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          Andamento
          <InfoHint
            label="Che cosa mostra la curva"
            text="Il valore del conto Trading a fine giornata, e oggi minuto per minuto. Comprende versamenti e prelievi: il rendimento vero del periodo è il P/L generato qui sotto, cioè i profitti chiusi più la variazione del P/L aperto."
          />
        </span>
        <div role="group" aria-label="Intervallo della curva" className="flex rounded-md border border-border/60 p-0.5">
          {INTERVALLI.map((i) => (
            <button
              key={i.chiave}
              type="button"
              aria-pressed={intervallo === i.chiave}
              onClick={() => setIntervallo(i.chiave)}
              className={cn(
                "min-w-[2.25rem] rounded px-1.5 py-1 text-[0.6765rem] font-semibold transition-colors",
                intervallo === i.chiave ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {i.etichetta}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={riquadro}
        className="relative mt-2 min-h-0 flex-1"
        onPointerMove={(e) => {
          const r = riquadro.current?.getBoundingClientRect();
          if (r && r.width > 0) setCursore(((e.clientX - r.left) / r.width) * 1000);
        }}
        onPointerLeave={() => setCursore(null)}
      >
        {t ? (
          <>
            <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label={descrizione}>
              <defs>
                <linearGradient id="conto-etoro-area" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colore} stopOpacity="0.28" />
                  <stop offset="100%" stopColor={colore} stopOpacity="0" />
                </linearGradient>
              </defs>
              {t.yBase != null && (
                <line x1="0" x2="1000" y1={t.yBase} y2={t.yBase} stroke="currentColor" strokeOpacity="0.25"
                  strokeDasharray="6 6" vectorEffect="non-scaling-stroke" className="text-muted-foreground" />
              )}
              <path d={t.area} fill="url(#conto-etoro-area)" />
              <path d={t.linea} fill="none" stroke={colore} strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
              {punto && (
                <line x1={punto.x} x2={punto.x} y1="0" y2="300" stroke="currentColor" strokeOpacity="0.35"
                  vectorEffect="non-scaling-stroke" className="text-foreground" />
              )}
            </svg>
            <span className="pointer-events-none absolute right-0 top-0 text-[0.6471rem] tabular-nums text-muted-foreground">{USD(t.max)}</span>
            <span className="pointer-events-none absolute bottom-0 right-0 text-[0.6471rem] tabular-nums text-muted-foreground">{USD(t.min)}</span>
            {punto && (
              <div
                className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background"
                style={{ left: `${punto.x / 10}%`, top: `${(punto.y / 300) * 100}%`, width: 10, height: 10, background: colore }}
                aria-hidden
              />
            )}
            {punto && (
              <div className="pointer-events-none absolute left-0 top-0 rounded-md border bg-popover/95 px-2 py-1 text-[0.6765rem] tabular-nums shadow-sm">
                <span className="font-semibold">{USD(punto.p.v)}</span>{" "}
                <span className="text-muted-foreground">
                  {new Date(punto.p.t).toLocaleString("it-IT", intervallo === "oggi"
                    ? { hour: "2-digit", minute: "2-digit" }
                    : { day: "2-digit", month: "short" })}
                </span>
              </div>
            )}
          </>
        ) : (
          <div className={cn("absolute inset-0 flex items-center justify-center rounded-md text-xs text-muted-foreground",
            inAttesa && "animate-pulse bg-muted/40")}>
            {inAttesa ? "" : intervallo === "oggi" ? "La curva di oggi si riempie durante la giornata." : "Storico non ancora disponibile."}
          </div>
        )}
      </div>

      <div className="mt-2 min-h-[2.25rem] text-xs tabular-nums">
        {intervallo === "oggi" ? (
          <span className="text-muted-foreground">
            Dalla chiusura di ieri:{" "}
            <span className={cn("font-semibold", tono(v.guadagno_giorno))}>
              {formatMoneySigned(v.guadagno_giorno, "USD")} ({fmtPct(v.guadagno_giorno_pct, 2)})
            </span>
          </span>
        ) : periodo ? (
          <div className="flex flex-wrap gap-x-4 gap-y-0.5">
            <span className="text-muted-foreground">
              P/L generato{" "}
              <span className={cn("font-semibold", tono(periodo.generato))}>
                {formatMoneySigned(periodo.generato, "USD")} ({fmtPct(periodo.generato_pct)})
              </span>
            </span>
            {periodo.flussi != null && Math.abs(periodo.flussi) >= 1 && (
              <span className="text-muted-foreground">
                versamenti netti <span className="font-semibold text-foreground">{formatMoneySigned(periodo.flussi, "USD")}</span>
              </span>
            )}
            <span className="text-muted-foreground">dal {new Date(`${periodo.dal}T12:00:00Z`).toLocaleDateString("it-IT", { day: "2-digit", month: "short" })}</span>
          </div>
        ) : (
          <span className="text-muted-foreground">Rendimento del periodo non ancora calcolabile.</span>
        )}
      </div>
    </div>
  );
}

const RIGHE_MOVIMENTI = 5;

function Movimenti({ strumenti }: { strumenti: EtoroStrumentoOggi[] }) {
  const righe = strumenti.filter((s) => s.guadagno_giorno != null).slice(0, RIGHE_MOVIMENTI);
  const massimo = Math.max(...righe.map((s) => Math.abs(s.guadagno_giorno ?? 0)), 1);
  return (
    <div className="flex min-h-0 flex-col p-4">
      <span className="text-[0.6765rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Chi muove il conto oggi
      </span>
      {righe.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">Nessun movimento ancora oggi.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {righe.map((s) => {
            const g = s.guadagno_giorno ?? 0;
            const largo = `${(Math.abs(g) / massimo) * 50}%`;
            const nome = s.ticker ?? s.simbolo ?? `#${s.instrument_id}`;
            return (
              <li key={s.instrument_id} className="grid grid-cols-[4.5rem_minmax(0,1fr)_4.75rem] items-center gap-2 text-xs">
                {s.ticker ? (
                  <Link to={`/stocks/${encodeURIComponent(s.ticker)}`} className="truncate font-semibold hover:underline">{nome}</Link>
                ) : (
                  <span className="truncate font-semibold">{nome}</span>
                )}
                <div className="relative h-2 rounded-full bg-muted/60" aria-hidden>
                  <span className="absolute left-1/2 top-0 h-full w-px bg-border" />
                  <span
                    className={cn("absolute top-0 h-full rounded-full",
                      g >= 0 ? "left-1/2 bg-emerald-500/80" : "right-1/2 bg-rose-500/80")}
                    style={{ width: largo }}
                  />
                </div>
                <span className={cn("text-right font-semibold tabular-nums", tono(g))}>{formatMoneySigned(g, "USD")}</span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-auto pt-2 text-[0.6471rem] text-muted-foreground">
        Guadagno di oggi per strumento, calcolato da eToro.{" "}
        <Link to="/positions" className="underline">Tutte le posizioni</Link>
      </p>
    </div>
  );
}

/** `v` arriva dalla home, che lo aspetta prima di disegnarsi. */
export function ContoEtoroHero({ v }: { v: EtoroVivo }) {
  const a = useEtoroAndamento();
  const giornata = v.guadagno_giorno ?? 0;
  return (
    <section
      aria-label="Il tuo conto eToro"
      className={cn("relative overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm", ALTEZZA)}
    >
      {/* Un alone che prende il colore della giornata: il verso si legge prima del numero. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute -left-32 -top-32 h-80 w-80 rounded-full blur-3xl",
          giornata > 0 ? "bg-emerald-500/15" : giornata < 0 ? "bg-rose-500/15" : "bg-muted/40",
        )}
      />
      <div className="relative grid h-full grid-rows-[auto_minmax(0,1fr)_auto] divide-y divide-border/50 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.65fr)_minmax(0,0.95fr)] lg:grid-rows-1 lg:divide-x lg:divide-y-0">
        <Saldo v={v} />
        <Curva v={v} a={a.data} inAttesa={a.isLoading} />
        <Movimenti strumenti={v.strumenti} />
      </div>
    </section>
  );
}
