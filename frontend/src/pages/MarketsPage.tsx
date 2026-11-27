import { Globe2 } from "lucide-react";

import { TabellaPanoramica } from "@/components/markets/TabellaPanoramica";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useLiveAssets } from "@/hooks/useLiveAssets";
import { usePanoramica } from "@/hooks/useMercati";
import { unisciRighe } from "@/lib/panoramica";

/* ─── Mercati (C-55, FA-184) ──────────────────────────────────────────────
 *
 * Prima l'elenco ripeteva il paniere della home in tre schede. Ora risponde a
 * cio' che la home non dice: come stanno andando i mercati su settimane e
 * mesi, quanto sono lontani dai massimi, quanto si muovono. Prezzo e «oggi»
 * vengono dal paniere vivo (cache condivisa con la home), i periodi dalla
 * panoramica alla chiusura giornaliera. */

export default function MarketsPage() {
  const vivi = useLiveAssets();
  const pan = usePanoramica();
  const righe = pan.data ? unisciRighe(pan.data.strumenti, vivi.data?.assets ?? []) : [];
  return (
    <div className="space-y-4">
      <h1 className="sr-only">Mercati</h1>
      <Card>
        <CardContent className="space-y-3 p-3 sm:p-4">
          <SectionTitle icon={Globe2} label="Mercati" />
          {pan.isError ? (
            <QueryError message="dei mercati" errore={pan.error} onRetry={() => pan.refetch()} isRetrying={pan.isFetching} />
          ) : pan.isLoading ? (
            <div className="h-[560px] animate-pulse rounded bg-muted/40" aria-hidden />
          ) : righe.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">Nessuno strumento.</p>
          ) : (
            <TabellaPanoramica righe={righe} allaChiusuraDel={pan.data?.alla_chiusura_del ?? null} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
