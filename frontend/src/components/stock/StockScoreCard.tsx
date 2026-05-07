import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";

import type {
  ScoreBreakdownComponent,
  ScoreBreakdownMeta,
  StockScore,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useStockMultiTfKpis } from "@/hooks/useMultiTfKpis";
import { useStockScore } from "@/hooks/useStockScore";
import {
  CATEGORY_LABEL,
  RISK_LABEL,
  RISK_TONE,
  scoreBgColor,
  scoreColor,
  scoreHex,
  scoreLabel,
} from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

/* ─── Component label map ───────────────────────────────────────────────── */
/* Pretty names + 1-line descriptions for the 43 components emitted by the
 * backend score engine v2 (see `backend/app/services/score_service.py`).
 * The component KEYS come from `_Component("name", ...)` calls — keep this
 * map in sync when adding/removing pillar inputs. Unknown keys fall back
 * to a humanized version of the snake-case name (`name.replace(/_/g," ")`),
 * which keeps the UI working even if the backend introduces a key the
 * frontend doesn't yet know about. */

interface ComponentMeta {
  label: string;
  /** What this component measures, in one sentence — shown in the
   *  tooltip-of-tooltip on the row's `title` attribute so a curious user
   *  can hover the row and learn what the metric represents. */
  hint: string;
  /** Format hint for the raw value: how to render `comp.raw`. */
  format: "pct" | "pct_raw" | "ratio" | "usd" | "num" | "score" | "count";
}

