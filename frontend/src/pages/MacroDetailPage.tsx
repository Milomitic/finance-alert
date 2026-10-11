import { ArrowLeft, Building2, Globe } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MacroRelease } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useMacroDetail } from "@/hooks/useCalendar";
import { regionFlagAsset, regionLabel } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";
import { HintLabel } from "@/components/ui/info-hint";
import { formatMacroValue } from "@/lib/macroFormat";
import { MacroAnalisiCard } from "@/components/macro/MacroAnalisiCard";
import { formatConsenso } from "@/lib/consensoMacro";
import { formatVariazioneMacro, tonoControStima, tonoVariazione } from "@/lib/variazioneMacro";

/* ─── /macro/:seriesId — Investing-style indicator detail page ─────────── *
 *
 * Layout decisions (faithful to the user's reference screenshot):
 *  1. Sticky-ish header strip: ATTUALE · PREVISTO · PRECEDENTE side by
 *     side, with the actual styled bigger and tinted by surprise sign.
 *     This is the "primary" data cell — what the user comes here for.
 *  2. Two-column body: description text (left, narrative) +  metadata
 *     card (right, importance/region/currency/source).
 *  3. Range tabs (1A / 5A / MAX) above a recharts BarChart of the full
 *     observation history. Bars are positive/negative-tinted. A zero
 *     reference line splits the field for visual anchor.
 *  4. History table below the chart: Data · Periodo · Attuale · Previsto
 *     · Precedente. Expected stays "—" for past rows (we don't backfill
 *     consensus — see API docstring).
 */

const RANGES = [
  { id: "1y", label: "1A", years: 1 },
  { id: "5y", label: "5A", years: 5 },
  { id: "max", label: "MAX", years: null },
] as const;
type RangeId = (typeof RANGES)[number]["id"];
/** Il grafico: il livello, o la variazione sul periodo o sull'anno. */
type Modo = "level" | "periodo" | "anno";

