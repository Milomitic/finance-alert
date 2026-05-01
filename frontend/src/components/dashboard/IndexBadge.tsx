import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  code: string | null | undefined;
  size?: "xs" | "sm" | "md";
  showCode?: boolean;
}

const SIZE_CLASSES: Record<NonNullable<Props["size"]>, string> = {
  xs: "text-[10px] px-1.5 py-0 gap-1",
  sm: "text-xs px-2 py-0.5 gap-1.5",
  md: "text-sm px-2.5 py-1 gap-2",
};

const FLAG_HEIGHT_PX: Record<NonNullable<Props["size"]>, number> = {
  xs: 9,
  sm: 11,
  md: 13,
};

export function IndexBadge({ code, size = "sm", showCode = true }: Props) {
  if (!code) return <span className="text-muted-foreground">—</span>;
  const meta = getIndexMeta(code);
  const flagHeight = FLAG_HEIGHT_PX[size];
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
          height={flagHeight}
          style={{ height: `${flagHeight}px`, width: "auto" }}
          className="rounded-[1px] shadow-sm"
        />
      )}
      {showCode && <span>{code}</span>}
    </span>
  );
}
