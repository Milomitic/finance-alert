import { BarChart3 } from "lucide-react";

export function AlertsByIndexBars() {
  return (
    <div className="px-4 py-8 flex flex-col items-center justify-center text-center min-h-[100px]">
      <BarChart3 className="h-6 w-6 text-muted-foreground mb-2" />
      <div className="text-sm text-muted-foreground">
        Breakdown alert per indice — disponibile in Fase 3E
      </div>
    </div>
  );
}
