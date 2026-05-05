import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { GlobalKpiTiles } from "@/components/dashboard/GlobalKpiTiles";
import { MoodCard } from "@/components/dashboard/MoodCard";
import { ScanTriggerCard } from "@/components/dashboard/ScanTriggerCard";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
  /** Forwarded to ScanTriggerCard for the "next scheduled scan" footer. */
  nextScanAt?: string | null;
}

/* ─── HeroStrip — top of dashboard ──────────────────────────────────────── */
/* Three columns side-by-side at the same row height (300px on lg+):
 *
 *   ┌────── MoodCard (3fr) ──────┐  ┌── Global KPI (1.5fr) ──┐  ┌─ Scan (1.2fr) ─┐
 *   │ market mood hero            │  │ vertical KPI list     │  │ Esegui scan   │
 *   │                             │  │ (Universe / A/D / ...) │  │ Invia digest  │
 *   │                             │  │                       │  │ Ultimo / Prox │
 *   └────────────────────────────┘  └───────────────────────┘  └───────────────┘
 *
 * Was a 2-column layout where the right column stacked Global KPI on top
 * of Scan Trigger. The stack squashed Global KPI to ~150px (visible only
 * 1 tile of the 6 list rows; rest scrolled), wasting horizontal space.
 * Side-by-side gives Global KPI the full row height — all 6 tiles fit
 * without scroll — and keeps Scan Trigger at a comfortable column width.
 */
export function HeroStrip({ global, byIndex, nextScanAt }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_1.5fr_1.2fr] lg:h-[300px]">
      <div className="h-full min-h-0">
        <MoodCard global={global} byIndex={byIndex} />
      </div>
      <div className="h-full min-h-0">
        <GlobalKpiTiles global={global} />
      </div>
      <div className="h-full min-h-0">
        <ScanTriggerCard nextScanAt={nextScanAt} />
      </div>
    </div>
  );
}
