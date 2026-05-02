import { Check, X } from "lucide-react";

import type { EffectiveRule } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  rules: EffectiveRule[];
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

export function EffectiveRulesCard({ rules }: Props) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Regole effettive
        </div>
        {rules.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            Nessuna regola configurata.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {rules.map((r) => (
              <li key={r.kind} className="flex items-center gap-2 text-xs">
                {r.enabled
                  ? <Check className="h-3.5 w-3.5 text-green-600" />
                  : <X className="h-3.5 w-3.5 text-muted-foreground" />}
                <span className={cn("font-medium", !r.enabled && "line-through text-muted-foreground")}>
                  {KIND_LABEL[r.kind] ?? r.kind}
                </span>
                <Badge
                  variant={r.source === "tier2" ? "secondary" : "outline"}
                  className="ml-auto text-[10px] h-5"
                  title={r.source === "tier2" ? `Override da watchlist "${r.watchlist_name}"` : "Regola globale"}
                >
                  {r.source === "tier2" ? `WL: ${r.watchlist_name}` : "Globale"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
        <div className="text-[10px] text-muted-foreground mt-3 italic">
          Override per-stock disponibili in fasi future.
        </div>
      </CardContent>
    </Card>
  );
}
