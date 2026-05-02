import { useEffect, useState } from "react";

import type { PriceAlert } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface Props {
  open: boolean;
  initialPrice?: number;
  initialDirection?: "above" | "below";
  editing?: PriceAlert | null;
  onClose: () => void;
  onSubmit: (body: { target_price: number; direction: "above" | "below"; note: string | null }) => void;
}

export function PriceAlertDialog({
  open, initialPrice, initialDirection, editing, onClose, onSubmit,
}: Props) {
  const [price, setPrice] = useState<string>("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setPrice(String(editing.target_price));
      setDirection(editing.direction);
      setNote(editing.note ?? "");
    } else {
      setPrice(initialPrice != null ? initialPrice.toFixed(2) : "");
      setDirection(initialDirection ?? "above");
      setNote("");
    }
    setError("");
  }, [open, editing, initialPrice, initialDirection]);

  const submit = () => {
    const num = parseFloat(price);
    if (Number.isNaN(num) || num <= 0) {
      setError("Inserisci un prezzo positivo");
      return;
    }
    onSubmit({ target_price: num, direction, note: note.trim() || null });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{editing ? "Modifica price alert" : "Nuovo price alert"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="price">Target price ($)</Label>
            <Input
              id="price"
              type="number"
              step="0.01"
              min="0"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <Label>Direzione</Label>
            <Select value={direction} onValueChange={(v) => setDirection(v as "above" | "below")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="above">Above (sopra il target)</SelectItem>
                <SelectItem value="below">Below (sotto il target)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="note">Nota (opzionale)</Label>
            <Input
              id="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="es. resistance level"
              maxLength={255}
            />
          </div>
          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Annulla</Button>
          <Button onClick={submit}>{editing ? "Salva" : "Crea"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
