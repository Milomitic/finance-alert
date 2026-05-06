import { Search, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  /** Optional className for the wrapping `<label>`; pass flex-shrink rules
   *  from the parent (e.g. `flex-1 min-w-0`) here. */
  className?: string;
  /** ARIA label for the input. Defaults to a generic Italian filter label. */
  ariaLabel?: string;
}

/**
 * Compact search input designed to live inside a column header next to
 * a sort label. Visual style:
 *   - tiny magnifying glass on the left
 *   - clear-button (X) on the right when populated
 *   - normal-case + tracking-normal so it doesn't inherit the column
 *     header's uppercase + wide tracking treatment
 *   - low-contrast bg that lifts on focus to show the input is active
 *
 * Used by:
 *   - Calendar earnings table (Stock column header)
 *   - Stock screener (Ticker column header — "ticker + name" search)
 *   - Alerts page table (Stock column header)
 */
export function TableSearchInput({
  value,
  onChange,
  placeholder = "cerca…",
  className,
  ariaLabel = "Filtra",
}: Props) {
  return (
    <label className={cn("relative flex items-center min-w-0", className)}>
      <Search className="absolute left-1.5 h-3 w-3 text-muted-foreground/70 pointer-events-none" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "w-full rounded border bg-background/60 pl-6 pr-6 py-0.5",
          // Override any uppercase + wide tracking inherited from
          // a column header so the placeholder reads naturally.
          "text-[12px] font-normal normal-case tracking-normal",
          "placeholder:text-muted-foreground/60",
          "focus:outline-none focus:ring-1 focus:ring-primary/40 focus:bg-background",
        )}
        aria-label={ariaLabel}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Cancella filtro"
          className="absolute right-1 inline-flex h-4 w-4 items-center justify-center rounded text-muted-foreground hover:text-foreground"
        >
          <X className="h-2.5 w-2.5" />
        </button>
      )}
    </label>
  );
}
