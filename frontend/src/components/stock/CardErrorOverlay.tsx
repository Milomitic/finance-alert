import { AlertTriangle } from "lucide-react";

import { ApiError } from "@/api/client";
import { messaggioErrore } from "@/lib/errori";
import { Button } from "@/components/ui/button";

/** Centered, formatted error shown inside a detail card when its force-refresh
 *  fails (e.g. the upstream source returned an error). Fills the card body and
 *  offers a one-click retry. */
export function CardErrorOverlay({
  error,
  onRetry,
  retrying,
}: {
  error: ApiError | Error;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  // Il testo del server era in inglese e tecnico («User not found», «Failed
  // to fetch»): ora si dice quale guasto e' (B-76).
  const message = messaggioErrore(error) ?? "Aggiornamento non riuscito.";
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 p-4 text-center">
      <AlertTriangle className="h-6 w-6 text-destructive" />
      <p className="text-sm text-destructive break-words max-w-full">{message}</p>
      {onRetry ? (
        <Button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          variant="testo" size="testo" className="mt-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {retrying ? "Aggiornamento…" : "Riprova"}
        </Button>
      ) : null}
    </div>
  );
}
