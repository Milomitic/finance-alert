import { AlertTriangle } from "lucide-react";

import { ApiError } from "@/api/client";

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
  const message = error instanceof ApiError ? error.detail : error.message;
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 p-4 text-center">
      <AlertTriangle className="h-6 w-6 text-destructive" />
      <p className="text-sm text-destructive break-words max-w-full">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="mt-1 text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 disabled:opacity-50"
        >
          {retrying ? "Aggiornamento…" : "Riprova"}
        </button>
      ) : null}
    </div>
  );
}
