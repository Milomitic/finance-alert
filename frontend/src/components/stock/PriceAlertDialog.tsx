import { useState } from "react";

import type { PriceAlert } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SelectField } from "@/components/ui/select-field";
import { currencySymbol } from "@/lib/money";
import { cn } from "@/lib/utils";
import {
  SelectItem,
} from "@/components/ui/select";

interface Props {
  open: boolean;
  initialPrice?: number;
  initialDirection?: "above" | "below";
  editing?: PriceAlert | null;
  onClose: () => void;
  onSubmit: (body: { target_price: number; direction: "above" | "below"; note: string | null }) => void;
  /** Valuta di quotazione del titolo. L'etichetta diceva "($)" per tutti,
   *  mentre 312 titoli su 1010 non sono in dollari: una soglia a 150 su un
   *  titolo di Milano sotto un simbolo del dollaro non e ambigua, e falsa.
   *  Assente = nessuna unita mostrata, mai una di ripiego. */
  currency?: string | null;
  /** Assente = nessun comando di eliminazione. Compare solo in modifica: in
   *  creazione non c'e' ancora nulla da distruggere. */
  onDelete?: (id: number) => void;
}

export function PriceAlertDialog({
  open, initialPrice, initialDirection, editing, onClose, onSubmit, onDelete,
  currency = null,
}: Props) {
  const unit = currencySymbol(currency);
  const [price, setPrice] = useState<string>("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string>("");
  /* Conferma IN LOCO: il pulsante diventa "Confermi?" invece di aprire un
     secondo modale sopra il primo. Eliminare distrugge una riga scritta a
     mano, senza annulla e senza cestino, quindi va chiesto — ma un dialog
     impilato su un dialog pesa piu' di quanto la decisione meriti, e il
     doppio passo nello stesso punto lascia il puntatore dov'e' gia'. */
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  /* ⚠️ Il modulo si azzera in RENDER quando cambia la SESSIONE di modifica.
   *
   * «Sessione» = questo dialog, aperto, su questo soggetto. La chiave la
   * riassume, cosi' riaprire sullo stesso avviso non azzera nulla mentre
   * passare da un avviso a un altro si'. Da dentro un effect il dialog
   * verrebbe DIPINTO una volta con i valori dell'avviso precedente: su una
   * finestra che chiede una conferma di eliminazione, mostrare per un
   * fotogramma il bersaglio sbagliato non e' un dettaglio estetico. */
  const sessione = open
    ? `${editing?.id ?? "nuovo"}|${initialPrice ?? ""}|${initialDirection ?? ""}`
    : null;
  /* La sentinella `undefined` distingue «mai visto» da «chiuso» (`null`):
   * senza, un dialog che monta GIA' aperto non azzererebbe il modulo, che
   * qui parte da stringhe vuote. Stessa ragione documentata in LogStream. */
  const [sessionePrec, setSessionePrec] = useState<string | null | undefined>(undefined);
  if (sessione !== sessionePrec) {
    setSessionePrec(sessione);
    if (sessione !== null) azzera();
  }

  function azzera() {
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
    // La conferma non sopravvive alla chiusura: riaprire deve ripartire da
    // "Elimina", non da un dialog gia' armato.
    setConfirmingDelete(false);
  }

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
          <DialogDescription className="sr-only">
            Imposta il prezzo obiettivo, la direzione e una nota opzionale per questo alert.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="price">
              Prezzo obiettivo{unit ? ` (${unit})` : ""}
            </Label>
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
          {/* L'etichetta era visibile e non associata: il bottone non aveva
              nome per chi ascolta. `SelectField` cabla i due id. */}
          <SelectField
            label="Direzione"
            value={direction}
            onValueChange={(v) => setDirection(v as "above" | "below")}
          >
            <SelectItem value="above">Above (sopra il target)</SelectItem>
            <SelectItem value="below">Below (sotto il target)</SelectItem>
          </SelectField>
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
        <DialogFooter className="sm:justify-between">
          {editing && onDelete ? (
            <Button
              variant={confirmingDelete ? "destructive" : "ghost"}
              className={cn(
                "min-h-[36px]",
                !confirmingDelete && "text-destructive hover:text-destructive",
              )}
              onClick={() => {
                if (!confirmingDelete) {
                  setConfirmingDelete(true);
                  return;
                }
                onDelete(editing.id);
              }}
            >
              {confirmingDelete ? "Confermi? Elimina" : "Elimina"}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex items-center gap-2">
            <Button variant="ghost" className="min-h-[36px]" onClick={onClose}>
              Annulla
            </Button>
            <Button className="min-h-[36px]" onClick={submit}>
              {editing ? "Salva" : "Crea"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
