import { BarChart3 } from "lucide-react";

export function AlertsByIndexBars() {
  return (
    <div className="px-4 py-6 flex flex-col items-center justify-center text-center min-h-[80px]">
      <BarChart3 className="h-5 w-5 text-muted-foreground mb-2" />
      <div className="text-xs text-muted-foreground">
        Breakdown alert per indice — disponibile in Fase 3E
      </div>
    </div>
  );
}
