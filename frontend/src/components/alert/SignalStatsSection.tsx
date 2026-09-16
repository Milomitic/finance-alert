import { BarChart3, ChevronDown } from "lucide-react";
import { Suspense, lazy, useState } from "react";

import { CalibrationPanel } from "@/components/settings/CalibrationPanel";
import { DetectorPerformancePanel } from "@/components/settings/DetectorPerformancePanel";
import { SignalEffectivenessPanel } from "@/components/settings/SignalEffectiveness";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { MetricStrip } from "@/components/ui/metric-tile";
import { SectionTitle } from "@/components/ui/section-title";
import { useDetectorPerformance } from "@/hooks/useDetectorPerformance";
import { signalStatTiles } from "@/lib/signalStats";
import { cn } from "@/lib/utils";

/* Pigro: unico consumatore di Recharts qui, e sta dentro il dettaglio chiuso. */
const EquityCurvePanel = lazy(() =>
  import("@/components/settings/EquityCurvePanel").then((m) => ({
    default: m.EquityCurvePanel,
  })),
);

/* ─── Statistiche sui segnali, sopra la tabella ─────────────────────────────
 *
 * Spostate da Diagnostica il 2026-09-16 su richiesta dell'utente. Le metriche
 * in evidenza rispondono alla domanda della pagina — «i segnali battono il
 * mercato?» — e leggono TUTTO il magazzino degli esiti (`overall`), non la
 * pagina della tabella ne' i filtri attivi. I quattro pannelli di dettaglio
 * stanno in una sezione chiusa di default e si montano solo quando aperta:
 * aperti spingerebbero la tabella sotto la piega e farebbero quattro query a
 * ogni visita.
 */

export function SignalStatsSection() {
  const q = useDetectorPerformance();
  const [aperto, setAperto] = useState(false);

  return (
    <section aria-label="Statistiche dei segnali" className="space-y-2">
      <SectionTitle icon={BarChart3} label="Efficacia dei segnali — tutti gli esiti maturati" />
      {q.isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} rows={2} className="h-[96px]" />
          ))}
        </div>
      ) : q.data ? (
        <MetricStrip tiles={signalStatTiles(q.data)} />
      ) : null}
      <button
        type="button"
        aria-expanded={aperto}
        onClick={() => setAperto((a) => !a)}
        className="inline-flex min-h-[36px] items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", aperto && "rotate-180")} aria-hidden />
        {aperto ? "Nascondi" : "Mostra"} il dettaglio: per detector, calibrazione, equity
      </button>
      {aperto && (
        <div className="space-y-4">
          <SignalEffectivenessPanel />
          <CalibrationPanel />
          <DetectorPerformancePanel />
          <Suspense fallback={<div className="h-48 animate-pulse rounded-lg bg-muted/30" />}>
            <EquityCurvePanel />
          </Suspense>
        </div>
      )}
    </section>
  );
}
