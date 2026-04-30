import { useRef, useState } from "react";
import { useParams } from "react-router-dom";

import type { Stock } from "@/api/types";
import { StockFiltersTab } from "@/components/StockFiltersTab";
import { StockSearchTab } from "@/components/StockSearchTab";
import {
  WatchlistEditor,
  type WatchlistEditorHandle,
} from "@/components/WatchlistEditor";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWatchlistDetail } from "@/hooks/useWatchlists";

export default function WatchlistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const numericId = id ? Number.parseInt(id, 10) : null;
  const detailQuery = useWatchlistDetail(numericId);

  const editorRef = useRef<WatchlistEditorHandle | null>(null);
  const [, setTick] = useState(0);
  const forceTick = () => setTick((v) => v + 1);

  const handleAdd = async (stock: Stock) => {
    await editorRef.current?.addStock(stock);
    forceTick();
  };
  const handleAddBulk = async (list: Stock[]) => {
    await editorRef.current?.addBulk(list);
    forceTick();
  };

  const pickedIds = editorRef.current?.pickedIds ?? new Set<number>();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Aggiungi stock</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="search">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="search">Ricerca singola</TabsTrigger>
              <TabsTrigger value="filters">Filtri combinati</TabsTrigger>
            </TabsList>
            <TabsContent value="search" className="pt-4">
              <StockSearchTab onAdd={handleAdd} excludeIds={pickedIds} />
            </TabsContent>
            <TabsContent value="filters" className="pt-4">
              <StockFiltersTab onAddBulk={handleAddBulk} excludeIds={pickedIds} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {numericId ? "Watchlist" : "Nuova watchlist"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {numericId !== null && detailQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Caricamento…</p>
          )}
          {numericId !== null && detailQuery.isError && (
            <p className="text-sm text-destructive">Errore caricamento.</p>
          )}
          {(numericId === null || detailQuery.data !== undefined) && (
            <WatchlistEditor
              ref={editorRef}
              detail={numericId !== null ? detailQuery.data ?? null : null}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
