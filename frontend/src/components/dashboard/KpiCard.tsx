import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  title: string;
  value: ReactNode;
  subtext?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "success" | "warning" | "destructive";
}

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  default: "",
  success: "border-green-300/50 dark:border-green-800/50",
  warning: "border-amber-300/50 dark:border-amber-800/50",
  destructive: "border-destructive/50",
};

export function KpiCard({ title, value, subtext, icon, tone = "default" }: Props) {
  return (
    <Card className={cn(TONE[tone])}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="text-xs text-muted-foreground uppercase tracking-wide">
            {title}
          </div>
          {icon && <div className="text-muted-foreground">{icon}</div>}
        </div>
        <div className="text-2xl font-semibold tabular-nums mt-1">{value}</div>
        {subtext && (
          <div className="text-xs text-muted-foreground mt-1">{subtext}</div>
        )}
      </CardContent>
    </Card>
  );
}
