import { CheckCircle2, CircleSlash } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import type { Setup } from "@/hooks/useSetups";
import { resolvedAfterDays } from "@/hooks/useSetups";
import { detectorLabel } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

/* ─── What happened to the setups that closed ───────────────────────────── *
 *
 * The live list groups by CONDITION, because the question there is "what am I
 * waiting for". History asks a different question — "did the wait pay off" —
 * so this is flat and chronological instead.
 *
 * Both outcomes are shown together on purpose. A converted setup on its own
 * says nothing; the conversion RATE is the ratio, and an expired row is the
 * other half of it. Hiding the expiries would make the feature look better
 * than it is, which is the same rule that stops `expire_stale_setups` from
 * deleting them.
 */

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" });
}

function OutcomeRow({ setup }: { setup: Setup }) {
  const converted = setup.status === "converted";
  const waited = resolvedAfterDays(setup);
  // Literal tone classes, never composed — the Tailwind purger only sees
  // string literals and would strip a template-built class (CLAUDE.md).
  const badge = converted
    ? "border-emerald-300/60 bg-emerald-50 text-emerald-700 dark:border-emerald-700/50 dark:bg-emerald-950/40 dark:text-emerald-300"
    : "border-border bg-muted/50 text-muted-foreground";
  const Icon = converted ? CheckCircle2 : CircleSlash;

  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(setup.ticker)}`}
        className="flex items-center gap-3 px-3 py-2 hover:bg-accent/40 transition-colors"
      >
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.6471rem] font-semibold shrink-0",
            badge,
          )}
        >
          <Icon className="h-3 w-3" aria-hidden />
          {converted ? "Convertito" : "Scaduto"}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="text-sm font-medium truncate">{setup.ticker}</span>
            <span className="text-[0.6471rem] text-muted-foreground truncate">{setup.name}</span>
          </span>
          <span className="block text-[0.6471rem] text-muted-foreground truncate">
            {detectorLabel(setup.detector)}
            {converted && setup.lead_days !== null && setup.lead_days !== undefined
              ? ` · ${setup.lead_days}g di preavviso`
              : waited !== null
                ? ` · atteso ${waited}g senza scattare`
                : ""}
          </span>
        </span>

        <span className="shrink-0 text-[0.6471rem] text-muted-foreground tabular-nums">
          {fmtDate(setup.resolved_at)}
        </span>
      </Link>
    </li>
  );
}

export function SetupOutcomeList({ setups }: { setups: Setup[] }) {
  if (setups.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Nessun setup si è ancora chiuso. Un setup si chiude quando il suo
          detector spara (convertito) oppure quando smette di essere valido o
          resta in attesa troppo a lungo (scaduto).
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <ol className="divide-y">
          {setups.map((s) => (
            <OutcomeRow key={s.id} setup={s} />
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
