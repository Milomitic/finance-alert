import { useEffect, useState } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

export type SaveState = "idle" | "saving" | "saved" | "error";

interface Props {
  state: SaveState;
  onRetry?: () => void;
}

export function SaveIndicator({ state, onRetry }: Props) {
  const [visible, setVisible] = useState(state !== "idle");

  useEffect(() => {
    if (state === "saved") {
      setVisible(true);
      const t = setTimeout(() => setVisible(false), 2000);
      return () => clearTimeout(t);
    }
    setVisible(state !== "idle");
  }, [state]);

  if (!visible && state === "idle") return null;
  if (!visible) return null;

  return (
    <div
      className={cn(
        "flex items-center gap-1.5 text-xs transition-opacity",
        state === "saving" && "text-muted-foreground",
        state === "saved" && "text-green-600",
        state === "error" && "text-destructive"
      )}
      role="status"
      aria-live="polite"
    >
      {state === "saving" && (
        <>
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Salvataggio…</span>
        </>
      )}
      {state === "saved" && (
        <>
          <Check className="h-3 w-3" />
          <span>Salvato</span>
        </>
      )}
      {state === "error" && (
        <>
          <AlertCircle className="h-3 w-3" />
          <span>Errore di salvataggio</span>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="underline hover:no-underline ml-1"
            >
              Riprova
            </button>
          )}
        </>
      )}
    </div>
  );
}
