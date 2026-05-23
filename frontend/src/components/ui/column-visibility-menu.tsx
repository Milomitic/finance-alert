import type { ColumnDef } from "@/hooks/useColumnVisibility";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface Props {
  columns: ColumnDef[];
  isVisible: (id: string) => boolean;
  toggle: (id: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Viewport-relative pixel coordinates where the context-menu was triggered. */
  anchor: { x: number; y: number };
}

/**
 * A right-click column visibility menu.
 *
 * Rendered as a controlled `DropdownMenu` whose trigger is an invisible
 * 0-size element pinned (via `position: fixed`) to the cursor position
 * at the time of the right-click.  When `open` flips to true, Radix
 * opens the menu anchored to that element — giving the appearance of a
 * context menu that appears exactly under the cursor.
 *
 * The parent is responsible for:
 *   1. Calling `e.preventDefault()` in `onContextMenu` so the browser's
 *      native context menu is suppressed.
 *   2. Setting `open = true` and recording `anchor = { x: e.clientX, y: e.clientY }`.
 *   3. Passing `onOpenChange` so Radix can close the menu on Escape / blur.
 */
export function ColumnVisibilityMenu({
  columns,
  isVisible,
  toggle,
  open,
  onOpenChange,
  anchor,
}: Props) {
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      {/* Zero-size fixed trigger placed at the right-click coords */}
      <DropdownMenuTrigger asChild>
        <span
          aria-hidden
          style={{
            position: "fixed",
            top: anchor.y,
            left: anchor.x,
            width: 0,
            height: 0,
            pointerEvents: "none",
          }}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[180px]">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          Colonne visibili
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {columns.map((col) => (
          <DropdownMenuCheckboxItem
            key={col.id}
            checked={isVisible(col.id)}
            onCheckedChange={() => toggle(col.id)}
          >
            {col.label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
