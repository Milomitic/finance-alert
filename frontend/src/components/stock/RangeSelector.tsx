import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (range: string) => void;
}

const OPTIONS = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
  { key: "all", label: "All" },
];

export function RangeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-md border bg-muted/30 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={cn(
            "px-3 py-1 text-xs font-medium rounded transition-colors",
            value === opt.key
              ? "bg-background shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
