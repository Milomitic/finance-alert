import { Settings as SettingsIcon } from "lucide-react";
import { Suspense, lazy } from "react";

import { EngineHealthPanel } from "@/components/EngineHealthPanel";
import { CalibrationPanel } from "@/components/settings/CalibrationPanel";
import { CatalogRefreshPanel } from "@/components/settings/CatalogRefreshPanel";
import { DetectorPerformancePanel } from "@/components/settings/DetectorPerformancePanel";

import { ScanLogPanel } from "@/components/settings/ScanLogPanel";

/* Pigro: unico consumatore di Recharts della pagina, ~358 kB grezzi. La
   pagina e' un muro di otto pannelli e questo sta in fondo, quindi il grafico
   arriva mentre si scorre invece che prima di poter leggere il primo. */
const EquityCurvePanel = lazy(() =>
  import("@/components/settings/EquityCurvePanel").then((m) => ({
    default: m.EquityCurvePanel,
  })),
);
import { ScoreIcPanel } from "@/components/settings/ScoreIcPanel";
import { SignalEffectivenessPanel } from "@/components/settings/SignalEffectiveness";

/* ─── SettingsPage — /settings route ────────────────────────────────────── *
 *
 * Admin / diagnostic surface. Two main panels:
 *   - Signal effectiveness, read from the matured `signal_outcomes`
 *     warehouse (skill beside absolute hit, sized on independent windows).
 *   - Catalog refresh status (per-index last-run state + manual
 *     trigger).
 *
 * Was a placeholder ("Disponibile nelle prossime fasi") in the
 * sidebar for the entire 3A-3C lifetime; ships in Fase 3E.
 */
export default function SettingsPage({ embedded = false }: { embedded?: boolean } = {}) {
  return (
    <div className="space-y-5 max-w-6xl">
      {/* ⚠️ Questa pagina non ha mai contenuto una sola impostazione: otto
          pannelli, tutti diagnostici, e il suo stesso occhiello diceva
          «Amministrazione · diagnostica». Il titolo «Impostazioni» mandava a
          cercare qui le preferenze, che vivono altrove, e mandava a cercare
          altrove la diagnostica del motore, che vive qui.

          Dentro Diagnostica il titolo lo mette la pagina contenitore. Fuori
          resta, perche la rotta `/settings` continua a esistere per i vecchi
          segnalibri — ma dice cosa contiene davvero. */}
      {!embedded && (
        <header className="space-y-1">
          <div className="flex items-center gap-2 text-[0.6765rem] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            <SettingsIcon className="h-3 w-3" />
            <span>Diagnostica · motore</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
            Motore
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Statistiche di efficacia dei segnali e stato dei refresh
            catalogo per indice.
          </p>
        </header>
      )}

      <EngineHealthPanel />
      <SignalEffectivenessPanel />
      <CalibrationPanel />
      <DetectorPerformancePanel />
      <Suspense fallback={<div className="h-48 animate-pulse rounded-lg bg-muted/30" />}>
        <EquityCurvePanel />
      </Suspense>
      <ScoreIcPanel />
      <ScanLogPanel />
      <CatalogRefreshPanel />
    </div>
  );
}
