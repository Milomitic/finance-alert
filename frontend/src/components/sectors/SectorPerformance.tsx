import { Activity, BellRing, Gauge, LineChart as LineChartIcon, TrendingDown, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { SectionTitle } from "@/components/ui/section-title";
import type { AndamentoSettore, Quota, SectorStockRow, SegnaliSettore } from "@/hooks/useSectorDetail";
import {
  INTERVALLI,
  type Intervallo,
  formatRendimento,
  letturaAmpiezza,
  quota,
  ribasa,
  tonoRendimento,
} from "@/lib/sectorPerformance";
import { detectorLabel } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

/* ─── L'andamento di un settore (2026-10-11) ───────────────────────────────
 *
 * La pagina di un settore mostrava fondamentali e punteggi, e nemmeno un numero
 * su come il settore si fosse MOSSO. Quattro schede, tutte dalle barre che
 * l'app ha gia' (`sector_performance_service`):
 *
 *   - Andamento: il settore contro l'ETF settoriale e l'S&P 500, e i
 *     rendimenti su sei finestre;
 *   - Ampiezza: quanti titoli partecipano, non solo la media;
 *   - Chi traina e chi frena: i migliori e i peggiori del mese;
 *   - Segnali: cosa ha detto il motore sul settore nell'ultimo mese.
 *
 * Colori di linea neutri (il settore nel colore primario, i confronti in
 * ambra e grigio): rosa/smeraldo restano la DIREZIONE dei rendimenti. */

const COLORI = {
  settore: "hsl(var(--primary))",
  etf: "rgb(245 158 11)",
  spy: "rgb(148 163 184)",
} as const;

function dataBreve(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

/* ─── Andamento ─────────────────────────────────────────────────────────── */

export function AndamentoCard({ a, nTitoli }: { a: AndamentoSettore; nTitoli: number }) {
  const [intervallo, setIntervallo] = useState<Intervallo>("1a");
  const punti = useMemo(() => ribasa(a.serie, intervallo), [a.serie, intervallo]);
  const ultimo = punti[punti.length - 1];
  const etf = a.etf_ticker ?? null;
  const linee: { k: "settore" | "etf" | "spy"; nome: string }[] = [
    { k: "settore", nome: "Settore" },
    ...(etf ? [{ k: "etf" as const, nome: etf }] : []),
    { k: "spy", nome: "S&P 500" },
  ];
  const rendimenti = a.rendimenti;

  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <SectionTitle
          icon={LineChartIcon}
          label="Andamento"
          className="mb-2"
          right={
            <div className="flex rounded-md border p-0.5" role="group" aria-label="Intervallo del grafico">
              {INTERVALLI.map((i) => (
                <button
                  key={i.id}
                  type="button"
                  onClick={() => setIntervallo(i.id)}
                  aria-pressed={intervallo === i.id}
                  className={cn(
                    "min-h-[32px] min-w-[40px] rounded px-2 text-xs font-semibold transition-colors",
                    intervallo === i.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {i.label}
                </button>
              ))}
            </div>
          }
        />

        {/* La legenda porta il numero: quanto ha fatto ciascuno nell'intervallo. */}
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {linee.map((l) => (
            <span key={l.k} className="inline-flex items-center gap-1.5">
              <span
                className={cn("inline-block h-0.5 w-4 rounded", l.k === "spy" && "border-t border-dashed")}
                style={{ background: l.k === "spy" ? "transparent" : COLORI[l.k], borderColor: COLORI.spy }}
                aria-hidden
              />
              <span className="text-muted-foreground">{l.nome}</span>
              <span className={cn("font-bold tabular-nums", tonoRendimento(ultimo?.[l.k]))}>
                {formatRendimento(ultimo?.[l.k])}
              </span>
            </span>
          ))}
        </div>

        <div className="h-[240px] sm:h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={punti} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis
                dataKey="data"
                tickFormatter={dataBreve}
                minTickGap={40}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v: number) => formatRendimento(v)}
                width={56}
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                axisLine={false}
                tickLine={false}
                domain={["auto", "auto"]}
              />
              <ReferenceLine y={0} stroke="hsl(var(--border))" />
              <Tooltip content={<TooltipAndamento etf={etf} />} />
              <Line type="monotone" dataKey="spy" stroke={COLORI.spy} strokeWidth={1.5} strokeDasharray="4 3"
                dot={false} isAnimationActive={false} connectNulls />
              {etf && (
                <Line type="monotone" dataKey="etf" stroke={COLORI.etf} strokeWidth={1.5} dot={false}
                  isAnimationActive={false} connectNulls />
              )}
              <Line type="monotone" dataKey="settore" stroke={COLORI.settore} strokeWidth={2.25} dot={false}
                isAnimationActive={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* I rendimenti su sei finestre, e lo scarto dall'S&P 500 sotto. */}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-sm tabular-nums">
            <thead>
              <tr className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground">
                <th className="py-1 text-left font-semibold" />
                {rendimenti.map((r) => (
                  <th key={r.finestra} className="py-1 text-right font-semibold">
                    {r.finestra === "ytd" ? "YTD" : r.finestra.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <RigaRendimenti nome="Settore" valori={rendimenti.map((r) => r.settore)} forte />
              {etf && <RigaRendimenti nome={etf} valori={rendimenti.map((r) => r.etf)} />}
              <RigaRendimenti nome="S&P 500" valori={rendimenti.map((r) => r.spy)} />
              <tr className="border-t border-border/60">
                <td className="py-1.5 pr-2 text-xs text-muted-foreground whitespace-nowrap">
                  <span className="inline-flex items-center gap-1">
                    Contro l'S&P 500
                    <InfoHint
                      label="Contro l'S&P 500"
                      text="Il rendimento del settore meno quello dello SPY nella stessa finestra, in punti percentuali. Positivo: il settore ha fatto meglio del mercato."
                    />
                  </span>
                </td>
                {rendimenti.map((r) => {
                  const d = r.settore != null && r.spy != null ? r.settore - r.spy : null;
                  return (
                    <td key={r.finestra} className={cn("py-1.5 text-right font-semibold", tonoRendimento(d))}>
                      {d == null ? "—" : `${formatRendimento(d).replace("%", "")} pp`}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[0.7059rem] leading-snug text-muted-foreground">
          Il settore è un indice a pesi uguali dei suoi {nTitoli} titoli: ogni giorno la media dei loro
          rendimenti{etf ? <>, mentre {etf} è pesato per capitalizzazione e segue di più i grandi nomi</> : null}.
          {a.aggiornato_al && <> Ultima seduta: {dataBreve(a.aggiornato_al)}.</>}
        </p>
      </CardContent>
    </Card>
  );
}

function RigaRendimenti({ nome, valori, forte }: { nome: string; valori: (number | null | undefined)[]; forte?: boolean }) {
  return (
    <tr className="border-t border-border/40">
      <td className={cn("py-1.5 pr-2 whitespace-nowrap", forte ? "font-semibold" : "text-muted-foreground")}>{nome}</td>
      {valori.map((v, i) => (
        <td key={i} className={cn("py-1.5 text-right", forte ? "font-bold" : "font-medium", tonoRendimento(v))}>
          {formatRendimento(v)}
        </td>
      ))}
    </tr>
  );
}

interface VoceTooltip {
  payload: { data: string; settore: number | null; etf: number | null; spy: number | null };
}

function TooltipAndamento({ active, payload, etf }: { active?: boolean; payload?: VoceTooltip[]; etf: string | null }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const righe: [string, number | null][] = [["Settore", p.settore], ...(etf ? [[etf, p.etf] as [string, number | null]] : []), ["S&P 500", p.spy]];
  return (
    <div className="rounded border bg-popover px-2.5 py-1.5 text-xs shadow-lg">
      <div className="mb-0.5 font-medium">{dataBreve(p.data)}</div>
      {righe.map(([nome, v]) => (
        <div key={nome} className="flex justify-between gap-4 tabular-nums">
          <span className="text-muted-foreground">{nome}</span>
          <span className={cn("font-bold", tonoRendimento(v))}>{formatRendimento(v)}</span>
        </div>
      ))}
    </div>
  );
}

/* ─── Ampiezza ──────────────────────────────────────────────────────────── */

function Metro({ titolo, q, spiegazione, tono }: {
  titolo: string;
  q: Quota;
  spiegazione: string;
  tono: "su" | "giu" | "neutro";
}) {
  const pct = quota(q);
  const barra = tono === "su" ? "bg-emerald-500" : tono === "giu" ? "bg-rose-500" : "bg-primary";
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="inline-flex min-w-0 items-center gap-1 text-muted-foreground">
          <span className="truncate">{titolo}</span>
          <InfoHint label={titolo} text={spiegazione} />
        </span>
        <span className="shrink-0 tabular-nums">
          <span className="font-bold">{pct == null ? "—" : `${pct}%`}</span>
          <span className="ml-1 text-xs text-muted-foreground">{q.n}/{q.su}</span>
        </span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className={cn("h-full rounded-full", barra)} style={{ width: `${pct ?? 0}%` }} />
      </div>
    </div>
  );
}

export function AmpiezzaCard({ a }: { a: AndamentoSettore }) {
  const p200 = quota(a.sopra_ema200);
  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <SectionTitle icon={Gauge} label="Ampiezza" className="mb-1" />
        <p className="mb-3 text-xs text-muted-foreground">
          Quanti titoli partecipano, non solo la media.
          {p200 != null && <> Sopra la media a 200 sedute: <strong className="text-foreground">{letturaAmpiezza(p200)}</strong>.</>}
        </p>
        <div className="space-y-3">
          <Metro titolo="Sopra la media a 200 sedute" q={a.sopra_ema200} tono="neutro"
            spiegazione="La quota di titoli che chiudono sopra la loro EMA a 200 sedute, cioè in tendenza di fondo positiva. Si contano solo i titoli con almeno 200 sedute di storia." />
          <Metro titolo="Sopra la media a 50 sedute" q={a.sopra_ema50} tono="neutro"
            spiegazione="La quota di titoli sopra la loro EMA a 50 sedute: la tendenza degli ultimi due-tre mesi." />
          <Metro titolo="Vicino ai massimi dell'anno" q={a.vicino_massimi} tono="su"
            spiegazione="Titoli entro il 5% dal loro massimo di chiusura degli ultimi 12 mesi." />
          <Metro titolo="Vicino ai minimi dell'anno" q={a.vicino_minimi} tono="giu"
            spiegazione="Titoli entro il 5% dal loro minimo di chiusura degli ultimi 12 mesi." />
          <Metro titolo="In rialzo nell'ultima seduta" q={a.in_rialzo} tono="su"
            spiegazione="Titoli che hanno chiuso l'ultima seduta sopra la chiusura precedente." />
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Chi traina e chi frena ────────────────────────────────────────────── */

export function TrainaFrenaCard({ rows }: { rows: SectorStockRow[] }) {
  const conRendimento = rows.filter((r) => r.r_1m != null);
  const ordinati = [...conRendimento].sort((a, b) => (b.r_1m ?? 0) - (a.r_1m ?? 0));
  // Con meno di dieci titoli le due liste si dividono il settore invece di
  // ripetere gli stessi nomi in entrambe.
  const k = Math.min(5, Math.ceil(ordinati.length / 2));
  const migliori = ordinati.slice(0, k);
  const peggiori = ordinati.slice(Math.max(k, ordinati.length - 5)).reverse();
  const scala = Math.max(1, ...[...migliori, ...peggiori].map((r) => Math.abs(r.r_1m ?? 0)));
  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <SectionTitle icon={Activity} label="Chi traina e chi frena · 1 mese" className="mb-3" />
        {conRendimento.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">Nessun rendimento calcolabile.</p>
        ) : (
          <div className="space-y-3">
            <ListaMovimenti titolo="Migliori" icona={TrendingUp} righe={migliori} scala={scala} />
            {peggiori.length > 0 && <ListaMovimenti titolo="Peggiori" icona={TrendingDown} righe={peggiori} scala={scala} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ListaMovimenti({ titolo, icona: Icona, righe, scala }: {
  titolo: string;
  icona: typeof TrendingUp;
  righe: SectorStockRow[];
  scala: number;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1 text-[0.6765rem] font-semibold uppercase tracking-wider text-muted-foreground">
        <Icona className="h-3.5 w-3.5" aria-hidden /> {titolo}
      </div>
      <ul className="space-y-1">
        {righe.map((r) => {
          const v = r.r_1m ?? 0;
          return (
            <li key={r.ticker}>
              <Link
                to={`/stocks/${encodeURIComponent(r.ticker)}`}
                className="grid grid-cols-[minmax(0,1fr)_4.5rem_3.75rem] items-center gap-2 rounded px-1 py-0.5 hover:bg-muted/40"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <StockIdentity ticker={r.ticker} name={r.name} forma="riga" />
                </span>
                <span className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
                  <span
                    className={cn("block h-full rounded-full", v >= 0 ? "bg-emerald-500" : "bg-rose-500")}
                    style={{ width: `${Math.min(100, (Math.abs(v) / scala) * 100)}%` }}
                  />
                </span>
                <span className={cn("text-right text-sm font-bold tabular-nums", tonoRendimento(v))}>
                  {formatRendimento(v)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ─── Segnali del mese ──────────────────────────────────────────────────── */

export function SegnaliSettoreCard({ s }: { s: SegnaliSettore }) {
  const altri = s.totale - s.rialzisti - s.ribassisti;
  return (
    <Card className="min-w-0">
      <CardContent className="p-4">
        <SectionTitle icon={BellRing} label={`Segnali · ${s.giorni} giorni`} className="mb-2" />
        {s.totale === 0 ? (
          <p className="text-sm italic text-muted-foreground">Nessun segnale sui titoli del settore nell'ultimo mese.</p>
        ) : (
          <>
            <div className="flex items-baseline justify-between text-sm tabular-nums">
              <span className="font-bold text-emerald-800 dark:text-emerald-400">
                {s.rialzisti} {s.rialzisti === 1 ? "rialzista" : "rialzisti"}
              </span>
              <span className="font-bold text-rose-600 dark:text-rose-400">
                {s.ribassisti} {s.ribassisti === 1 ? "ribassista" : "ribassisti"}
              </span>
            </div>
            <div className="mt-1 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
              <span className="bg-emerald-500" style={{ flex: s.rialzisti }} />
              <span className="bg-slate-400" style={{ flex: altri }} />
              <span className="bg-rose-500" style={{ flex: s.ribassisti }} />
            </div>
            <ul className="mt-3 space-y-1">
              {s.recenti.map((x, i) => (
                <li key={`${x.ticker}-${x.signal_name}-${i}`}>
                  <Link
                    to={`/stocks/${encodeURIComponent(x.ticker)}`}
                    className="flex items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-muted/40"
                  >
                    <span
                      className={cn(
                        "h-2 w-2 shrink-0 rounded-full",
                        x.tone === "bull" ? "bg-emerald-500" : x.tone === "bear" ? "bg-rose-500" : "bg-slate-400",
                      )}
                      aria-label={x.tone === "bull" ? "rialzista" : x.tone === "bear" ? "ribassista" : "neutro"}
                    />
                    <span className="w-16 shrink-0 font-bold tabular-nums">{x.ticker}</span>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground">
                      {x.signal_name ? detectorLabel(x.signal_name) : "—"}
                    </span>
                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {x.signal_date ? dataBreve(x.signal_date) : ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
