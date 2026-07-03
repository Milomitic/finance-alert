import { ChevronDown, ChevronRight, FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";

import type {
  DetectorPerfCell,
  DetectorPerfMeta,
  DetectorPerfRow,
} from "@/api/platformHealth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useDetectorPerformance } from "@/hooks/useDetectorPerformance";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── DetectorPerformancePanel — esplora esiti per detector ─────────────── *
 *
 * Slicing del warehouse `signal_outcomes` che la UI non esponeva: hit-rate
 * per detector × regime al segnale × tono × fascia di Forza. Una riga per
 * detector (totali), espandibile alle celle dei tre breakdown.
 *
 * Onestà prima di tutto: il warehouse è giovane e PARZIALE (gli orizzonti
 * lunghi a 63g maturano mesi dopo il segnale, interi detector mancano
 * ancora), quindi l'header dichiara la copertura reale e ogni cella con
 * n < 30 è resa attenuata con un chip "n<30" — indicativa, non conclusiva.
 *
 * Collassato di default: il fetch parte solo alla prima apertura (hook con
 * `enabled`), coerente con un pannello diagnostico consultato di rado.
 */
export function DetectorPerformancePanel() {
  const [open, setOpen] = useState(false);
  const q = useDetectorPerformance(open);
  const data = q.data;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={FlaskConical}
          label="Esiti per detector — regime · tono · Forza"
          right={
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setOpen((v) => !v)}
              className="text-xs"
            >
              {open ? (
                <ChevronDown className="h-3.5 w-3.5 mr-1" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 mr-1" />
              )}
              {open ? "Nascondi" : "Mostra"}
            </Button>
          }
          className={open ? "mb-3" : "mb-0"}
        />

        {open && (
          <>
            {q.isLoading ? (
              <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
                <Loader2 className="h-4 w-4 animate-spin" />
                Aggrego gli esiti maturati…
              </div>
            ) : q.isError ? (
              <div className="py-6 text-center text-sm text-rose-700 dark:text-rose-400">
                Errore nel caricamento degli esiti — riprova più tardi.
              </div>
            ) : !data || data.meta.total_rows === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">
                Nessun esito maturato nel warehouse: si popola a fine scan man
                mano che gli orizzonti dei segnali si compiono.
              </div>
            ) : (
              <div className="space-y-3">
                <CoverageBanner meta={data.meta} />
                <div className="overflow-x-auto">
                  <table className="w-full text-sm tabular-nums">
                    <thead className="bg-muted/30 text-muted-foreground border-b">
                      <tr>
                        <th className="text-left px-3 py-2 font-semibold">
                          Detector
                        </th>
                        <th className="text-right px-3 py-2 font-semibold">N</th>
                        <th className="text-right px-3 py-2 font-semibold">
                          Hit
                        </th>
                        <th
                          className="text-right px-3 py-2 font-semibold"
                          title="Hit-rate market-neutral: quota di segnali che hanno battuto la media dell'universo nella loro direzione (skill al netto del mercato)."
                        >
                          Hit neutro
                        </th>
                        <th className="text-right px-3 py-2 font-semibold">
                          Fwd medio
                        </th>
                        <th className="px-2 py-2 w-6" />
                      </tr>
                    </thead>
                    <tbody>
                      {data.detectors.map((row) => (
                        <DetectorRow key={row.detector} row={row} />
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-[11px] text-muted-foreground italic">
                  "Hit" = direzione del prezzo coerente col tono entro
                  l'orizzonte del detector; "Hit neutro" al netto della media
                  dell'universo (skill, non beta). Le celle attenuate con chip
                  "n&lt;{data.meta.min_n}" hanno campione sottile: indicative,
                  non conclusive.
                </p>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* Header di copertura: il warehouse è parziale e il pannello lo DICE, invece
 * di lasciar credere che 9 detector su 17 siano "tutti i detector". */
function CoverageBanner({ meta }: { meta: DetectorPerfMeta }) {
  const fmt = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString("it-IT", {
          day: "2-digit",
          month: "2-digit",
          year: "2-digit",
        })
      : "—";
  return (
    <div className="rounded-md border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-2.5 py-1.5 text-xs text-amber-800 dark:text-amber-300">
      <span className="font-semibold">Copertura parziale:</span>{" "}
      {meta.total_rows} esiti maturati · {meta.n_detectors}/
      {meta.n_detectors_universe} detector · segnali dal {fmt(meta.date_min)} al{" "}
      {fmt(meta.date_max)}. Gli orizzonti lunghi (63g) maturano ~3 mesi dopo il
      segnale — i primi esiti attesi verso metà agosto; i detector assenti non
      hanno ancora esiti compiuti.
    </div>
  );
}

/* Etichette italiane dei bucket. Mappe a stringhe LITERALI (vedi CLAUDE.md:
 * il purger Tailwind e la leggibilità preferiscono literal, niente template). */
const REGIME_LABELS: Record<string, string> = {
  bull: "Regime bull",
  bear: "Regime bear",
  flat: "Regime flat",
  "n/d": "Regime n/d",
};
const TONE_LABELS: Record<string, string> = {
  bull: "Bull",
  bear: "Bear",
};
const STRENGTH_LABELS: Record<string, string> = {
  "<60": "Forza <60",
  "60-74": "Forza 60–74",
  ">=75": "Forza ≥75",
  "n/d": "Forza n/d",
};

function DetectorRow({ row }: { row: DetectorPerfRow }) {
  const [expanded, setExpanded] = useState(false);
  // I nomi nel warehouse sono "nudi" (volume_breakout); il meta-helper vuole
  // il prefisso "signal:" per risolvere etichetta + icona amichevoli.
  const meta = getAlertKindMeta(`signal:${row.detector}`);
  const Icon = meta.icon;
  const t = row.total;

  return (
    <>
      <tr
        className="border-b border-border/40 hover:bg-muted/30 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-3 py-2">
          <span className="inline-flex items-center gap-2">
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            <Icon className="h-3.5 w-3.5 shrink-0" />
            <span className="font-semibold">{meta.label}</span>
          </span>
        </td>
        <td className="text-right px-3 py-2 font-bold">{t.n}</td>
        <td className={cn("text-right px-3 py-2 font-semibold", hitTone(t.abs_hit_rate))}>
          {pct(t.abs_hit_rate)}
        </td>
        <td
          className={cn(
            "text-right px-3 py-2 font-semibold",
            hitTone(t.mkt_neutral_hit_rate),
          )}
        >
          {pct(t.mkt_neutral_hit_rate)}
        </td>
        <td className={cn("text-right px-3 py-2 font-semibold", retTone(t.avg_fwd_return))}>
          {ret(t.avg_fwd_return)}
        </td>
        <td className="px-2 py-2 text-right">
          {t.low_confidence && <LowNChip />}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/40 bg-muted/20">
          <td colSpan={6} className="px-3 py-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <BreakdownTable
                title="Regime al segnale"
                cells={row.by_regime}
                labels={REGIME_LABELS}
              />
              <BreakdownTable
                title="Tono"
                cells={row.by_tone}
                labels={TONE_LABELS}
              />
              <BreakdownTable
                title="Fascia di Forza"
                cells={row.by_strength}
                labels={STRENGTH_LABELS}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function BreakdownTable({
  title,
  cells,
  labels,
}: {
  title: string;
  cells: DetectorPerfCell[];
  labels: Record<string, string>;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
        {title}
      </div>
      <table className="w-full text-xs tabular-nums">
        <thead className="text-muted-foreground border-b">
          <tr>
            <th className="text-left px-2 py-1 font-semibold">Gruppo</th>
            <th className="text-right px-2 py-1 font-semibold">N</th>
            <th className="text-right px-2 py-1 font-semibold">Hit</th>
            <th className="text-right px-2 py-1 font-semibold">Neutro</th>
            <th className="text-right px-2 py-1 font-semibold">Fwd</th>
          </tr>
        </thead>
        <tbody>
          {cells.map((c) => (
            <tr
              key={c.key}
              className={cn(
                "border-b border-border/40",
                c.low_confidence && "text-muted-foreground/70",
              )}
            >
              <td className="px-2 py-1">
                <span className="inline-flex items-center gap-1.5">
                  {labels[c.key] ?? c.key}
                  {c.low_confidence && <LowNChip />}
                </span>
              </td>
              <td className="px-2 py-1 text-right">{c.n}</td>
              <td
                className={cn(
                  "px-2 py-1 text-right font-semibold",
                  !c.low_confidence && hitTone(c.abs_hit_rate),
                )}
              >
                {pct(c.abs_hit_rate)}
              </td>
              <td
                className={cn(
                  "px-2 py-1 text-right font-semibold",
                  !c.low_confidence && hitTone(c.mkt_neutral_hit_rate),
                )}
              >
                {pct(c.mkt_neutral_hit_rate)}
              </td>
              <td
                className={cn(
                  "px-2 py-1 text-right",
                  !c.low_confidence && retTone(c.avg_fwd_return),
                )}
              >
                {ret(c.avg_fwd_return)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* Chip "campione sottile" — sempre sotto la soglia min_n del backend (30). */
function LowNChip() {
  return (
    <span
      className="px-1 py-px rounded text-[9px] uppercase tracking-wider font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
      title="Campione sotto la soglia di 30 esiti maturati: valore indicativo, non conclusivo."
    >
      n&lt;30
    </span>
  );
}

/* ─── formattazione + toni (percentuali 0..100 dal backend) ─────────────── */

function pct(v: number | null): string {
  return v == null ? "—" : `${v.toFixed(0)}%`;
}

function ret(v: number | null): string {
  return v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/* Stessa scala della tabella "Efficacia segnali": ≥55% verde, <45% rosso. */
function hitTone(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v >= 55) return "text-emerald-700 dark:text-emerald-400";
  if (v < 45) return "text-rose-700 dark:text-rose-400";
  return "";
}

function retTone(v: number | null): string {
  if (v == null) return "text-muted-foreground";
  if (v > 0) return "text-emerald-700 dark:text-emerald-400";
  if (v < 0) return "text-rose-700 dark:text-rose-400";
  return "";
}
