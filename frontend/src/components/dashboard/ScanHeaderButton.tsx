import { Calculator, Loader2, PlayCircle, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useScanStatus } from "@/hooks/useScanStatus";
import {
  useSendDigest,
  useTriggerScan,
} from "@/hooks/useAlertMutations";
import {
  useScoreRecomputeStatus,
  useTriggerScoreRecompute,
} from "@/hooks/useScoreRecompute";

/* ─── ScanHeaderButton — compact scan + digest controls ─────────────────── */
/* The scan-trigger card used to occupy a column of the dashboard hero.
 * Moved here as two small icon-buttons in the page header so the hero
 * strip can be all market context. The progress UI for an in-flight
 * scan still lives in the global ScanProgressToast (mounted in Layout)
 * — these buttons are just the "kick off" affordances.
 *
 * Kept minimal: outline-button style, icon-led, compact tooltip on
 * hover. Disabled state when a scan is already running so a double-
 * click doesn't queue a second one. */

interface Props {
  /** Unused for now — placeholder for future "next scan ETA" pill that
   *  could live next to the buttons. The dashboard header already shows
   *  the timestamp inline; keeping this prop on the API surface makes
   *  it easy to forward later without a breaking change. */
  nextScanAt?: string | null;
}

export function ScanHeaderButton(_: Props) {
  const status = useScanStatus().data;
  const recomputeStatus = useScoreRecomputeStatus().data;
  const triggerScan = useTriggerScan();
  const triggerRecompute = useTriggerScoreRecompute();
  const sendDigest = useSendDigest();

  const isRunning = status?.is_running ?? false;
  const isStarting = triggerScan.isPending;
  const isRecomputeRunning = recomputeStatus?.is_running ?? false;
  const isRecomputeStarting = triggerRecompute.isPending;

  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerScan.mutate()}
            disabled={isRunning || isStarting}
            className="h-8 px-2.5 text-xs"
            aria-label={isRunning ? "Scan già in corso" : "Esegui scan ora"}
          >
            {isRunning || isStarting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <PlayCircle className="h-3.5 w-3.5" />
            )}
            <span className="ml-1.5 hidden sm:inline">
              {isRunning ? "Scan in corso" : "Scan"}
            </span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-[11px]">
          {isRunning
            ? "Uno scan è già in corso — vedi il toast in basso a destra"
            : "Avvia uno scan in background. La notifica seguirà l'avanzamento."}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={() => triggerRecompute.mutate()}
            disabled={isRecomputeRunning || isRecomputeStarting}
            className="h-8 px-2.5 text-xs"
            aria-label={
              isRecomputeRunning
                ? "Ricalcolo già in corso"
                : "Ricalcola tutti gli score"
            }
          >
            {isRecomputeRunning || isRecomputeStarting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Calculator className="h-3.5 w-3.5" />
            )}
            <span className="ml-1.5 hidden sm:inline">
              {isRecomputeRunning ? "Ricalcolo in corso" : "Ricalcola score"}
            </span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-[11px]">
          {isRecomputeRunning
            ? "Ricalcolo già in corso — vedi il toast in basso a destra"
            : "Forza il ricalcolo del composite score per tutte le stock (~30-60s). La notifica seguirà l'avanzamento."}
        </TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={() => sendDigest.mutate()}
            disabled={sendDigest.isPending}
            className="h-8 px-2.5 text-xs"
            aria-label="Invia digest"
          >
            {sendDigest.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            <span className="ml-1.5 hidden md:inline">Digest</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-[11px]">
          Invia il digest degli ultimi alert sui canali configurati
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
