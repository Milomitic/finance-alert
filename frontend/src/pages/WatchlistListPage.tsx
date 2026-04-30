import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import type { WatchlistSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDeleteWatchlist, useWatchlists } from "@/hooks/useWatchlists";

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function WatchlistListPage() {
  const navigate = useNavigate();
  const list = useWatchlists();
  const deleteWl = useDeleteWatchlist();
  const [pendingDelete, setPendingDelete] = useState<WatchlistSummary | null>(null);

  const onConfirmDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteWl.mutateAsync(pendingDelete.id);
      toast.success(`Watchlist "${pendingDelete.name}" eliminata`);
    } catch {
      toast.error("Errore durante l'eliminazione");
    } finally {
      setPendingDelete(null);
    }
  };

  const renderEmpty = () => (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Nessuna watchlist</CardTitle>
        <CardDescription>
          Crea la tua prima watchlist per iniziare a monitorare gli stock.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild className="w-full">
          <Link to="/watchlists/new">
            <Plus className="mr-2 h-4 w-4" />
            Crea la tua prima watchlist
          </Link>
        </Button>
      </CardContent>
    </Card>
  );

  const renderTable = (rows: WatchlistSummary[]) => (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nome</TableHead>
              <TableHead>Descrizione</TableHead>
              <TableHead className="text-right">Stock</TableHead>
              <TableHead>Aggiornata</TableHead>
              <TableHead className="text-right">Azioni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((wl) => (
              <TableRow
                key={wl.id}
                className="cursor-pointer"
                onClick={() => navigate(`/watchlists/${wl.id}`)}
              >
                <TableCell className="font-medium">{wl.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {wl.description ?? "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">{wl.item_count}</TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(wl.updated_at)}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete(wl);
                    }}
                    aria-label={`Elimina ${wl.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Le mie watchlist</h2>
          <p className="text-sm text-muted-foreground">
            Crea e gestisci le tue selezioni di stock.
          </p>
        </div>
        <Button asChild>
          <Link to="/watchlists/new">
            <Plus className="mr-2 h-4 w-4" />
            Nuova watchlist
          </Link>
        </Button>
      </div>

      {list.isLoading && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">Caricamento…</CardContent>
        </Card>
      )}
      {list.isError && (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Errore nel caricamento delle watchlist.
          </CardContent>
        </Card>
      )}
      {list.data && list.data.length === 0 && renderEmpty()}
      {list.data && list.data.length > 0 && renderTable(list.data)}

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminare la watchlist?</DialogTitle>
            <DialogDescription>
              Stai per eliminare <strong>{pendingDelete?.name}</strong>. L'operazione non
              può essere annullata.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Annulla
            </Button>
            <Button
              variant="destructive"
              onClick={onConfirmDelete}
              disabled={deleteWl.isPending}
            >
              Elimina
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
