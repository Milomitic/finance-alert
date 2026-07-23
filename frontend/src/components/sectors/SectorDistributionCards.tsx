import { BarChart3, Factory, Layers } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { CountBucket, PillarAverages } from "@/hooks/useSectorDetail";
import { cn } from "@/lib/utils";

/* Distribution / breakdown cards for the sector detail page. Each card is
 * self-contained and reads one slice of the sector KPIs. Extracted from
 * SectorDetailPage so the page file stays an orchestrator. */

const SCORE_BUCKETS = [
  { label: "<20", color: "bg-red-500" },
  { label: "20-39", color: "bg-orange-500" },
  { label: "40-59", color: "bg-amber-500" },
  { label: "60-79", color: "bg-green-500" },
  { label: "≥80", color: "bg-emerald-600" },
];

export function ScoreDistributionCard({ distribution }: { distribution: number[] }) {
  const maxBucket = Math.max(...distribution, 1);
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={BarChart3}
          label="Distribuzione score composito"
          className="mb-3"
        />
        <div className="grid grid-cols-5 gap-2 items-end h-32">
          {distribution.map((count, i) => {
            const pct = (count / maxBucket) * 100;
            const b = SCORE_BUCKETS[i];
            return (
              <div key={b.label} className="flex flex-col items-center gap-1 h-full">
                <div className="text-xs tabular-nums text-muted-foreground">
                  {count}
                </div>
                <div className="flex-1 w-full flex items-end">
                  <div
                    className={cn("w-full rounded-t", b.color)}
                    style={{ height: `${Math.max(pct, count > 0 ? 6 : 0)}%` }}
                  />
                </div>
                <div className="text-xs text-muted-foreground tabular-nums">
                  {b.label}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// NB: niente "momentum" qui — il pilastro è stato RIMOSSO dal composito
// Qualità (lens split 2026-05: la price-action vive nel lens Tecnico).
// StockScore.momentum è NULL by design per tutto l'universo, quindi la
// barra renderizzava sempre vuota ("—"). Non re-aggiungerla senza che
// il backend torni a popolare il campo.
const PILLAR_LABELS: Array<[keyof PillarAverages, string]> = [
  ["profitability", "Profittabilità"],
  ["sustainability", "Sostenibilità"],
  ["growth", "Crescita"],
  ["value", "Valore"],
  ["sentiment", "Sentiment"],
];

function pillarBarTone(score: number | null): string {
  if (score === null) return "bg-muted";
  if (score >= 70) return "bg-emerald-500";
  if (score >= 50) return "bg-sky-500";
  if (score >= 30) return "bg-amber-500";
  return "bg-rose-500";
}

export function PillarAveragesCard({ pa }: { pa: PillarAverages }) {
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Layers}
          label="Punteggio medio per pilastro"
          className="mb-3"
        />

        <div className="space-y-2">
          {PILLAR_LABELS.map(([key, label]) => {
            const v = pa[key];
            const pct = v === null ? 0 : Math.max(0, Math.min(100, v));
            return (
              <div key={key} className="grid grid-cols-[110px_1fr_44px] items-center gap-2">
                <span className="text-xs text-muted-foreground truncate">{label}</span>
                <div className="h-2 rounded-full bg-muted/50 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", pillarBarTone(v))}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs tabular-nums font-semibold text-right">
                  {v === null ? "—" : v.toFixed(0)}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

export function IndustryBreakdownCard({
  buckets,
  total,
}: {
  buckets: CountBucket[];
  total: number;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Factory}
          label={`Sotto-industrie (${buckets.length})`}
          className="mb-3"
        />
        {buckets.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">Nessun dato</div>
        ) : (
          <div className="space-y-1.5">
            {buckets.map((b) => {
              const pct = (b.count / max) * 100;
              const sharePct = total > 0 ? (b.count / total) * 100 : 0;
              // Funnel verso lo screener: ogni industry apre /stocks
              // pre-filtrato (param `industry`). Il bucket "(no
              // industry)" è un'etichetta sintetica, non un filtro.
              const linkable = b.label !== "(no industry)";
              return (
                <div
                  key={b.label}
                  // V3.6: right column widened 36px → 72px and explicitly
                  // `whitespace-nowrap` because counts >9 paired with
                  // percentages ≥10% (e.g. "25 · 63%") used to wrap onto
                  // two lines inside the original 36px cell, doubling the
                  // row height and breaking the rhythm.
                  className="grid grid-cols-[1fr_60px_72px] items-center gap-2"
                >
                  {linkable ? (
                    <Link
                      to={`/stocks?industry=${encodeURIComponent(b.label)}`}
                      className="text-xs truncate hover:underline hover:text-foreground"
                      title={`Apri "${b.label}" nello screener`}
                    >
                      {b.label}
                    </Link>
                  ) : (
                    <span className="text-xs truncate" title={b.label}>
                      {b.label}
                    </span>
                  )}
                  <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500/70"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums text-right text-muted-foreground whitespace-nowrap">
                    {b.count} · {sharePct.toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const RISK_PALETTE: Record<string, string> = {
  conservative: "bg-emerald-500",
  moderate: "bg-sky-500",
  aggressive: "bg-rose-500",
};

export function DistributionCard({
  title,
  buckets,
  total,
  palette,
  preserveOrder = false,
  icon,
}: {
  title: string;
  buckets: CountBucket[];
  total: number;
  palette: "blue" | "amber" | "risk";
  preserveOrder?: boolean;
  /** Icon shown in the SectionTitle. Defaults to BarChart3 when not
   *  supplied so callers that just need a generic histogram look don't
   *  have to import an icon. */
  icon?: typeof BarChart3;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const ordered = preserveOrder ? buckets : [...buckets].sort((a, b) => b.count - a.count);

  function barClass(label: string, idx: number): string {
    if (palette === "risk") return RISK_PALETTE[label] ?? "bg-muted";
    if (palette === "amber") {
      // Mega → emerald, descending → progressively warmer
      const tones = ["bg-emerald-500", "bg-sky-500", "bg-amber-500", "bg-orange-500", "bg-rose-500"];
      return tones[idx] ?? "bg-muted";
    }
    return "bg-blue-500/70";
  }

  const Icon = icon ?? BarChart3;
  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={Icon} label={title} className="mb-3" />
        {ordered.length === 0 ? (
          <div className="text-sm text-muted-foreground py-3">Nessun dato</div>
        ) : (
          <div className="space-y-1.5">
            {ordered.map((b, i) => {
              const pct = (b.count / max) * 100;
              const sharePct = total > 0 ? (b.count / total) * 100 : 0;
              return (
                <div
                  key={b.label}
                  // V3.6: right column widened 36px → 72px + nowrap
                  // (see IndustryBreakdownCard for the rationale —
                  // same "25 · 63%" two-line bug).
                  className="grid grid-cols-[1fr_50px_72px] items-center gap-2"
                >
                  <span className="text-xs truncate capitalize" title={b.label}>
                    {b.label}
                  </span>
                  <div className="h-2 rounded-full bg-muted/40 overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", barClass(b.label, i))}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs tabular-nums text-right text-muted-foreground whitespace-nowrap">
                    {b.count} · {sharePct.toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
