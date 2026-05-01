import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  code: string | null | undefined;
  size?: "xs" | "sm" | "md";
  showCode?: boolean;
}

const SIZE_CLASSES: Record<NonNullable<Props["size"]>, string> = {
  xs: "text-xs px-1.5 py-0.5 gap-1",
  sm: "text-sm px-2 py-0.5 gap-1.5",
  md: "text-base px-2.5 py-1 gap-2",
};

const FLAG_HEIGHT_PX: Record<NonNullable<Props["size"]>, number> = {
  xs: 11,
  sm: 14,
  md: 18,
};

export function IndexBadge({ code, size = "sm", showCode = true }: Props) {
  if (!code) return <span className="text-muted-foreground">—</span>;
  const meta = getIndexMeta(code);
  const flagHeight = FLAG_HEIGHT_PX[size];
  // Force a 3:2 aspect ratio so the US flag (natively 1.9:1) doesn't render
  // wider than the others. `object-fit: cover` slightly crops the US flag's
  // horizontal stripes; EU/IT/CN/HK (all 3:2 source) fill the box exactly.
  const flagWidth = Math.round(flagHeight * 1.5);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md bg-muted/60 dark:bg-muted/40 font-medium tabular-nums",
        SIZE_CLASSES[size],
      )}
      title={`${meta.fullName} · ${meta.country}`}
    >
      {meta.countryCode && (
        <img
          src={`/flags/${meta.countryCode}.svg`}
          alt={meta.country}
          width={flagWidth}
          height={flagHeight}
          style={{
            width: `${flagWidth}px`,
            height: `${flagHeight}px`,
            objectFit: "cover",
          }}
          className="rounded-[1px] shadow-sm shrink-0"
        />
      )}
      {showCode && <span>{code}</span>}
    </span>
  );
}