export default function MacroDetailPage() {
  const { seriesId } = useParams<{ seriesId: string }>();
  const navigate = useNavigate();
  const id = seriesId ? parseInt(seriesId, 10) : undefined;
  const detail = useMacroDetail(id);

  const [range, setRange] = useState<RangeId>("5y");

  const filteredHistory = useMemo(() => {
    if (!detail.data) return [];
    const cfg = RANGES.find((r) => r.id === range);
    if (!cfg || cfg.years === null) return detail.data.history;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - cfg.years);
    return detail.data.history.filter(
      (h) => h.observation_period != null && new Date(h.observation_period) >= cutoff,
    );
  }, [detail.data, range]);

  // Chart data: oldest → newest for natural left-to-right reading.
  // Recharts iterates in array order, so this is the only place we
  // reverse the history (the API returns newest-first).
  // ⚠️ Il default segue il TIPO di valore, e non e una preferenza estetica.
  // Un livello disegnato su cinque anni e il muro piatto descritto piu sotto:
  // per le serie di livello si parte dalla variazione, che e la grandezza di
  // cui si parla. Percentuali, rendimenti e indici partono dal livello, che li
  // e' gia' quella giusta.
  //
  // `null` significa "non ancora scelto dall'utente": cosi il default puo
  // seguire il tipo appena i dati arrivano, senza sovrascrivere una scelta
  // fatta a mano.
  const [modeChoice, setModeChoice] = useState<Modo | null>(null);
  const chartData = useMemo(
    () =>
      filteredHistory
        .slice()
        .reverse()
        .filter((r) => r.actual_value != null && r.observation_period != null)
        .map((r) => ({
          date: r.observation_period as string,
          value: r.actual_value as number,
          period: r.period_label ?? "",
          periodo: r.variazione ?? null,
          anno: r.variazione_annua ?? null,
        })),
    [filteredHistory],
  );

  /* Il livello contro la variazione.
   *
   * ⚠️ Un LIVELLO disegnato a barre partendo da zero non mostra niente. Su
   * cinque anni di occupati non agricoli si vedono sessanta barre identiche,
   * perche la variazione mensile vale ~150 mila contro un livello di 159
   * milioni: un millesimo dell'altezza della barra. E la variazione e proprio
   * la domanda che si fa a quel dato.
   *
   * Quindi: barre per le variazioni, linea per i livelli, e la scelta e
   * esplicita invece che implicita nel tipo di grafico. La variazione e una
   * trasformazione NOSTRA — FRED conserva l'unita originale — e la didascalia
   * lo dice, perche un numero calcolato da noi non deve sembrare della fonte.
   */
  /* ⚠️ Le variazioni vengono dal backend, nell'unita' giusta (% su un indice
   * o un livello, punti su un tasso). Prima qui si sottraevano i livelli: sul
   * CPI una barra valeva «1.3» punti d'indice, un numero che nessuno usa. */
  const variazioniData = useMemo(
    () => ({
      periodo: chartData.filter((p) => p.periodo != null).map((p) => ({ ...p, value: p.periodo as number })),
      anno: chartData.filter((p) => p.anno != null).map((p) => ({ ...p, value: p.anno as number })),
    }),
    [chartData],
  );
  if (id == null || Number.isNaN(id)) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        Series id mancante o non valido.
      </div>
    );
  }

  if (detail.isLoading) {
    // Macro indicator detail = header KPIs + time-series chart. The
    // skeleton mirrors that two-block layout (was a spinner-line).
    return (
      <div className="space-y-3">
        <CardSkeleton rows={3} className="h-[140px]" />
        <CardSkeleton label="SERIE STORICA" rows={10} strongHeader className="h-[460px]" />
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="p-8">
        <div className="text-sm text-rose-600 dark:text-rose-400">
          Indicatore non trovato.
        </div>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Indietro
        </Button>
      </div>
    );
  }

  const d = detail.data;
  const flagAsset = regionFlagAsset(d.region);
  const valueKind = d.value_kind ?? "";
  const sourceScale = d.source_scale ?? null;
  // Il default segue il tipo di valore; una scelta manuale lo sovrascrive. Su
  // un indice o un livello si parte dalla variazione annua — la grandezza di
  // cui si parla (l'inflazione, non il livello dell'indice) — e su un tasso
  // dal livello, che li' e' gia' la misura.
  const unita = d.unita_variazione ?? "%";
  const tasso = valueKind === "pct" || valueKind === "yield";
  const mode: Modo =
    modeChoice ?? (tasso ? "level" : variazioniData.anno.length > 0 ? "anno" : "periodo");
  const plotted = mode === "level" ? chartData : variazioniData[mode];
  const latest = d.latest;
  const formato = d.formato_consenso ?? null;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header bar with back link + indicator title + flag.
          ⚠️ Era un `navigate(-1)`, che non porta da nessuna parte quando la
          pagina si apre da un link ricevuto e la storia del browser e vuota —
          proprio il caso in cui un ritorno serve. Ora punta al Calendario, da
          cui questa pagina si raggiunge, come fanno gia SectorDetail e
          InstitutionalDetail verso i loro elenchi. */}
      <div className="flex items-center gap-3">
        <Link
          to="/calendar"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline shrink-0"
        >
          <ArrowLeft className="h-4 w-4" />
          Calendario
        </Link>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {flagAsset ? (
            <img
              src={`/flags/${flagAsset}.svg`}
              alt={d.region}
              width={28}
              height={20}
              style={{ width: "28px", height: "20px", objectFit: "cover" }}
              className="rounded ring-1 ring-border shrink-0"
            />
          ) : null}
          <h1 className="text-xl font-semibold truncate">{d.label}</h1>
          <ImportanceStars importance={d.importance} />
        </div>
      </div>

      {/* Top KPI strip — the primary data the page is built around.
          Mirrors Investing's "Ultime Notizie [date] · Attuale · Previsto
          · Precedente" header where the latest release dominates and the
          three values sit on a single visual line. */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-baseline gap-3 mb-4 flex-wrap">
            {/* ⚠️ Diceva "Ultima release" seguita dalla data dell'OSSERVAZIONE,
                quindi il dato di agosto risultava pubblicato il 1 agosto: una
                lettura datata prima che il periodo che misura fosse finito.
                FRED consegna il periodo di riferimento e non la data di
                pubblicazione, quindi la seconda non si mostra finche' non
                arriva davvero dal calendario dei rilasci. */}
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              {latest?.publication_date ? "Pubblicato" : "Periodo di riferimento"}
            </div>
            <div className="text-sm font-medium tabular-nums">
              {latest?.publication_date
                ? formatMacroDate(latest.publication_date)
                : latest?.observation_period
                  ? formatMacroDate(latest.observation_period)
                  : "—"}
            </div>
            {latest?.period_label && (
              <div className="text-sm text-muted-foreground tabular-nums">
                ({latest.period_label})
              </div>
            )}
            {latest?.acquired_at && (
              <div
                className="text-xs text-muted-foreground"
                title="Quando abbiamo scaricato la serie. E' un'eta' della nostra copia, non una data della fonte."
              >
                · dati acquisiti {formatMacroDate(latest.acquired_at)}
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-6 sm:gap-8 [&>*]:min-w-0">
            <div className="flex min-w-0 flex-col gap-1">
              <KpiCell
                label="Attuale"
                value={latest?.actual_value}
                valueKind={valueKind}
                sourceScale={sourceScale}
                size="xl"
                tone={surpriseTone(latest)}
              />
              {/* La variazione e' il numero di cui si parla: in evidenza, sotto
                  il livello, nell'unita' giusta e col colore della direzione. */}
              {(latest?.variazione != null || latest?.variazione_annua != null) && (
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 tabular-nums">
                  {latest?.variazione != null && (
                    <span className={cn("text-base font-bold", tonoVariazione(latest.variazione))}>
                      {formatVariazioneMacro(latest.variazione, unita)}
                      <span className="ml-1 text-xs font-medium text-muted-foreground">sul periodo</span>
                    </span>
                  )}
                  {latest?.variazione_annua != null && (
                    <span className={cn("text-base font-bold", tonoVariazione(latest.variazione_annua))}>
                      {formatVariazioneMacro(latest.variazione_annua, unita)}
                      <span className="ml-1 text-xs font-medium text-muted-foreground">sull'anno</span>
                    </span>
                  )}
                </div>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-1" title="Il consenso del rilascio di questo periodo, dall'archivio. Forexfactory pubblica solo la settimana in corso: per i rilasci prima dell'11 ottobre 2026 non c'è.">
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Previsto</div>
              <div className="text-2xl font-bold tabular-nums leading-tight">
                {formatConsenso(latest?.previsto_consenso, formato, unita === "%")}
              </div>
              {latest?.attuale_consenso != null && (
                <div className={cn("text-sm font-bold tabular-nums", tonoControStima(latest.attuale_consenso, latest.previsto_consenso))}>
                  uscito {formatConsenso(latest.attuale_consenso, formato, unita === "%")}
                </div>
              )}
            </div>
            <KpiCell
              label="Precedente"
              value={latest?.previous_value}
              valueKind={valueKind}
              sourceScale={sourceScale}
              size="lg"
            />
          </div>
        </CardContent>
      </Card>

      {/* Two-column body: description (left, wide) + metadata (right) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 [&>*]:min-w-0">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Cos'è questo indicatore</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-foreground/85 leading-relaxed whitespace-pre-line">
              {d.description ?? "Descrizione non disponibile per questo indicatore."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Metadati</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <MetaRow label="Paese" value={regionLabel(d.region)} icon={<Globe className="h-3.5 w-3.5" />} />
            <MetaRow label="Valuta" value={d.currency ?? "—"} />
            <MetaRow
              label="Importanza"
              value={
                d.importance === "high"
                  ? "Alta"
                  : d.importance === "medium"
                    ? "Media"
                    : "Bassa"
              }
            />
            <MetaRow
              label="Fonte"
              value={d.source ?? "—"}
              icon={<Building2 className="h-3.5 w-3.5" />}
            />
            <MetaRow label="ID FRED" value={d.fred_series_id} mono />
            {d.upcoming.length > 0 && (
              <MetaRow
                label="Prossime release"
                value={d.upcoming.slice(0, 3).map(formatMacroDate).join(" · ")}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {d.analisi && (
        <MacroAnalisiCard a={d.analisi} unita={unita} valueKind={valueKind} sourceScale={sourceScale} />
      )}

      {/* Chart + range tabs */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0 pb-2">
          <CardTitle className="text-base">Storico osservazioni</CardTitle>
          <div className="flex items-center gap-3">
            <div className="flex gap-1">
              {(["level", "periodo", "anno"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setModeChoice(m)}
                  className={cn(
                    "px-2.5 py-1 text-xs rounded font-medium transition-colors",
                    m === mode
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted/50 text-muted-foreground hover:bg-muted",
                  )}
                >
                  {m === "level" ? "Livello" : m === "periodo" ? "Sul periodo" : "Sull'anno"}
                </button>
              ))}
            </div>
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setRange(r.id)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded font-medium transition-colors",
                  r.id === range
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
          </div>
        </CardHeader>
        <CardContent>
          {plotted.length === 0 ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-muted-foreground">
              Nessun dato nel range selezionato.
            </div>
          ) : (
            <div className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={plotted}
                  margin={{ top: 8, right: 12, left: 4, bottom: 4 }}
                >
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v: string) => formatMacroDate(v)}
                    tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                    interval="preserveStartEnd"
                    minTickGap={40}
                  />
                  <YAxis
                    // Un livello non parte da zero: forzarcelo e' cio' che
                    // schiaccia cinque anni di occupati in un muro piatto.
                    domain={mode === "level" ? ["auto", "auto"] : undefined}
                    tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                    tickFormatter={(v: number) =>
                      mode === "level" ? formatMacroValue(v, valueKind, sourceScale) : formatVariazioneMacro(v, unita, 1)
                    }
                    width={64}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--muted) / 0.4)" }}
                    content={
                      <ChartTooltip
                        valueKind={valueKind}
                        sourceScale={sourceScale}
                        variazione={mode === "level" ? null : unita}
                      />
                    }
                  />
                  {mode !== "level" && (
                    <ReferenceLine y={0} stroke="hsl(var(--border))" />
                  )}
                  {mode === "level" && (
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  )}
                  {mode !== "level" && (
                  <Bar dataKey="value" radius={[2, 2, 0, 0]}>
                    {/* Rosa/smeraldo: la DIREZIONE. Il rosso (`destructive`)
                        e' riservato a cio' che e' rotto (CLAUDE.md). */}
                    {plotted.map((p, i) => (
                      <Cell key={i} fill={p.value >= 0 ? "rgb(16 185 129)" : "rgb(244 63 94)"} />
                    ))}
                  </Bar>
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* History table — Investing's "Storico" */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tabella storica</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th
                  className="text-left font-semibold pb-2"
                >
                  <HintLabel text="Il periodo che il dato misura. La data di pubblicazione non e' fornita dalla fonte per le osservazioni storiche.">Periodo osservato</HintLabel>
                </th>
                <th className="text-left font-semibold pb-2 hidden sm:table-cell">Periodo</th>
                <th className="text-right font-semibold pb-2">Valore</th>
                <th className="text-right font-semibold pb-2">Sul periodo</th>
                <th className="text-right font-semibold pb-2">Sull'anno</th>
                <th className="text-right font-semibold pb-2 hidden sm:table-cell">
                  <HintLabel text="Il consenso del rilascio di quel periodo e il dato uscito, nell'unità del consenso, dall'archivio. Forexfactory pubblica solo la settimana in corso: i rilasci prima dell'11 ottobre 2026 restano «—».">Previsto</HintLabel>
                </th>
                <th className="text-right font-semibold pb-2 hidden sm:table-cell">Uscito</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.slice(0, 50).map((r) => (
                <tr
                  key={r.observation_period ?? r.period_label}
                  className="border-b border-border/40 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-2 text-left">
                    {r.observation_period ? formatMacroDate(r.observation_period) : "—"}
                  </td>
                  <td className="py-2 text-left text-muted-foreground hidden sm:table-cell">
                    {r.period_label ?? "—"}
                  </td>
                  <td className="py-2 text-right text-muted-foreground">
                    {r.actual_value != null
                      ? formatMacroValue(r.actual_value, valueKind, sourceScale)
                      : "—"}
                  </td>
                  <td className={cn("py-2 text-right font-bold", tonoVariazione(r.variazione))}>
                    {formatVariazioneMacro(r.variazione, unita)}
                  </td>
                  <td className={cn("py-2 text-right font-semibold", tonoVariazione(r.variazione_annua))}>
                    {formatVariazioneMacro(r.variazione_annua, unita)}
                  </td>
                  <td className="py-2 text-right text-muted-foreground hidden sm:table-cell">
                    {formatConsenso(r.previsto_consenso, formato, unita === "%")}
                  </td>
                  <td className={cn("py-2 text-right font-bold hidden sm:table-cell", tonoControStima(r.attuale_consenso, r.previsto_consenso))}>
                    {formatConsenso(r.attuale_consenso, formato, unita === "%")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredHistory.length > 50 && (
            <div className="text-xs text-muted-foreground mt-2 text-center">
              Mostrate 50 release più recenti del range selezionato (totale {filteredHistory.length}).
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-center pb-6">
        <Link to="/calendar" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Torna al calendario
        </Link>
      </div>
    </div>
  );
}

/* ─── Sub-components ───────────────────────────────────────────────────── */

function KpiCell({
  label,
  value,
  valueKind,
  sourceScale,
  size = "lg",
  tone,
}: {
  label: string;
  value: number | null | undefined;
  valueKind: string;
  sourceScale?: string | null;
  size?: "lg" | "xl";
  tone?: "pos" | "neg" | "neutral";
}) {
  const sizeCls = size === "xl" ? "text-3xl" : "text-2xl";
  const toneCls =
    tone === "pos"
      ? "text-emerald-800 dark:text-emerald-400"
      : tone === "neg"
        ? "text-rose-600 dark:text-rose-400"
        : "text-foreground";
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn(sizeCls, "font-bold tabular-nums leading-tight", toneCls)}>
        {value != null ? formatMacroValue(value, valueKind, sourceScale) : "—"}
      </div>
    </div>
  );
}

function MetaRow({
  label,
  value,
  icon,
  mono,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1">
        {icon}
        {label}
      </span>
      <span className={cn("text-right truncate", mono && "font-mono text-xs")}>
        {value}
      </span>
    </div>
  );
}

function ImportanceStars({ importance }: { importance: "high" | "medium" | "low" }) {
  const filled = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      className="inline-flex items-center gap-0.5 ml-2"
      title={`Importanza: ${importance}`}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            "text-base leading-none",
            i < filled ? "text-amber-500" : "text-muted-foreground",
          )}
        >
          ★
        </span>
      ))}
    </span>
  );
}

