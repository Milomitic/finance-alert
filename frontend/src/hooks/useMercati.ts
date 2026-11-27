import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/* ─── Panoramica dei rendimenti e statistiche di un mercato (FA-184/185) ──
 *
 * Forme del server: `RigaPanoramicaOut`, `PanoramicaOut`, `StatisticheOut` in
 * `backend/app/api/market_detail.py` (i nomi coincidono, cosi' il controllo
 * dei tipi generati li confronta da solo). Rendimenti come frazioni (0,05 =
 * +5%); un periodo che la storia non copre e' null, non zero. */

export interface Estremo {
  valore: number;
  data: string;
  distanza: number;
  sedute_da: number;
}

export interface RigaPanoramica {
  symbol: string;
  name: string;
  category: string;
  flag: string | null;
  ultima_chiusura: number;
  data_chiusura: string;
  rendimenti: Record<string, number | null>;
  massimo_52s: Estremo | null;
  minimo_52s: Estremo | null;
  posizione_52s: number | null;
  dal_massimo_storico: Estremo | null;
  vol_20g: number | null;
  vol_1a: number | null;
  distanza_ema200: number | null;
}

export interface Panoramica {
  alla_chiusura_del: string | null;
  strumenti: RigaPanoramica[];
}

export interface Calo {
  profondita: number;
  picco?: string | null;
  minimo?: string | null;
  recupero?: string | null;
}

export interface CaloCorrente {
  profondita: number;
  picco: string;
  sedute_dal_picco: number;
}

export interface AnnoCalendario {
  anno: number;
  mesi: (number | null)[];
  anno_totale: number | null;
  parziale: boolean;
}

export interface Calendario {
  anni: AnnoCalendario[];
  media_mesi: (number | null)[];
  positivi_mesi: (number | null)[];
  casi_mesi: number[];
  ultimo_mese: string | null;
}

export interface Statistiche {
  symbol: string;
  data_chiusura: string;
  dal: string;
  rendimenti: Record<string, number | null>;
  vol_20g: number | null;
  vol_1a: number | null;
  massimo_52s: Estremo | null;
  minimo_52s: Estremo | null;
  dal_massimo_storico: Estremo | null;
  calo_corrente: CaloCorrente | null;
  calo_massimo_1a: Calo | null;
  calo_massimo_5a: Calo | null;
  calo_massimo_storico: Calo | null;
  calendario: Calendario;
}

export function usePanoramica() {
  return useQuery({
    queryKey: ["markets", "panoramica"],
    queryFn: ({ signal }) => api<Panoramica>("/api/markets/panoramica", { signal }),
    staleTime: 5 * 60_000,
  });
}

export function useStatisticheMercato(simbolo: string) {
  return useQuery({
    queryKey: ["markets", "statistiche", simbolo],
    queryFn: ({ signal }) => api<Statistiche>(`/api/markets/${encodeURIComponent(simbolo)}/statistiche`, { signal }),
    staleTime: 5 * 60_000,
    enabled: !!simbolo,
  });
}
