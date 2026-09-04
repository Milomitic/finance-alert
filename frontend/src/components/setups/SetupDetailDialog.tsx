import { Clock, Crosshair, Target, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { waitingDays, type Setup } from "@/hooks/useSetups";
import { detectorLabel } from "@/lib/setupGrouping";
import { cn } from "@/lib/utils";

/* ─── SetupDetailDialog — the same affordance signals have ───────────────── *
 *
 * Clicking a signal on the Segnali page opens a panel that explains it. A
 * setup row had no equivalent: it linked straight to the stock page, which
 * answers "what is this company" and not "why is this here".
 *
 * What it must NOT become is the signal dialog. A signal reports a match with
 * a Forza and a Probabilità behind it; a setup reports a wait, and the engine
 * has no calibration for waits. So this panel carries no probability, no
 * strength, and states plainly what each number is and is not — the same
 * discipline the page's own docstring asks for.
 */

interface Props {
  setup: Setup | null;
  onClose: () => void;
}

/** Reads the distance out loud, because "0.34 ATR" is precise and opaque.
 *  ATR is roughly one session's range, so the number IS an answer to "could
 *  this happen tomorrow" — but only if we say so. */
function distanceReading(d: number | null | undefined): { label: string; hint: string } {
  if (d == null) {
    return {
      label: "—",
      hint: "Questo innesco non è un attraversamento di prezzo: non c'è un livello da cui misurare una distanza.",
    };
  }
  if (d <= 0.25) return { label: `${d.toFixed(2)} ATR`, hint: "A portata di una sessione normale." };
  if (d <= 1) return { label: `${d.toFixed(2)} ATR`, hint: "Circa una giornata di movimento tipico." };
  if (d <= 2.5) return { label: `${d.toFixed(2)} ATR`, hint: "Servono alcune sedute nella direzione giusta." };
  return { label: `${d.toFixed(2)} ATR`, hint: "Lontano: servirebbe un movimento fuori dall'ordinario." };
}

function Metric({
  label,
  value,
  hint,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 p-3", className)}>
      <div className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </div>
      <div className="text-xl font-bold tabular-nums leading-tight mt-0.5">{value}</div>
      {hint && <div className="text-[0.7059rem] text-muted-foreground mt-1 leading-snug">{hint}</div>}
    </div>
  );
}

export function SetupDetailDialog({ setup, onClose }: Props) {
  // Hooks would go here, above any early return — the rule that blanked this
  // app once already. There are none, and the guard below stays a plain
  // conditional render rather than an early `return null`.
  const open = setup !== null;
  const bull = setup?.tone === "bull";
  const days = setup ? waitingDays(setup) : null;
  const level = setup?.annotations?.levels?.[0];
  const dist = distanceReading(setup?.distance_atr);
  const factors: [string, number][] = Object.entries(setup?.factors ?? {});

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl p-0 max-h-[90vh] overflow-y-auto">
        {setup && (
          <>
            <DialogHeader
              className={cn(
                "p-5 pb-4 space-y-2 border-l-4",
                bull ? "border-l-emerald-500" : "border-l-rose-500",
              )}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold",
                    bull
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                      : "bg-rose-500/15 text-rose-700 dark:text-rose-300",
                  )}
                >
                  {bull ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                  {detectorLabel(setup.detector)}
                </span>
                <span className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" aria-hidden />
                  in attesa da {days === null ? "—" : days === 0 ? "oggi" : `${days} giorni`}
                </span>
                {/* Named for what it is, every time it appears. */}
                <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  in formazione — non è ancora un segnale
                </span>
              </div>

              <DialogTitle className="text-2xl flex items-baseline gap-2 flex-wrap">
                <Link
                  to={`/stocks/${encodeURIComponent(setup.ticker)}`}
                  onClick={onClose}
                  className="font-bold tracking-tight hover:underline decoration-2 underline-offset-4"
                  title="Vai al dettaglio del titolo"
                >
                  {setup.ticker}
                </Link>
                {setup.name && (
                  <span className="text-base font-medium text-muted-foreground truncate min-w-0">
                    {setup.name}
                  </span>
                )}
              </DialogTitle>
              <DialogDescription className="sr-only">
                Dettagli del setup {detectorLabel(setup.detector)} per {setup.ticker}.
              </DialogDescription>
            </DialogHeader>

            {/* What still has to happen — first, and largest, because it is the
                only part you can act on. */}
            <div className="px-5">
              <div className="rounded-lg border bg-muted/40 p-4 flex items-start gap-3">
                <Target className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0">
                  <div className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-semibold">
                    Cosa manca
                  </div>
                  <p className="text-base leading-snug mt-1">{setup.missing}</p>
                  {level && (
                    <p className="text-sm text-muted-foreground tabular-nums mt-2">
                      {level.label}: <b className="text-foreground">{level.price.toFixed(2)}</b>
                      <span className="ml-2 text-xs">— il livello su cui imposteresti l'allerta</span>
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="px-5 pt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Metric
                label="Distanza dall'innesco"
                value={<span className="flex items-center gap-1.5"><Crosshair className="h-4 w-4 text-muted-foreground" />{dist.label}</span>}
                hint={dist.hint}
              />
              <Metric
                label="Priorità"
                value={Math.round(setup.convenience)}
                // Said outright, because a 0-100 number next to a stock is read
                // as a probability unless it is told not to be.
                hint="Ordina la lista per attenzione. Non è una probabilità: i setup non fanno previsioni e nessuna calibrazione del motore si applica a loro."
              />
              <Metric
                label="Catena condizioni"
                value={`${Math.round(setup.proximity * 100)}%`}
                hint="Quota della catena di gate del detector già soddisfatta. È una proprietà del detector: identica per tutti i suoi setup allo stesso stadio."
              />
            </div>

            {factors.length > 0 && (
              <div className="px-5 pt-4">
                <div className="text-[0.6765rem] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
                  Fattori misurati
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {factors.map(([k, v]) => (
                    <div key={k} className="rounded border bg-card px-2.5 py-1.5">
                      <div className="text-[0.7059rem] text-muted-foreground truncate" title={k}>
                        {k.replace(/_/g, " ")}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                          <span
                            className="block h-full rounded-full bg-primary"
                            style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }}
                          />
                        </span>
                        <span className="text-xs tabular-nums font-semibold">{v.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="p-5 flex items-center justify-between gap-3">
              <p className="text-[0.7059rem] text-muted-foreground leading-snug max-w-md">
                Un setup descrive lo stato di oggi, non una previsione. Diventa un segnale solo
                quando la condizione qui sopra si verifica.
              </p>
              <Button asChild variant="secondary" size="sm">
                <Link to={`/stocks/${encodeURIComponent(setup.ticker)}`} onClick={onClose}>
                  Apri il titolo
                </Link>
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