interface ChartTooltipPayloadEntry {
  payload: { date: string; value: number; period: string };
}

function ChartTooltip({
  active,
  payload,
  valueKind,
  sourceScale,
  variazione = null,
}: {
  active?: boolean;
  payload?: ChartTooltipPayloadEntry[];
  valueKind: string;
  sourceScale?: string | null;
  /** L'unita' della variazione quando il grafico ne mostra una, null sul livello. */
  variazione?: string | null;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded border bg-popover px-2.5 py-1.5 text-xs shadow-lg">
      <div className="font-medium">{formatMacroDate(p.date)}</div>
      {p.period && <div className="text-muted-foreground tabular-nums">{p.period}</div>}
      <div className={cn("font-bold tabular-nums mt-0.5", variazione && tonoVariazione(p.value))}>
        {variazione ? formatVariazioneMacro(p.value, variazione) : formatMacroValue(p.value, valueKind, sourceScale)}
      </div>
    </div>
  );
}

/* ─── helpers (mirror DayDetailPanel internals) ────────────────────────── */

function surpriseTone(r: MacroRelease | null | undefined): "pos" | "neg" | "neutral" {
  if (!r || r.actual_value == null || r.expected_value == null) return "neutral";
  if (r.actual_value > r.expected_value) return "pos";
  if (r.actual_value < r.expected_value) return "neg";
  return "neutral";
}

function formatMacroDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });
}

