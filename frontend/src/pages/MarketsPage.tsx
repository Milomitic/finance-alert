import { Globe2 } from "lucide-react";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { ConfrontoNormalizzato } from "@/components/markets/ConfrontoNormalizzato";
import { ContestoMercato } from "@/components/markets/ContestoMercato";
import { MatriceCorrelazioni } from "@/components/markets/MatriceCorrelazioni";
import { OrariBorse } from "@/components/markets/OrariBorse";
import { TabellaPanoramica } from "@/components/markets/TabellaPanoramica";
import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useLiveAssets, useMercatiEstesi } from "@/hooks/useLiveAssets";
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
  const estesi = useMercatiEstesi();
  const pan = usePanoramica();
  // FA-190: il paniere della home piu' i mercati estesi, una lista sola.
  const tuttiVivi = [...(vivi.data?.assets ?? []), ...(estesi.data?.assets ?? [])];
  const righe = pan.data ? unisciRighe(pan.data.strumenti, tuttiVivi) : [];
  const nomi = Object.fromEntries(tuttiVivi.map((a) => [a.symbol, a.name]));
  const { hash } = useLocation();
  // Arrivando da «Confronta con altri mercati» si va al grafico: il router
  // non scorre da solo all'ancora, e la tabella sopra e' lunga.
  const pronta = pan.data != null;
  useEffect(() => {
    if (hash === "#confronto" && pronta) document.getElementById("confronto")?.scrollIntoView({ block: "start" });
  }, [hash, pronta]);
  return (
    <div className="space-y-4">
      <h1 className="sr-only">Mercati</h1>
      <Card>
        <CardContent className="space-y-3 p-3 sm:p-4">
          <SectionTitle icon={Globe2} label="Mercati" />
          {/* FA-191: in che fase e' ogni borsa, e quanto manca al cambio. */}
          <OrariBorse />
          {/* FA-188: tassi, volatilita' attesa, ampiezza, dollaro. */}
          <ContestoMercato />
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
      {/* FA-187: il confronto in base 100, anche con titoli del catalogo. */}
      <Card>
        <CardContent className="p-3 sm:p-4">
          <ConfrontoNormalizzato nomi={nomi} />
        </CardContent>
      </Card>
      {/* FA-189: le correlazioni fra mercati, adesso e un anno prima. */}
      <Card>
        <CardContent className="p-3 sm:p-4">
          <MatriceCorrelazioni />
        </CardContent>
      </Card>
    </div>
  );
}
