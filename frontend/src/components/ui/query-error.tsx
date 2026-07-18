import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";

interface QueryErrorProps {
  /**
   * What failed, completing "Errore nel caricamento {message}." e.g. "dei
   * segnali", "dei portafogli 13F". Defaults to a generic "dei dati".
   */
  message?: string;
  /** TanStack Query `refetch`. When omitted, no retry button is shown. */
  onRetry?: () => void;
  /** `isFetching` — disables + spins the retry button while a retry runs. */
  isRetrying?: boolean;
  className?: string;
}

/**
 * Consistent inline error state for a failed data fetch (U1). Previously each
 * page hand-rolled its own error markup — some with a retry, some without, some
 * silent (AlertsPage rendered nothing on failure). This centralises the visual
 * language (matches the SectorsOverview block) and always offers a retry.
 *
 * No Card wrapper on purpose: drop it wherever the loading branch was, and the
 * caller controls padding/placement. `role="alert"` so screen readers announce
 * the failure instead of the region just going quiet.
 */
export function QueryError({
  message = "dei dati",
  onRetry,
  isRetrying = false,
  className,
}: QueryErrorProps) {
  return (
    <div role="alert" className={cn("space-y-3", className)}>
      <p className="text-sm text-destructive">Errore nel caricamento {message}.</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", isRetrying && "animate-spin")} aria-hidden />
          Riprova
        </button>
      )}
    </div>
  );
}
