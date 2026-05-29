import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";

/** The per-card "force refresh" icon button. Identical look to the one on the
 *  stock-score card: a small ghost RefreshCw that spins while busy. */
export function CardRefreshButton({
  onClick,
  busy,
  title = "Aggiorna",
}: {
  onClick: () => void;
  busy: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className={cn(
        "p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors disabled:opacity-50",
      )}
      title={title}
      aria-label={title}
    >
      <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
    </button>
  );
}
