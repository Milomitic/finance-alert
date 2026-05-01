import { getSectorIcon } from "@/lib/sectorMeta";
import { cn } from "@/lib/utils";

interface Props {
  sector: string | null | undefined;
  variant?: "icon-only" | "icon-text";
  size?: "xs" | "sm";
}

export function SectorBadge({ sector, variant = "icon-text", size = "sm" }: Props) {
  if (!sector) return <span className="text-muted-foreground text-xs">—</span>;
  const Icon = getSectorIcon(sector);
  const iconSize = size === "xs" ? "h-3 w-3" : "h-3.5 w-3.5";

  if (variant === "icon-only") {
    return (
      <span className="inline-flex items-center" title={sector}>
        <Icon className={cn(iconSize, "text-muted-foreground")} />
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md bg-muted/60 dark:bg-muted/40",
        size === "xs" ? "text-[10px] px-1.5 py-0" : "text-xs px-2 py-0.5",
      )}
      title={sector}
    >
      <Icon className={cn(iconSize, "text-muted-foreground")} />
      <span className="truncate max-w-[100px]">{sector}</span>
    </span>
  );
}
