import { Settings as SettingsIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { EngineHealthPanel } from "@/components/EngineHealthPanel";
import { CatalogRefreshPanel } from "@/components/settings/CatalogRefreshPanel";
import { ScanLogPanel } from "@/components/settings/ScanLogPanel";
import { ScoreIcPanel } from "@/components/settings/ScoreIcPanel";

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
            Salute del motore, scansioni e stato dei refresh catalogo per indice.
          </p>
        </header>
      )}

      <EngineHealthPanel />
      {/* Efficacia, calibrazione, per detector ed equity vivono ora sopra la
          tabella dei segnali (2026-09-16): stanno dove si leggono i segnali. */}
      <p className="text-xs text-muted-foreground">
        Le statistiche di efficacia dei segnali sono nella pagina{" "}
        <Link to="/alerts" className="font-semibold underline underline-offset-2">
          Segnali
        </Link>
        , sopra la tabella; quelle dei setup nella pagina{" "}
        <Link to="/setups" className="font-semibold underline underline-offset-2">
          In formazione
        </Link>
        .
      </p>
      <ScoreIcPanel />
      <ScanLogPanel />
      <CatalogRefreshPanel />
    </div>
  );
}
