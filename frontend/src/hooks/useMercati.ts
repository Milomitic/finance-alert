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

// ─── FA-186: composizione dell'indice ────────────────────────────────────

export interface IndiceComposizione {
  code: string;
  nome: string;
  titoli_nel_catalogo: number;
  nota: string | null;
  pesato_sul_prezzo: boolean;
}

export interface AmpiezzaIndice {
  avanzano: number;
  scendono: number;
  sopra_ema50_pct: number | null;
  sopra_ema200_pct: number | null;
  nuovi_massimi_52s: number;
  nuovi_minimi_52s: number;
  rsi_sopra_70: number;
  rsi_sotto_30: number;
  var_media_pct: number | null;
}

export interface SettoreIndice {
  settore: string;
  titoli: number;
  var_media_pct: number | null;
  peso_pct: number | null;
}

/** ⚠️ `var_pct` e `contributo_pp` in PUNTI percentuali, non frazioni. */
export interface Costituente {
  ticker: string;
  nome: string;
  settore: string;
  var_pct: number | null;
  peso_pct: number | null;
  contributo_pp: number | null;
}

export interface Composizione {
  indice: IndiceComposizione;
  ampiezza: AmpiezzaIndice;
  settori: SettoreIndice[];
  migliori: Costituente[];
  peggiori: Costituente[];
  alla_scansione_del: string | null;
}

/** 404 quando il catalogo non ha i costituenti: non e' un errore da mostrare. */
export function useComposizione(simbolo: string, attivo: boolean) {
  return useQuery({
    queryKey: ["markets", "composizione", simbolo],
    queryFn: ({ signal }) => api<Composizione>(`/api/markets/${encodeURIComponent(simbolo)}/composizione`, { signal }),
    staleTime: 5 * 60_000,
    enabled: attivo && !!simbolo,
    retry: false,
  });
}

// ─── FA-187: confronto normalizzato ──────────────────────────────────────

export interface RiepilogoConfrontoMercati {
  rendimento: number;
  peggior_calo: number;
}

export interface ConfrontoMercati {
  date: string[];
  serie: Record<string, number[]>;
  riepilogo: Record<string, RiepilogoConfrontoMercati>;
  dal: string | null;
  al: string | null;
}

export const PERIODI_CONFRONTO = ["1m", "3m", "6m", "ytd", "1a", "3a", "5a", "10a"] as const;
export type PeriodoConfronto = (typeof PERIODI_CONFRONTO)[number];

export function useConfronto(simboli: string[], periodo: PeriodoConfronto) {
  return useQuery({
    queryKey: ["markets", "confronto", simboli.join(","), periodo],
    queryFn: ({ signal }) => api<ConfrontoMercati>(
      `/api/markets/confronto?simboli=${encodeURIComponent(simboli.join(","))}&periodo=${periodo}`, { signal }),
    staleTime: 5 * 60_000,
    enabled: simboli.length > 0,
    retry: false,
    placeholderData: (prev) => prev,
  });
}
