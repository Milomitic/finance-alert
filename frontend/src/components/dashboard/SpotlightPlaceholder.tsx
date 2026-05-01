import { Sparkles } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function SpotlightPlaceholder() {
  return (
    <Card className="border-dashed h-full">
      <CardContent className="p-6 flex flex-col items-center justify-center text-center min-h-[260px] h-full">
        <Sparkles className="h-7 w-7 text-muted-foreground mb-3" />
        <div className="text-base font-semibold text-muted-foreground">Stock Spotlight</div>
        <div className="text-sm text-muted-foreground mt-1">
          Sparkline + RSI mini + segnale corrente.<br />
          Disponibile in Fase 3B / 3C.
        </div>
      </CardContent>
    </Card>
  );
}
