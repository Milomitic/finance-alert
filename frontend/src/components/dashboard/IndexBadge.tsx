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

export function IndexBadge({ code, size = "sm", showCode = true }: Props) {
  if (!code) return <span className="text-muted-foreground">—</span>;
  const meta = getIndexMeta(code);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md bg-muted/60 dark:bg-muted/40 font-medium tabular-nums",
        SIZE_CLASSES[size],
      )}
      title={`${meta.fullName} · ${meta.country}`}
    >
      <span aria-hidden="true">{meta.flag}</span>
      {showCode && <span>{code}</span>}
    </span>
  );
}