const COMPONENT_META: Record<string, ComponentMeta> = {
  // ── Profitability (V3.2 — magnitude side of old Quality) ────
  roe: { label: "ROE", hint: "Return on Equity — utile / equity", format: "pct" },
  roa: { label: "ROA", hint: "Return on Assets — utile / asset totali", format: "pct" },
  profit_margin: { label: "Profit margin", hint: "Utile netto / ricavi", format: "pct" },
  operating_margin: { label: "Operating margin", hint: "Utile operativo / ricavi", format: "pct" },
  gross_margin: { label: "Gross margin", hint: "Profitto lordo / ricavi", format: "pct" },
  insider_holdings: { label: "% insider", hint: "Quota detenuta da insider — allineamento incentivi", format: "pct" },
  institutional_holdings: { label: "% istituzionali", hint: "Quota detenuta da fondi/ETF/banche", format: "pct" },
  // ── Sustainability (V3.2 — durability side of old Quality) ──
  fcf: { label: "Free cash flow", hint: "Flusso di cassa libero (TTM) — positivo = genera cassa", format: "usd" },
  fcf_to_ni: { label: "FCF / Net Income", hint: "Earnings quality — sopra 1 = utili supportati da cassa vera", format: "ratio" },
  earnings_stability: { label: "Stabilità utili 5y", hint: "1 − coefficiente di variazione del net_income negli ultimi 5 anni — alto = utili regolari", format: "ratio" },
  margin_trend: { label: "Trend margini 3y", hint: "Pendenza regressiva del profit margin — positivo = margini in miglioramento", format: "pct_raw" },
  dividend_coverage: { label: "Dividend coverage", hint: "EPS / DPS — sopra 3x = dividendo molto sicuro, sotto 1x = pagato a debito", format: "ratio" },
  debt_equity: { label: "Debt / Equity", hint: "Leva finanziaria — debito totale / equity", format: "ratio" },
  current_ratio: { label: "Current ratio", hint: "Liquidità a breve — attivo corrente / passivo corrente", format: "ratio" },
  quick_ratio: { label: "Quick ratio", hint: "Liquidità stringente — esclude inventario", format: "ratio" },
  overall_risk: { label: "Risk score (Yahoo)", hint: "Yahoo overall risk 1-10 — basso = governance solida", format: "num" },
  // ── Growth ──────────────────────────────────────────────────
  revenue_growth: { label: "Revenue growth (YoY)", hint: "Crescita ricavi anno-su-anno", format: "pct" },
  revenue_cagr_3y: { label: "Revenue CAGR 3y", hint: "Crescita media composta dei ricavi su 3 anni", format: "pct" },
  earnings_growth: { label: "EPS growth (YoY)", hint: "Crescita EPS anno-su-anno", format: "pct" },
  qoq_earnings_growth: { label: "EPS growth (QoQ)", hint: "Crescita EPS trimestre-su-trimestre", format: "pct" },
  eps_forward_growth: { label: "EPS forward / TTM", hint: "EPS atteso prossimi 12m vs TTM — accelerazione attesa", format: "pct" },
  earnings_beats: { label: "Earnings beats", hint: "Quota di trimestri recenti sopra le attese", format: "pct" },
  // ── Value ───────────────────────────────────────────────────
  pe: { label: "P/E (TTM)", hint: "Price/Earnings — valutazione vs utili realizzati", format: "ratio" },
  forward_pe: { label: "Forward P/E", hint: "Price/Earnings sull'EPS atteso 12m", format: "ratio" },
  peg: { label: "PEG", hint: "P/E ÷ growth — sotto 1 = sottovalutato vs crescita", format: "ratio" },
  pb: { label: "P/B", hint: "Price/Book — valutazione vs equity", format: "ratio" },
  ps: { label: "P/S", hint: "Price/Sales — valutazione vs ricavi", format: "ratio" },
  ev_ebitda: { label: "EV/EBITDA", hint: "Valutazione capital-structure-agnostic", format: "ratio" },
  ev_revenue: { label: "EV/Revenue", hint: "Variante EV-based del P/S", format: "ratio" },
  dividend_yield: { label: "Dividend yield", hint: "Dividendo annualizzato / prezzo", format: "pct_raw" },
  payout_ratio: { label: "Payout ratio", hint: "% utili distribuiti come dividendi", format: "pct" },
  // ── Momentum ────────────────────────────────────────────────
  change_52w: { label: "52w change", hint: "Performance prezzo nelle 52 settimane", format: "pct" },
  momentum_30d: { label: "30d momentum", hint: "Variazione % ultimi 30 giorni", format: "pct" },
  momentum_90d: { label: "90d momentum", hint: "Variazione % ultimi 90 giorni", format: "pct" },
  relative_strength: { label: "Relative strength vs S&P", hint: "Sovra/sottoperformance vs S&P500 nelle 52w", format: "pct" },
  rsi: { label: "RSI(14)", hint: "Oscillatore 0-100 — sopra 50 = momentum positivo", format: "num" },
  macd: { label: "MACD", hint: "Sopra signal e zero = momentum confermato", format: "score" },
  trend_stack: { label: "Trend stack (SMA)", hint: "Allineamento SMA 20/50/200 — pieno = uptrend confermato", format: "score" },
  price_vs_sma200: { label: "Price vs SMA200", hint: "% sopra/sotto SMA 200 giorni", format: "pct" },
  bb_position: { label: "BB position (%B)", hint: "Posizione del prezzo nelle Bande di Bollinger", format: "pct_raw" },
  adx: { label: "ADX(14)", hint: "Forza del trend — sopra 25 = trend tradeabile", format: "num" },
  short_percent_of_float: { label: "Short % of float", hint: "Pressione short — alto = sentiment ribassista", format: "pct" },
  // ── Sentiment ───────────────────────────────────────────────
  recommendation_mean: { label: "Analyst rating", hint: "Media analisti 1-5 — basso = Buy", format: "num" },
  net_upgrades_90d: { label: "Net upgrades 90d", hint: "Upgrade − downgrade negli ultimi 90 giorni", format: "count" },
  price_target_upside: { label: "Target upside", hint: "Differenza % tra target medio analisti e prezzo", format: "pct" },
  news_polarity: { label: "News polarity", hint: "Mix bullish/bearish dei titoli recenti, scala -100 / +100", format: "num" },
  news_volume: { label: "News volume 30d", hint: "Numero di articoli ultimi 30 giorni", format: "count" },
};

