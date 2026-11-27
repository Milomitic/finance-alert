import type { LiveAsset } from "@/hooks/useLiveAssets";
import type { RigaPanoramica } from "@/hooks/useMercati";

/* La panoramica dei mercati (FA-184): righe unite col paniere vivo. */

export type RigaUnita = RigaPanoramica & { prezzo: number | null; oggi: number | null; usaFuture: boolean };

/** Unisce la panoramica (chiusure giornaliere) col paniere vivo (prezzo e
 *  variazione di oggi, in frazione). Se il paniere non ha lo strumento, il
 *  prezzo e' l'ultima chiusura e «oggi» resta sconosciuto, non zero. */
export function unisciRighe(panoramica: RigaPanoramica[], vivi: LiveAsset[]): RigaUnita[] {
  const perSimbolo = new Map(vivi.map((a) => [a.symbol, a]));
  return panoramica.map((r) => {
    const v = perSimbolo.get(r.symbol);
    const oggi = v?.quote?.change_pct;
    return {
      ...r,
      prezzo: v?.quote?.price ?? r.ultima_chiusura,
      oggi: oggi == null ? null : oggi / 100,
      usaFuture: v?.using_futures === true,
    };
  });
}

/** Il valore di una colonna ordinabile. */
export function valoreColonna(r: RigaUnita, id: string): number | null {
  if (id === "oggi") return r.oggi;
  if (id === "max") return r.dal_massimo_storico?.distanza ?? null;
  if (id === "vol") return r.vol_20g;
  return r.rendimenti[id] ?? null;
}

/** Ordina tenendo gli sconosciuti in fondo in ENTRAMBI i versi: sconosciuto
 *  non e' zero, e non deve finire in cima a un ordinamento crescente. */
export function ordinaPer(righe: RigaUnita[], col: string, giu: boolean): RigaUnita[] {
  return [...righe].sort((a, b) => {
    const va = valoreColonna(a, col);
    const vb = valoreColonna(b, col);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return giu ? vb - va : va - vb;
  });
}
