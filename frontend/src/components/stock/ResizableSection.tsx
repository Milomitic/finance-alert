import { type ReactNode } from "react";

interface Props {
  /** Initial height in px (the user can drag-resize beyond this). */
  defaultHeight: number;
  /** Minimum height. The browser-native resize won't let the user shrink below. */
  minHeight?: number;
  label?: string;
  children: ReactNode;
}

/**
 * Vertically resizable section using CSS-native `resize: vertical`. No JS
 * drag handler needed — the browser provides the resizer affordance in the
 * bottom-right corner of the panel. We give the inner content `h-full` so
 * the chart inside reflows when the user drags.
 */
export function ResizableSection({ defaultHeight, minHeight = 80, label, children }: Props) {
  return (
    <div
      className="relative w-full overflow-auto resize-y border border-border/50 rounded-md bg-background/50"
      style={{ height: `${defaultHeight}px`, minHeight: `${minHeight}px` }}
    >
      {label && (
        <div className="absolute top-1 left-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground pointer-events-none z-10 bg-background/70 px-1 rounded">
          {label}
        </div>
      )}
      <div className="w-full h-full">{children}</div>
    </div>
  );
}
