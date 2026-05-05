import { Loader2, PlayCircle, Send, Zap } from "lucide-react";

import type { ScanStatusInfo } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useScanStatus } from "@/hooks/useScanStatus";
import {
  useSendDigest,
  useTriggerScan,
} from "@/hooks/useAlertMutations";
import { cn } from "@/lib/utils";

/* ─── ScanTriggerCard — manual scan + digest controls (dashboard) ────────── */
/* Lives in the right-side sidebar of the dashboard hero, directly below the
 * compressed Global KPI list. The two together form a slim "control rail"
 * to the right of the MoodCard.
 *
 * What it does:
 *   - Primary action: "Esegui scan ora" — triggers a manual scan_alerts run.
 *   - Secondary action: "Invia digest" — pushes the latest alert digest.
 *   - Footer: last completed timestamp + next scheduled scan, when known.
 *
 * What it does NOT do (anymore):
 *   - Show the running progress / phase / stop button. That UI moved to
 *     `ScanProgressToast` — a persistent floating notification that auto-
 *     dismisses 30s after the scan completes. The reason: the dashboard is
 *     a snapshot surface (read at-a-glance), not a process monitor; a card
 *     that grows/shrinks based on scan state was distracting.
 */

function formatRelative(iso: string | null): string | null {
  if (!iso) return null;
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return null;
  const diffMin = (Date.now() - ts) / (1000 * 60);
  if (diffMin < 1) return "or ora";
  if (diffMin < 60) return `${Math.round(diffMin)}m fa`;
  const diffH = diffMin / 60;
  if (diffH < 24) return `${Math.round(diffH)}h fa`;
  return `${Math.round(diffH / 24)}g fa`;
}

function formatTime(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString("it-IT", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return null;
  }
}

interface Props {
  /** Optional override for "next scheduled scan" — comes from the dashboard
   *  summary KPI block. When omitted the row simply hides. */
  nextScanAt?: string | null;
}

export function ScanTriggerCard({ nextScanAt }: Props) {
  const status: ScanStatusInfo | undefined = useScanStatus().data;
  const triggerScan = useTriggerScan();
  const sendDigest = useSendDigest();

  const isRunning = status?.is_running ?? false;
  const isStartingNow = triggerScan.isPending;
  const lastCompleted = status?.completed_at ?? null;
  const lastRel = formatRelative(lastCompleted);
  const nextAt = formatTime(nextScanAt ?? null);

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-3 flex flex-col gap-2 h-full">
        <SectionTitle icon={Zap} label="Scan mercati" className="px-1" />

        {/* Primary action — sized to dominate the card visually. The button
            is the reason this card exists. */}
        <Button
          onClick={() => triggerScan.mutate()}
          disabled={isRunning || isStartingNow}
          className="w-full justify-center gap-2"
          title={
            isRunning
              ? "Uno scan è già in corso — vedi la notifica in basso a destra"
              : "Avvia uno scan in background. La notifica seguirà l'avanzamento."
          }
        >
          {isRunning || isStartingNow ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <PlayCircle className="h-4 w-4" />
          )}
          {isRunning ? "Scan in corso…" : "Esegui scan ora"}
        </Button>

        {/* Secondary action — smaller, outlined */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => sendDigest.mutate()}
          disabled={sendDigest.isPending}
          className="w-full justify-center gap-2"
        >
          {sendDigest.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          Invia digest
        </Button>

        {/* Footer: last + next, compact text. Hides itself if both are
            unknown (e.g. fresh DB before any scan). */}
        {(lastRel || nextAt) && (
          <div className="mt-auto pt-2 border-t border-border/50 space-y-0.5 text-[10.5px] tabular-nums">
            {lastRel && (
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground uppercase tracking-wider font-semibold">
                  Ultimo
                </span>
                <span
                  className="text-foreground/80 font-medium truncate"
                  title={lastCompleted ?? undefined}
                >
                  {lastRel}
                </span>
              </div>
            )}
            {nextAt && (
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground uppercase tracking-wider font-semibold">
                  Prossimo
                </span>
                <span
                  className={cn(
                    "text-foreground/80 font-medium truncate",
                    isRunning && "text-muted-foreground/60",
                  )}
                  title={nextScanAt ?? undefined}
                >
                  {nextAt}
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
