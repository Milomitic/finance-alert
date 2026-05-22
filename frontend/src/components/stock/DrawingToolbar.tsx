import { Bell, Eraser, Minus, Slash } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type DrawingMode = "none" | "hline" | "trend" | "alert";

interface Props {
  mode: DrawingMode;
  onSetMode: (mode: DrawingMode) => void;
  onClearAll: () => void;
}

export function DrawingToolbar({ mode, onSetMode, onClearAll }: Props) {
  const Tool = ({
    target, label, icon: Icon, title,
  }: { target: DrawingMode; label: string; icon: typeof Bell; title: string }) => (
    <Button
      type="button"
      size="sm"
      variant={mode === target ? "default" : "outline"}
      onClick={() => onSetMode(mode === target ? "none" : target)}
      title={title}
      className={cn("text-sm h-8")}
    >
      <Icon className="h-3.5 w-3.5 mr-1" />
      {label}
    </Button>
  );

  return (
    <div className="inline-flex items-center gap-2">
      <Tool target="hline" label="H-line" icon={Minus} title="Disegna una linea orizzontale al prezzo cliccato" />
      <Tool target="trend" label="Linea" icon={Slash} title="Disegna una retta cliccando su due punti del grafico" />
      <Tool target="alert" label="Set alert" icon={Bell} title="Crea un price alert al prezzo cliccato" />
      <Button
        type="button" size="sm" variant="ghost" onClick={onClearAll}
        title="Rimuovi tutti i drawing per questo stock"
        className="text-sm h-8"
      >
        <Eraser className="h-3.5 w-3.5 mr-1" /> Clear
      </Button>
    </div>
  );
}
