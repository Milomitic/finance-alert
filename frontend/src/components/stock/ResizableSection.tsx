import { type PointerEvent as ReactPointerEvent, type ReactNode, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  /** Initial height in px. */
  defaultHeight: number;
  /** Minimum height the drag can shrink to. */
  minHeight?: number;
  label?: string;
  children: ReactNode;
}

/**
 * Vertically resizable section with an explicit, touch-capable drag handle at
 * the bottom. The old version relied on CSS `resize: vertical`, whose only
 * affordance was a hard-to-find corner grip that doesn't work on touch at all.
 * A Pointer Events handle works for mouse AND touch, and the visible grip bar
 * makes the affordance obvious.
 */
export function ResizableSection({ defaultHeight, minHeight = 80, label, children }: Props) {
  const [height, setHeight] = useState(defaultHeight);
  const drag = useRef<{ startY: number; startH: number } | null>(null);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = { startY: e.clientY, startH: height };
    e.currentTarget.setPointerCapture(e.pointerId); // keep events even off the handle
    e.preventDefault();
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const next = drag.current.startH + (e.clientY - drag.current.startY);
    setHeight(Math.max(minHeight, next));
  };
  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    drag.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* pointer already released */
    }
  };

  return (
    <div
      className="relative w-full overflow-hidden border border-border/50 rounded-md bg-background/50"
      style={{ height: `${height}px` }}
    >
      {label && (
        <div className="absolute top-1 left-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground pointer-events-none z-10 bg-background/70 px-1 rounded">
          {label}
        </div>
      )}
      {/* Inner content sits above the handle's height so the chart never
          renders under the grip. */}
      <div className="w-full" style={{ height: `${height - 10}px` }}>
        {children}
      </div>
      {/* Drag handle — full-width bottom bar, touch-action:none so a touch
          drag resizes instead of scrolling the page. */}
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Ridimensiona"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "absolute bottom-0 left-0 right-0 h-2.5 flex items-center justify-center",
          "cursor-ns-resize touch-none select-none",
          "bg-muted/40 hover:bg-muted/70 transition-colors",
        )}
        style={{ touchAction: "none" }}
      >
        <span className="h-0.5 w-8 rounded-full bg-muted-foreground/40" />
      </div>
    </div>
  );
}