function metaFor(key: string): ComponentMeta {
  return (
    COMPONENT_META[key] ?? {
      label: key.replace(/_/g, " "),
      hint: "",
      format: "num",
    }
  );
}


/* ─── Multi-timeframe technical strip ───────────────────────────────────── */
/* Compact 6-column header that shows the composite technical score per
 * timeframe (30m/1h/1d/1w/1m/all). Replaces the standalone
 * MultiTimeframeKpisCard at the top of the detail page — same data,
 * but inline in the score card so the user sees Profittabilità/
 * Sostenibilità (fundamentals-driven) and the multi-TF technical
 * outlook (chart-driven) side by side without scrolling. */

const TF_PRIORITY: Record<string, "primary" | "secondary"> = {
  "30m": "secondary",
  "1h": "primary",
  "1d": "primary",
  "1w": "secondary",
  "1m": "primary",
  "all": "primary",
};

function compositeTone(score: number): string {
  // Backend emits -3..+3 composite. Tinted so the user reads bullishness
  // at a glance without parsing the number.
  if (score >= 2) return "bg-emerald-500/25 text-emerald-700 dark:text-emerald-300 border-emerald-300/50";
  if (score === 1) return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-300/30";
  if (score === 0) return "bg-muted/40 text-muted-foreground border-border/40";
  if (score === -1) return "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-300/30";
  return "bg-rose-500/25 text-rose-700 dark:text-rose-300 border-rose-300/50";
}

