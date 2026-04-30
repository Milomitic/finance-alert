import { useState } from "react";

import type { Stock } from "@/api/types";
import { StockFiltersTab } from "@/components/StockFiltersTab";
import { StockSearchTab } from "@/components/StockSearchTab";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function WatchlistDetailPage() {
  // I3 will wire actual watchlist state here
  const [pickedIds] = useState<Set<number>>(new Set());

  const handleAdd = (_stock: Stock) => {
    // I3 will replace with real autosave POST to /api/watchlists/:id/items
    console.log("add stock placeholder", _stock.ticker);
  };

  const handleAddBulk = (_list: Stock[]) => {
    console.log("add bulk placeholder", _list.length);
  };

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
          <CardTitle className="text-base">Watchlist</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Pannello watchlist (autosave) — Task I3.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
