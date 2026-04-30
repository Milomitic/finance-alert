import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import type { Stock, WatchlistDetail } from "@/api/types";
import { watchlists } from "@/api/watchlists";
import { SaveIndicator, type SaveState } from "@/components/SaveIndicator";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

export interface WatchlistEditorHandle {
  pickedIds: Set<number>;
  addStock: (stock: Stock) => Promise<void>;
  addBulk: (stocks: Stock[]) => Promise<void>;
}

interface Props {
  detail: WatchlistDetail | null;
  ref?: Ref<WatchlistEditorHandle>;
}

const TEXT_DEBOUNCE_MS = 500;

export function WatchlistEditor({ detail, ref }: Props) {
  const navigate = useNavigate();
  const [name, setName] = useState(detail?.name ?? "");
  const [description, setDescription] = useState(detail?.description ?? "");
  const [stocks, setStocks] = useState<Stock[]>(detail?.stocks ?? []);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const idRef = useRef<number | null>(detail?.id ?? null);
  const inFlightRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPatchRef = useRef<{ name?: string; description?: string | null } | null>(null);

  useEffect(() => {
    if (detail) {
      idRef.current = detail.id;
      setName(detail.name);
      setDescription(detail.description ?? "");
      setStocks(detail.stocks);
    }
  }, [detail]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (inFlightRef.current) inFlightRef.current.abort();
    };
  }, []);

  const performTextSave = async (payload: {
    name?: string;
    description?: string | null;
  }) => {
    if (inFlightRef.current) inFlightRef.current.abort();
    const ctrl = new AbortController();
    inFlightRef.current = ctrl;
    setSaveState("saving");
    lastPatchRef.current = payload;
    try {
      if (idRef.current === null) {
        if (!payload.name || !payload.name.trim()) {
          setSaveState("idle");
          return;
        }
        const created = await watchlists.create({
          name: payload.name.trim(),
          description: payload.description ?? null,
        });
        if (ctrl.signal.aborted) return;
        idRef.current = created.id;
        setStocks(created.stocks);
        navigate(`/watchlists/${created.id}`, { replace: true });
        setSaveState("saved");
      } else {
        await watchlists.patch(idRef.current, payload, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setSaveState("saved");
      }
    } catch (err) {
      if (ctrl.signal.aborted) return;
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (err instanceof ApiError && err.status === 409) {
        setSaveState("error");
        toast.error("Esiste già una watchlist con questo nome");
        return;
      }
      setSaveState("error");
    }
  };

  const scheduleTextSave = (payload: {
    name?: string;
    description?: string | null;
  }) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void performTextSave(payload);
    }, TEXT_DEBOUNCE_MS);
  };

  const onNameChange = (value: string) => {
    setName(value);
    if (value.trim().length === 0) {
      setSaveState("idle");
      if (debounceRef.current) clearTimeout(debounceRef.current);
      return;
    }
    scheduleTextSave({ name: value.trim() });
  };

  const onDescriptionChange = (value: string) => {
    setDescription(value);
    if (idRef.current === null && name.trim().length === 0) {
      return;
    }
    scheduleTextSave({ description: value || null });
  };

  const ensurePersisted = async (): Promise<number | null> => {
    if (idRef.current !== null) return idRef.current;
    if (!name.trim()) {
      toast.error("Inserisci un nome per iniziare");
      return null;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (inFlightRef.current) inFlightRef.current.abort();
    setSaveState("saving");
    try {
      const created = await watchlists.create({
        name: name.trim(),
        description: description || null,
      });
      idRef.current = created.id;
      setStocks(created.stocks);
      navigate(`/watchlists/${created.id}`, { replace: true });
      setSaveState("saved");
      return created.id;
    } catch (err) {
      setSaveState("error");
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Esiste già una watchlist con questo nome");
      }
      return null;
    }
  };

  const onAddStock = async (stock: Stock) => {
    const id = await ensurePersisted();
    if (id === null) return;
    if (stocks.some((s) => s.id === stock.id)) return;
    const previous = stocks;
    const optimistic = [...stocks, stock];
    setStocks(optimistic);
    setSaveState("saving");
    try {
      await watchlists.addItems(id, [stock.id]);
      setSaveState("saved");
    } catch {
      setStocks(previous);
      setSaveState("error");
      toast.error(`Errore aggiunta ${stock.ticker}`);
    }
  };

  const onAddBulk = async (incoming: Stock[]) => {
    const id = await ensurePersisted();
    if (id === null) return;
    const known = new Set(stocks.map((s) => s.id));
    const fresh = incoming.filter((s) => !known.has(s.id));
    if (fresh.length === 0) return;
    const previous = stocks;
    const optimistic = [...stocks, ...fresh];
    setStocks(optimistic);
    setSaveState("saving");
    try {
      const result = await watchlists.addItems(
        id,
        fresh.map((s) => s.id)
      );
      setSaveState("saved");
      toast.success(`${result.added} stock aggiunti`);
    } catch {
      setStocks(previous);
      setSaveState("error");
      toast.error("Errore durante l'aggiunta");
    }
  };

  const onRemoveStock = async (stock: Stock) => {
    if (idRef.current === null) return;
    const previous = stocks;
    setStocks(stocks.filter((s) => s.id !== stock.id));
    setSaveState("saving");
    try {
      await watchlists.removeItem(idRef.current, stock.id);
      setSaveState("saved");
    } catch {
      setStocks(previous);
      setSaveState("error");
      toast.error(`Errore rimozione ${stock.ticker}`);
    }
  };

  const onDeleteWatchlist = async () => {
    if (idRef.current === null) {
      navigate("/watchlists");
      return;
    }
    try {
      await watchlists.delete(idRef.current);
      toast.success("Watchlist eliminata");
      navigate("/watchlists");
    } catch {
      toast.error("Errore durante l'eliminazione");
    }
  };

  const retryLast = () => {
    if (lastPatchRef.current) void performTextSave(lastPatchRef.current);
  };

  useImperativeHandle(
    ref,
    () => ({
      pickedIds: new Set(stocks.map((s) => s.id)),
      addStock: onAddStock,
      addBulk: onAddBulk,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stocks]
  );

  const isCreateModeNotPersisted = idRef.current === null;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 flex-1">
          <Label htmlFor="wl-name">Nome</Label>
          <Input
            id="wl-name"
            value={name}
            placeholder="es. Tech USA"
            onChange={(e) => onNameChange(e.target.value)}
            maxLength={100}
          />
        </div>
        <div className="pt-7">
          <SaveIndicator state={saveState} onRetry={retryLast} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="wl-desc">Descrizione (opzionale)</Label>
        <Textarea
          id="wl-desc"
          value={description}
          placeholder="Descrivi questa watchlist…"
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={2}
        />
      </div>

      {isCreateModeNotPersisted && !name.trim() && (
        <p className="text-xs text-muted-foreground">
          Inserisci un nome per iniziare. Gli stock selezionati verranno aggiunti
          dopo.
        </p>
      )}

      <div className="rounded border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticker</TableHead>
              <TableHead>Nome</TableHead>
              <TableHead>Exchange</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stocks.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="text-sm text-muted-foreground text-center py-6"
                >
                  Nessuno stock. Aggiungi dal pannello a sinistra.
                </TableCell>
              </TableRow>
            )}
            {stocks.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="font-medium">{s.ticker}</TableCell>
                <TableCell className="truncate max-w-[200px]">{s.name}</TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {s.exchange}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onRemoveStock(s)}
                    aria-label={`Rimuovi ${s.ticker}`}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {idRef.current !== null && (
        <div className="pt-2">
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Elimina watchlist
          </Button>
        </div>
      )}

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminare la watchlist?</DialogTitle>
            <DialogDescription>
              Stai per eliminare <strong>{name || "questa watchlist"}</strong>.
              L'operazione non può essere annullata.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Annulla
            </Button>
            <Button variant="destructive" onClick={onDeleteWatchlist}>
              Elimina
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
