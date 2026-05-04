import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

/**
 * Themed Radix tooltip wrapper, sibling-shape to popover.tsx.
 *
 * Why a custom tooltip vs the native `title` attribute:
 *  - Native `title` is browser-rendered, ~700ms delay, no rich formatting,
 *    no theming, and inaccessible to keyboard users on most browsers.
 *  - Radix tooltip respects `delayDuration`, supports keyboard focus,
 *    handles dismiss-on-escape, and lets us format multi-line content
 *    with proper typography.
 *
 * Usage in components: wrap a `<TooltipProvider>` around the page
 * (already done at the app root in main.tsx) so multiple Tooltip instances
 * share the same activation timer (Radix calls this "skip delay").
 */

const TooltipProvider = TooltipPrimitive.Provider;

const Tooltip = TooltipPrimitive.Root;

const TooltipTrigger = TooltipPrimitive.Trigger;

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        // Base: dark popover with light text (works in both color modes
        // because we invert via the theme tokens). Constrained max-width
        // so long explanations wrap into a readable column rather than a
        // 2000px line that escapes the viewport.
        "z-50 max-w-xs rounded-lg border border-border/60 bg-popover px-3 py-2 text-popover-foreground shadow-lg",
        // Animation tokens mirror Popover for visual consistency
        "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out-0 data-[state=delayed-open]:fade-in-0",
        "data-[state=closed]:zoom-out-95 data-[state=delayed-open]:zoom-in-95",
        "data-[side=bottom]:slide-in-from-top-1 data-[side=left]:slide-in-from-right-1",
        "data-[side=right]:slide-in-from-left-1 data-[side=top]:slide-in-from-bottom-1",
        "origin-[--radix-tooltip-content-transform-origin]",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
