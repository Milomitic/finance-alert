import { Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function SpotlightPlaceholder() {
  return (
    <Card className="border-dashed">
      <CardContent className="p-4 flex flex-col items-center justify-center text-center min-h-[140px]">
        <Sparkles className="h-5 w-5 text-muted-foreground mb-2" />
        <div className="text-[11px] font-semibold text-muted-foreground">Stock Spotlight</div>
        <div className="text-[10px] text-muted-foreground mt-1">
          Sparkline + RSI mini + segnale corrente.<br />
          Disponibile in Fase 3B / 3C.
        </div>
      </CardContent>
    </Card>
  );
}
