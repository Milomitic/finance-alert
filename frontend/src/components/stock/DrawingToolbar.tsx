import { Bell, Eraser, Minus, Slash, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";

export type DrawingMode = "none" | "hline" | "trend" | "alert" | "erase";

interface Props {
  mode: DrawingMode;
  onSetMode: (mode: DrawingMode) => void;
  onClearAll: () => void;
}

/* The four tools used to be rendered by a `Tool` component declared inside
 * DrawingToolbar's body. That made it a NEW component type on every render, so
 * React remounted all four buttons whenever the mode changed — and since the
 * mode changes exactly when you press one, the button you just pressed was
 * destroyed underneath you. Focus went with it: keyboard users landed on
 * <body>. See DrawingToolbar.test.tsx.
 *
 * A table plus a `.map()` fixes it without threading `mode`/`onSetMode` through
 * a sub-component's props, because there is no sub-component left to thread
 * them into. `Button` is imported from the module scope, so its type is stable
 * by construction. */
const TOOLS: {
  target: DrawingMode;
  label: string;
  icon: typeof Bell;
  title: string;
}[] = [
  { target: "hline", label: "H-line", icon: Minus, title: "Disegna una linea orizzontale al prezzo cliccato" },
  { target: "trend", label: "Linea", icon: Slash, title: "Disegna una retta cliccando su due punti del grafico" },
  { target: "alert", label: "Set alert", icon: Bell, title: "Crea un price alert al prezzo cliccato" },
  { target: "erase", label: "Cancella", icon: Eraser, title: "Clicca su una linea/retta per cancellarla" },
];

export function DrawingToolbar({ mode, onSetMode, onClearAll }: Props) {
  return (
    <div className="inline-flex items-center gap-2">
      {TOOLS.map(({ target, label, icon: Icon, title }) => {
        const active = mode === target;
        return (
          <Button
            key={target}
            type="button"
            size="sm"
            variant={active ? "default" : "outline"}
            // These are toggles, not commands: pressing "Linea" arms the tool
            // and stays armed. Only the fill said so, which a screen reader
            // does not read.
            aria-pressed={active}
            onClick={() => onSetMode(active ? "none" : target)}
            title={title}
            className="text-sm h-8"
          >
            <Icon className="h-3.5 w-3.5 mr-1" aria-hidden />
            {label}
          </Button>
        );
      })}
      <Button
        type="button" size="sm" variant="ghost" onClick={onClearAll}
        title="Rimuovi tutti i drawing per questo stock"
        className="text-sm h-8"
      >
        <Trash2 className="h-3.5 w-3.5 mr-1" aria-hidden /> Pulisci
      </Button>
    </div>
  );
}
