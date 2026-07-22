import { Settings as SettingsIcon } from "lucide-react";

import { EngineHealthPanel } from "@/components/EngineHealthPanel";
import { CalibrationPanel } from "@/components/settings/CalibrationPanel";
import { CatalogRefreshPanel } from "@/components/settings/CatalogRefreshPanel";
import { DetectorPerformancePanel } from "@/components/settings/DetectorPerformancePanel";
import { EquityCurvePanel } from "@/components/settings/EquityCurvePanel";
import { RulePerformancePanel } from "@/components/settings/RulePerformancePanel";
import { ScanLogPanel } from "@/components/settings/ScanLogPanel";
import { ScoreIcPanel } from "@/components/settings/ScoreIcPanel";

/* ─── SettingsPage — /settings route ────────────────────────────────────── *
 *
 * Admin / diagnostic surface. Two main panels:
 *   - Rule effectiveness (forward-return stats per rule.kind over
 *     1d / 5d / 20d windows).
 *   - Catalog refresh status (per-index last-run state + manual
 *     trigger).
 *
 * Was a placeholder ("Disponibile nelle prossime fasi") in the
 * sidebar for the entire 3A-3C lifetime; ships in Fase 3E.
 */
export default function SettingsPage() {
  return (
    <div className="space-y-5 max-w-6xl">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          <SettingsIcon className="h-3 w-3" />
          <span>Amministrazione · diagnostica</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
          Impostazioni
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Statistiche di efficacia dei segnali e stato dei refresh
          catalogo per indice.
        </p>
      </header>

      <EngineHealthPanel />
      <RulePerformancePanel />
      <CalibrationPanel />
      <DetectorPerformancePanel />
      <EquityCurvePanel />
      <ScoreIcPanel />
      <ScanLogPanel />
      <CatalogRefreshPanel />
    </div>
  );
}