function MultiTfStrip({ ticker, kind }: { ticker: string; kind: "stock" | "market" }) {
  const stockQ = useStockMultiTfKpis(kind === "stock" ? ticker : "");
  // For now we only mount the stock variant; the kind="market" hook will
  // be consumed by MarketDetailPage in a sibling change. The hook is
  // gated on the ticker prop being non-empty so the unused branch never
  // triggers a request.
  const data = stockQ.data;
  if (stockQ.isLoading || !data || data.items.length === 0) {
    return (
      <div className="grid grid-cols-6 gap-1 text-center">
        {["30m", "1h", "1d", "1w", "1m", "All"].map((tf) => (
          <div
            key={tf}
            className="h-9 rounded bg-muted/20 border border-border/30 animate-pulse"
          />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-6 gap-1">
      {data.items.map((it) => {
        const prio = TF_PRIORITY[it.timeframe] ?? "secondary";
        const tone = compositeTone(it.composite_score);
        return (
          <Tooltip key={it.timeframe}>
            <TooltipTrigger asChild>
              <div
                className={cn(
                  "px-1.5 py-1 rounded border text-center cursor-help transition-opacity",
                  tone,
                  prio === "secondary" && "opacity-70",
                )}
              >
                <div className="text-[10px] uppercase tracking-wider font-bold leading-none">
                  {it.timeframe === "all" ? "All" : it.timeframe}
                </div>
                <div className="text-sm font-bold tabular-nums leading-none mt-0.5">
                  {it.composite_score >= 0 ? "+" : ""}
                  {it.composite_score}
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="text-[11px] space-y-0.5">
              <div className="font-bold uppercase tracking-wider">
                Timeframe {it.timeframe}
              </div>
              <div>RSI(14): {it.rsi != null ? it.rsi.toFixed(1) : "—"}</div>
              <div>
                SMA20/50/200:{" "}
                {it.sma20_above ? "✓" : "✗"} /{" "}
                {it.sma50_above ? "✓" : "✗"} /{" "}
                {it.sma200_above ? "✓" : "✗"}
              </div>
              <div>BB pos: {it.bb_position != null ? `${it.bb_position.toFixed(0)}%` : "—"}</div>
              <div>MACD: {it.macd_tone}</div>
              <div className="pt-1 mt-1 border-t border-border/40 font-semibold">
                Outlook: {it.composite_label.replace("_", " ")}
              </div>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}


interface Props {
  ticker: string;
}


/* ─── Time helpers ──────────────────────────────────────────────────────── */

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 1) return "ora";
  if (diffMin < 60) return `${Math.max(1, Math.round(diffMin))} min fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  const diffD = diffH / 24;
  if (diffD < 30) return `${Math.round(diffD)}g fa`;
  return `${Math.round(diffD / 30)} mesi fa`;
}

/* ─── Composite score gauge (semicircle SVG) ────────────────────────────── */
/* Pure SVG arc, 180°, 0–100. Single solid color picked from the score's tone
 * (rose / amber / sky / emerald) so the visual matches the number color and
 * the spark bars in the dashboard rows. The big composite number sits in the
 * center; the score label ("Buono", "Eccellente", ...) below it.
 *
 * Chosen vs gradient stops for clarity: a uniform tone says "this score is
 * X strength" — a gradient would say "this dial spans the full range" which
 * is a different statement. */

interface GaugeProps {
  score: number;
  size?: number;
}

function ScoreGauge({ score, size = 180 }: GaugeProps) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 12; // 12px stroke + tiny padding
  const stroke = 12;
  const clamped = Math.max(0, Math.min(100, score));
  // Arc spans 180° (left half-circle): angle 0 at the left, 180 at the right.
  // We sweep `pct` of that range from the left end.
  // SVG: pathLength + stroke-dasharray gives us a clean way to render a partial arc.
  // Build a half-circle path going from (cx - r, cy) clockwise to (cx + r, cy).
  const startX = cx - radius;
  const startY = cy;
  const endX = cx + radius;
  const endY = cy;
  // We use pathLength=100 so dasharray maps directly to percent.
  const dashLen = clamped;
  const fillColor = scoreHex(score);

  return (
    <svg
      width={size}
      height={size / 2 + 16}
      viewBox={`0 0 ${size} ${size / 2 + 16}`}
      className="overflow-visible"
      role="img"
      aria-label={`Score ${score.toFixed(1)} su 100`}
    >
      {/* Track */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.12}
        strokeWidth={stroke}
        strokeLinecap="round"
        className="text-foreground"
      />
      {/* Fill */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke={fillColor}
        strokeWidth={stroke}
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${dashLen} 100`}
        style={{ transition: "stroke-dasharray 400ms ease-out" }}
      />
      {/* Tick marks at 40 / 60 / 80 — the threshold boundaries */}
      {[40, 60, 80].map((t) => {
        const angle = Math.PI * (1 - t / 100); // π at 0, 0 at 100
        const tx = cx + Math.cos(angle) * radius;
        const ty = cy - Math.sin(angle) * radius;
        const tx2 = cx + Math.cos(angle) * (radius - stroke / 2 - 2);
        const ty2 = cy - Math.sin(angle) * (radius - stroke / 2 - 2);
        return (
          <line
            key={t}
            x1={tx}
            y1={ty}
            x2={tx2}
            y2={ty2}
            stroke="currentColor"
            strokeOpacity={0.35}
            strokeWidth={1}
            className="text-foreground"
          />
        );
      })}
    </svg>
  );
}

/* ─── Sub-score row with breakdown tooltip ──────────────────────────────── */

const PILLAR_ORDER: Array<keyof StockScore["sub_scores"]> = [
  "profitability",
  "sustainability",
  "growth",
  "value",
  "momentum",
  "sentiment",
];

/** Render a raw component value per its declared format. None / NaN /
 *  Infinity collapse to "n/d" so missing inputs are visually distinct
 *  from real zero values. */
function fmtRaw(v: ScoreBreakdownComponent["raw"], format: ComponentMeta["format"]): string {
  if (v == null) return "n/d";
  if (typeof v === "string") return v;
  if (!Number.isFinite(v)) return "n/d";
  const n = v as number;
  switch (format) {
    case "pct":
      // Backend emits fractions for ratios (0.27 = 27%).
      return `${(n * 100).toFixed(1)}%`;
    case "pct_raw":
      // Already-percent values (e.g. dividend_yield, bb_position).
      return `${n.toFixed(2)}%`;
    case "ratio":
      return n.toFixed(2);
    case "usd": {
      const abs = Math.abs(n);
      const sign = n < 0 ? "-" : "";
      if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
      if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
      if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
      return `${sign}$${abs.toLocaleString()}`;
    }
    case "score":
      // 0-100-ish helper score (e.g. trend_stack derived from SMA alignment).
      return n.toFixed(0);
    case "count":
      return Math.round(n).toString();
    case "num":
    default:
      return Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2);
  }
}

/** Type-guard separating component entries from the optional `_meta` row. */
function isComponent(
  entry: ScoreBreakdownComponent | ScoreBreakdownMeta,
): entry is ScoreBreakdownComponent {
  return "score" in entry && "weight" in entry;
}

function isMeta(
  entry: ScoreBreakdownComponent | ScoreBreakdownMeta,
): entry is ScoreBreakdownMeta {
  return "components_present" in entry;
}

interface SubScoreRowProps {
  pillar: keyof StockScore["sub_scores"];
  score: number | null;
  components:
    | Record<string, ScoreBreakdownComponent | ScoreBreakdownMeta>
    | undefined;
}

function SubScoreRow({ pillar, score, components }: SubScoreRowProps) {
  const label = CATEGORY_LABEL[pillar];
  const isMissing = score == null;
  const fillCls = isMissing ? "bg-muted" : scoreBgColor(score);
  const valueCls = isMissing ? "text-muted-foreground" : scoreColor(score);
  const widthPct = isMissing ? 0 : Math.max(0, Math.min(100, score));

  // Split the breakdown dict into the per-component entries and the
  // optional `_meta` row. The components are sorted: present first
  // (descending by weight × score so the biggest contributors lead),
  // missing last so the user reads the active drivers first.
  let presentList: Array<[string, ScoreBreakdownComponent]> = [];
  let missingList: Array<[string, ScoreBreakdownComponent]> = [];
  let meta: ScoreBreakdownMeta | null = null;
  if (components) {
    for (const [name, entry] of Object.entries(components)) {
      if (isMeta(entry)) {
        meta = entry;
      } else if (isComponent(entry)) {
        if (entry.present) presentList.push([name, entry]);
        else missingList.push([name, entry]);
      }
    }
    // Sort present components by their effective contribution (score × weight)
    // descending. Heaviest signal drivers up top.
    presentList = presentList.sort((a, b) => {
      const sa = (a[1].score ?? 0) * a[1].weight;
      const sb = (b[1].score ?? 0) * b[1].weight;
      return sb - sa;
    });
    missingList = missingList.sort((a, b) => b[1].weight - a[1].weight);
  }

  const trigger = (
    <div className="grid grid-cols-[80px_1fr_38px] items-center gap-2 py-1 cursor-help">
      <span className="text-xs font-medium text-muted-foreground truncate">
        {label}
      </span>
      <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", fillCls)}
          style={{ width: `${widthPct}%` }}
        />
      </div>
      <span
        className={cn(
          "text-sm font-bold tabular-nums text-right",
          valueCls,
        )}
      >
        {isMissing ? "—" : Math.round(score!)}
      </span>
    </div>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent
        side="left"
        align="start"
        sideOffset={8}
        collisionPadding={12}
        className="w-[22rem] p-3"
      >
        <div className="space-y-2">
          {/* Header — pillar name + final pillar score */}
          <div className="flex items-baseline justify-between gap-3 pb-1.5 border-b border-border/50">
            <span className="text-xs font-bold uppercase tracking-wider">
              {label}
            </span>
            <span
              className={cn(
                "text-sm font-bold tabular-nums",
                isMissing ? "text-muted-foreground" : scoreColor(score!),
              )}
            >
              {isMissing ? "n/d" : `${Math.round(score!)}/100`}
            </span>
          </div>

          {isMissing ? (
            <div className="text-xs text-muted-foreground">
              Dati insufficienti per questo pilastro — escluso dal calcolo,
              i pesi vengono rinormalizzati sugli altri pilastri.
            </div>
          ) : presentList.length === 0 && missingList.length === 0 ? (
            <div className="text-xs text-muted-foreground">
              Dettaglio componenti non disponibile.
            </div>
          ) : (
            <>
              {/* Active components — these contribute to the final pillar
                  score. Sorted by effective contribution (score × weight)
                  desc so the user sees the strongest drivers first. */}
              {presentList.length > 0 && (
                <ul className="space-y-1 text-[11px]">
                  {presentList.map(([name, comp]) => {
                    const m = metaFor(name);
                    const compScore = comp.score ?? 0;
                    return (
                      <li
                        key={name}
                        className="grid grid-cols-[1fr_auto_auto_auto] items-baseline gap-2"
                        title={
                          comp.sector_median != null
                            ? `${m.hint}

Vs settore: mediana ${fmtRaw(comp.sector_median, m.format)}`
                            : m.hint
                        }
                      >
                        <span className="text-foreground/85 truncate">
                          {m.label}
                        </span>
                        <span className="tabular-nums text-muted-foreground/80 shrink-0">
                          {fmtRaw(comp.raw, m.format)}
                          {comp.sector_median != null && (
                            <span className="text-[10px] text-muted-foreground/50 ml-1">
                              ({fmtRaw(comp.sector_median, m.format)})
                            </span>
                          )}
                        </span>
                        <span
                          className={cn(
                            "tabular-nums font-semibold shrink-0 px-1 rounded",
                            scoreBgColor(compScore),
                          )}
                          title={`Score componente ${Math.round(compScore)}/100`}
                        >
                          {Math.round(compScore)}
                        </span>
                        <span
                          className="tabular-nums text-muted-foreground/60 shrink-0 text-[10px]"
                          title={`Peso ${(comp.weight * 100).toFixed(0)}% nel pilastro`}
                        >
                          ×{(comp.weight * 100).toFixed(0)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}

              {/* Missing components — listed but visually de-emphasized
                  to make clear they did NOT influence the pillar score
                  (the aggregator excludes them from numerator AND
                  denominator). The user can see at a glance "I'd score
                  higher if I had this data, but the absence isn't
                  hurting me right now". */}
              {missingList.length > 0 && (
                <details className="text-[11px]">
                  <summary className="cursor-pointer text-muted-foreground/70 hover:text-muted-foreground italic select-none">
                    {missingList.length} componente{missingList.length === 1 ? "" : "i"} senza dato
                    <span className="ml-1 text-muted-foreground/50">
                      (esclus{missingList.length === 1 ? "o" : "i"} dal calcolo)
                    </span>
                  </summary>
                  <ul className="mt-1 space-y-0.5 text-muted-foreground/70">
                    {missingList.map(([name, comp]) => {
                      const m = metaFor(name);
                      return (
                        <li
                          key={name}
                          className="flex items-baseline justify-between gap-2 italic"
                          title={m.hint}
                        >
                          <span className="truncate">{m.label}</span>
                          <span className="tabular-nums text-[10px] shrink-0">
                            ×{(comp.weight * 100).toFixed(0)} · n/d
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </details>
              )}

              {/* Footer — meta from the backend aggregator: how many
                  components actually fed into the score, and the total
                  weight that was active. Communicates the
                  missing-data-neutralization invariant explicitly. */}
              {meta && (
                <div className="pt-1.5 border-t border-border/40 text-[10px] text-muted-foreground/80 italic">
                  {meta.components_present} di {meta.components_total}{" "}
                  componenti attivi
                  {meta.components_present < meta.components_total &&
                    " · pesi rinormalizzati"}
                </div>
              )}
            </>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/* ─── Card body wrappers ────────────────────────────────────────────────── */

function CardShell({
  children,
  onRefresh,
  isFetching,
}: {
  children: React.ReactNode;
  onRefresh?: () => void;
  isFetching?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-3">
        <SectionTitle
          icon={Sparkles}
          label="Stock score"
          className="mb-2"
          right={
            onRefresh ? (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isFetching}
                className={cn(
                  "p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50",
                )}
                title="Ricarica score"
                aria-label="Ricarica score"
              >
                <RefreshCw
                  className={cn(
                    "h-3.5 w-3.5",
                    isFetching && "animate-spin",
                  )}
                />
              </button>
            ) : undefined
          }
        />
        {children}
      </CardContent>
    </Card>
  );
}

/* ─── Main component ────────────────────────────────────────────────────── */

export function StockScoreCard({ ticker }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, noScoreYet, refetch } =
    useStockScore(ticker);

  const onRefresh = () => {
    qc.invalidateQueries({ queryKey: ["stock-score", ticker] });
    refetch();
  };

  if (isLoading) {
    return (
      <CardShell>
        <div className="space-y-3">
          <div className="h-[110px] rounded bg-muted/40 animate-pulse" />
          <div className="h-5 w-24 mx-auto rounded bg-muted/40 animate-pulse" />
          <div className="space-y-2 mt-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-4 w-full rounded bg-muted/30 animate-pulse"
              />
            ))}
          </div>
        </div>
      </CardShell>
    );
  }

  if (noScoreYet) {
    return (
      <CardShell onRefresh={onRefresh} isFetching={false}>
        <div className="py-6 text-center text-xs text-muted-foreground leading-relaxed">
          Score non ancora calcolato per questo ticker — sarà disponibile al
          prossimo scan.
        </div>
      </CardShell>
    );
  }

  if (isError || !data) {
    return (
      <CardShell onRefresh={onRefresh} isFetching={false}>
        <div className="py-6 text-center text-xs text-muted-foreground">
          Errore nel caricamento dello score.
        </div>
      </CardShell>
    );
  }

  const composite = data.composite;
  const compTone = scoreColor(composite);

  return (
    <CardShell onRefresh={onRefresh}>
      {/* Gauge + composite number — gauge shrunk 180->130 to give the
          card a much shorter footprint per user feedback. The label
          ("Buono"/"Ottimo"/...) was moved next to the risk chip
          horizontally so the gauge area stays vertically tight. */}
      <div className="flex items-center justify-center gap-3">
        <div className="relative shrink-0">
          <ScoreGauge score={composite} size={130} />
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-0.5">
            <span
              className={cn(
                "text-2xl font-bold tabular-nums leading-none",
                compTone,
              )}
            >
              {composite.toFixed(1)}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-start gap-1.5">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
            {scoreLabel(composite)}
          </span>
          <span
            className={cn(
              "px-2 py-0.5 rounded border text-[11px] uppercase tracking-wider font-semibold",
              RISK_TONE[data.risk_tier],
            )}
          >
            {RISK_LABEL[data.risk_tier]}
          </span>
        </div>
      </div>

      {/* Multi-timeframe technical strip - integrated from the old
          standalone MultiTimeframeKpisCard. Compact -3..+3 composite
          per TF with hover tooltip that drills into RSI/SMA/BB/MACD. */}
      <div className="mt-2 border-t border-border/40 pt-2">
        <div className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground/70 mb-1.5">
          Technical outlook per timeframe
        </div>
        <MultiTfStrip ticker={ticker} kind="stock" />
      </div>

      {/* 6 pillar bars in a 2-column grid - splits Profittabilità +
          Sostenibilità from the V3.2 refactor onto the left, leaves
          Growth + Value + Momentum + Sentiment on a balanced layout. */}
      <div className="mt-2 border-t border-border/40 pt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-0.5">
        {PILLAR_ORDER.map((pillar) => (
          <SubScoreRow
            key={pillar}
            pillar={pillar}
            score={data.sub_scores[pillar]}
            components={data.breakdown[pillar]}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
        <span title={new Date(data.computed_at).toLocaleString("it-IT")}>
          Calcolato {formatRelative(data.computed_at)}
        </span>
      </div>
    </CardShell>
  );
}
