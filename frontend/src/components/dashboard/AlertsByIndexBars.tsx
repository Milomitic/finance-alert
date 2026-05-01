import { BarChart3 } from "lucide-react";

export function AlertsByIndexBars() {
  return (
    <div className="px-3 py-4 flex flex-col items-center justify-center text-center min-h-[60px]">
      <BarChart3 className="h-4 w-4 text-muted-foreground mb-1" />
      <div className="text-[10px] text-muted-foreground">
        Breakdown alert per indice — disponibile in Fase 3E
      </div>
    </div>
  );
}
