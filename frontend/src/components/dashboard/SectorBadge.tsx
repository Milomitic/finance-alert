import { Link } from "react-router-dom";

import { getSectorIcon } from "@/lib/sectorMeta";
import { cn } from "@/lib/utils";

interface Props {
  sector: string | null | undefined;
  variant?: "icon-only" | "icon-text";
  size?: "xs" | "sm";
  /** When true (default), the badge is wrapped in a <Link> to the
   *  sector recap page. Set to false in contexts where the parent is
   *  itself a link (avoids nested anchors which is invalid HTML). */
  clickable?: boolean;
}

export function SectorBadge({
  sector,
  variant = "icon-text",
  size = "sm",
  clickable = true,
}: Props) {
  if (!sector) return <span className="text-muted-foreground text-xs">—</span>;
  const Icon = getSectorIcon(sector);
  const iconSize = size === "xs" ? "h-3 w-3" : "h-3.5 w-3.5";
  const href = `/sectors/${encodeURIComponent(sector)}`;

  if (variant === "icon-only") {
    const inner = (
      <span className="inline-flex items-center" title={sector}>
        <Icon className={cn(iconSize, "text-muted-foreground")} />
      </span>
    );
    return clickable ? (
      <Link to={href} onClick={(e) => e.stopPropagation()}>
        {inner}
      </Link>
    ) : inner;
  }

  const inner = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md bg-muted/60 dark:bg-muted/40",
        size === "xs" ? "text-[10px] px-1.5 py-0" : "text-xs px-2 py-0.5",
        clickable && "hover:bg-muted/80 transition-colors",
      )}
      title={sector}
    >
      <Icon className={cn(iconSize, "text-muted-foreground")} />
      <span className="truncate max-w-[100px]">{sector}</span>
    </span>
  );

  return clickable ? (
    <Link
      to={href}
      onClick={(e) => e.stopPropagation()}
      className="inline-flex"
    >
      {inner}
    </Link>
  ) : inner;
}
