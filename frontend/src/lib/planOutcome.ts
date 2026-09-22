/* ─── Raccontare una gara stop-contro-target ──────────────────────────────
 *
 * Calcolo puro, fuori dal JSX, perche' ogni riga di questa vista e'
 * un'affermazione su un trade che non e' stato fatto: va poter essere provata.
 *
 * ⚠️ La regola che questa vista esiste per rendere visibile: la posizione si
 * chiude alla PRIMA gamba toccata — target o stop, chi arriva prima — ma le
 * altre gambe si mostrano lo stesso, con la loro data. «Stop il 5, target il
 * 18» vale -1R ed e' giusto, perche' la posizione era chiusa; e dice anche
 * che quello stop era troppo stretto e il trade aveva ragione. Quel secondo
 * fatto non e' ricavabile dall'esito, ed e' esattamente cio' che si perde
 * contando solo chi ha vinto.
 *
 * ⚠️ E non e' un «ha mai toccato il target». Contare i soli tocchi produce un
 * tasso lusinghiero per costruzione — quasi tutto tocca un target vicino,
 * prima o poi — che non corrisponde a nessun guadagno, perche' una posizione
 * con quel target aveva anche uno stop e si sarebbe chiusa da sola in perdita.
 */

/** Il minimo che serve per raccontare una gara.
 *
 *  ⚠️ Una forma STRUTTURALE, non `PlanOutcomeRow`: la stessa gara arriva da
 *  due percorsi — l'elenco degli esiti (che porta anche titolo e detector) e
 *  il campo `plan` di un alert (che no) — e legare queste funzioni al tipo
 *  piu' ricco costringerebbe il secondo chiamante a inventare i campi che non
 *  ha. Entrambi i tipi soddisfano questo. */
export interface GaraDiPiano {
  /** tp1 | stop | ambigua | scaduto */
  esito: string;
  resolved_date: string;
  r_multiple: number;
  stop_hit_date: string | null;
  tp1_hit_date: string | null;
  tp2_hit_date: string | null;
}

export interface Gamba {
  chiave: "stop" | "tp1" | "tp2";
  etichetta: string;
  data: string;
  /** Questa gamba ha CHIUSO la posizione. */
  chiude: boolean;
  /** Toccata DOPO la chiusura: il prezzo ci e' arrivato, ma la posizione non
   *  c'era piu'. Mostrarla senza dirlo la farebbe leggere come un guadagno. */
  dopo: boolean;
}

/** Chi ha chiuso la posizione, per esito. `null` = l'ha chiusa l'orizzonte,
 *  senza che nessuna gamba fosse toccata.
 *
 *  ⚠️ `ambigua` (stop e target nella STESSA barra) e' assegnata allo stop: il
 *  dato giornaliero non dice quale sia venuto prima, e la convenzione
 *  pessimista e' l'unica che non si auto-elogia. Resta una categoria a se'
 *  per poter misurare, dopo, quanto costa. */
export function gambaChiudente(esito: string): "stop" | "tp1" | null {
  if (esito === "tp1") return "tp1";
  if (esito === "stop" || esito === "ambigua") return "stop";
  return null;
}

/** Le gambe toccate, in ORDINE CRONOLOGICO.
 *
 *  A parita' di data lo stop viene per primo, per la stessa ragione per cui
 *  una barra ambigua si assegna allo stop. */
export function sequenzaGambe(riga: GaraDiPiano): Gamba[] {
  const chiude = gambaChiudente(riga.esito);
  const grezze: { chiave: Gamba["chiave"]; etichetta: string; data: string | null }[] = [
    { chiave: "stop", etichetta: "stop", data: riga.stop_hit_date },
    { chiave: "tp1", etichetta: "target", data: riga.tp1_hit_date },
    { chiave: "tp2", etichetta: "secondo target", data: riga.tp2_hit_date },
  ];
  const ordine: Record<Gamba["chiave"], number> = { stop: 0, tp1: 1, tp2: 2 };
  return grezze
    .filter((g): g is { chiave: Gamba["chiave"]; etichetta: string; data: string } => !!g.data)
    .sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : ordine[a.chiave] - ordine[b.chiave]))
    .map((g) => ({
      chiave: g.chiave,
      etichetta: g.etichetta,
      data: g.data,
      chiude: g.chiave === chiude && g.data === riga.resolved_date,
      // ⚠️ Il confronto e' con la data di CHIUSURA, non con la gamba
      // precedente: due gambe possono cadere lo stesso giorno (barra
      // ambigua), e nessuna delle due e' «dopo».
      dopo: g.data > riga.resolved_date,
    }));
}

/* ─── La gara nel tempo: dove cade ogni gamba sull'orizzonte ───────────── */

/** Una gara con le misure che servono a disegnarla nel tempo. `PlanOutcomeRow`
 *  e `PlanBrief` le portano entrambi. */
export interface GaraNelTempo extends GaraDiPiano {
  entry_date: string;
  /** Sedute dall'ingresso alla chiusura: la posizione ESATTA della chiusura. */
  bars_to_outcome: number;
  horizon_days: number;
}

export interface PuntoTraccia {
  chiave: Gamba["chiave"];
  data: string;
  /** Sull'orizzonte: 0 = l'ingresso, 1 = l'ultima seduta dell'orizzonte. */
  x: number;
  chiude: boolean;
  /** Toccata DOPO la chiusura: nel disegno e' un segno vuoto. */
  dopo: boolean;
  /** Quante gambe PRIMA di questa cadono nella stessa seduta — barra ambigua,
   *  o i due target nello stesso giorno. Sposta il segno in verticale, cosi'
   *  due segni nello stesso punto non diventano uno. */
  impilato: number;
}

export interface TracciaGara {
  /** Dove si e' chiusa la posizione, sulla stessa scala dei punti. */
  chiusura: number;
  punti: PuntoTraccia[];
}

const GIORNO_MS = 86_400_000;

function giornoUtc(iso: string): number | null {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

/** Le sedute (lun-ven) in `(da, a]`: la stessa convenzione della gara, che
 *  parte dalla barra STRETTAMENTE successiva all'ingresso.
 *
 *  ⚠️ In UTC, non nel fuso locale: una data ISO nuda e' mezzanotte UTC, e
 *  mescolarla con una mezzanotte locale sposta il conteggio di un giorno a
 *  ovest di Greenwich — il difetto che questo repo ha gia' trovato in un test
 *  «vero di niente» in CI.
 *
 *  ⚠️ Le festivita' NON sono saltate: il catalogo copre borse con calendari
 *  diversi e nessuno e' a portata di questo calcolo. Il disegno e' quindi una
 *  posizione approssimata di qualche seduta; la data esatta resta nel testo
 *  accanto, e la CHIUSURA non usa questa funzione ma `bars_to_outcome`. */
export function sedute(da: string, a: string): number {
  const inizio = giornoUtc(da);
  const fine = giornoUtc(a);
  if (inizio == null || fine == null || fine <= inizio) return 0;
  let n = 0;
  for (let t = inizio + GIORNO_MS; t <= fine; t += GIORNO_MS) {
    const g = new Date(t).getUTCDay();
    if (g !== 0 && g !== 6) n++;
  }
  return n;
}

/** Dove cade ogni gamba toccata sull'orizzonte del segnale.
 *
 *  ⚠️ A sinistra della chiusura, per costruzione, non puo' esserci niente se
 *  non cio' che e' accaduto NELLA STESSA SEDUTA: la posizione si chiude alla
 *  prima gamba toccata. Il disegno lo rende visibile invece di doverlo
 *  spiegare — ed e' anche la ragione per cui qui l'ordine prevale sulla
 *  posizione stimata: una gamba dopo la chiusura non puo' finire a sinistra
 *  della barretta per un errore di calendario. */
export function tracciaGara(riga: GaraNelTempo): TracciaGara {
  const orizzonte = Math.max(1, riga.horizon_days);
  const scala = (v: number) => Math.min(1, Math.max(0, v / orizzonte));
  const chiusura = scala(riga.bars_to_outcome);
  const perGiorno = new Map<string, number>();
  const punti = sequenzaGambe(riga).map((g) => {
    const stimata = scala(sedute(riga.entry_date, g.data));
    const x =
      g.data === riga.resolved_date
        ? chiusura
        : g.dopo
          ? Math.max(chiusura, stimata)
          : Math.min(chiusura, stimata);
    const impilato = perGiorno.get(g.data) ?? 0;
    perGiorno.set(g.data, impilato + 1);
    return { chiave: g.chiave, data: g.data, x, chiude: g.chiude, dopo: g.dopo, impilato };
  });
  return { chiusura, punti };
}

/** Lo stop e' stato colpito PRIMA di un target poi arrivato lo stesso.
 *
 *  E' il numero che nessun altro magazzino sa dare, e la ragione per cui le
 *  date delle gambe sono registrate anche dopo la chiusura: non «entrambe
 *  toccate», ma l'ORDINE, che e' tutta la diagnosi. */
export function stopTroppoStretto(riga: GaraDiPiano): boolean {
  return (
    !!riga.stop_hit_date &&
    !!riga.tp1_hit_date &&
    riga.stop_hit_date < riga.tp1_hit_date
  );
}

export interface EsitoMeta {
  /** ⚠️ CORTA: sta in una pastiglia dentro una colonna da 116px e nei chip
   *  del filtro. La distinzione fra «stop» e «stop e target nella stessa
   *  barra» resta — e' una categoria a se' apposta — ma si dice in due
   *  parole, e il perche' sta nella spiegazione. */
  label: string;
  /** ⚠️ `emerald`/`rose` — la DIREZIONE di un risultato di mercato. `red`/
   *  `green` in questo repo vogliono dire «rotto/a posto». */
  tono: "ok" | "bad" | "neutro";
  spiegazione: string;
}

export const ESITO_META: Record<string, EsitoMeta> = {
  tp1: {
    label: "Target",
    tono: "ok",
    spiegazione: "Il prezzo ha toccato il primo target prima dello stop: la posizione si sarebbe chiusa in guadagno.",
  },
  stop: {
    label: "Stop",
    tono: "bad",
    spiegazione: "Lo stop è arrivato per primo: la posizione si sarebbe chiusa in perdita, di 1R per costruzione.",
  },
  ambigua: {
    label: "Stessa barra",
    tono: "bad",
    spiegazione:
      "Stop e target sono stati toccati nella stessa seduta. Il dato giornaliero non dice quale sia venuto prima, quindi si assegna lo stop — la convenzione pessimista — e la categoria resta separata per poter misurare quanto costa.",
  },
  scaduto: {
    label: "Scaduto",
    tono: "neutro",
    spiegazione:
      "L'orizzonte è trascorso senza che né stop né target fossero toccati: la posizione è valorizzata alla chiusura dell'ultima seduta.",
  },
};

/** «+2,4R». Il segno sempre, perche' la grandezza da sola non dice l'esito. */
export function formatR(v: number): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}R`;
}

/** Il P/L della posizione alla chiusura, in PERCENTUALE del prezzo d'ingresso.
 *
 *  `r_multiple × r / entry`: R e' la distanza dello stop in prezzo, e
 *  `r_multiple` porta gia' il segno del GUADAGNO — positivo per uno short il
 *  cui prezzo e' sceso — quindi la stessa formula vale per entrambi i versi.
 *  Coincide con `(uscita − ingresso) / ingresso` sul target, sullo stop e
 *  sulla chiusura a orizzonte, perche' la gara calcola R proprio cosi'.
 *
 *  ⚠️ Una percentuale SENZA leva e senza costi: il piano dimensiona la
 *  posizione sullo stop, quindi due righe a +8% possono valere guadagni
 *  diversi in conto. E' la ragione per cui R resta accanto.
 *
 *  null quando l'ingresso non e' un prezzo usabile: meglio «—» di un infinito. */
export function plPercentuale(riga: { r_multiple: number; r: number; entry: number }): number | null {
  const { r_multiple: rm, r, entry } = riga;
  if (!(entry > 0) || !Number.isFinite(r) || !Number.isFinite(rm)) return null;
  return ((rm * r) / entry) * 100;
}

/** «+8.4%», «−2.1%», «—». Il segno meno tipografico, come `formatR`. */
export function formatPL(pct: number | null): string {
  if (pct == null || !Number.isFinite(pct)) return "—";
  return `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct).toFixed(1)}%`;
}

/** Una data ISO in «5 mar». `—` su un valore assente o illeggibile. */
export function giornoBreve(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

/** La chiusura del piano in una frase, per un titolo accessibile o una riga
 *  di dettaglio.
 *
 *  ⚠️ Dice sempre DUE cose quando ci sono: quale gamba ha chiuso, e quali
 *  altre il prezzo ha toccato dopo. La seconda meta' e' la sola diagnosi che
 *  questo magazzino sa dare — «stop il 5, target il 18» vale -1R ed e'
 *  giusto, e dice anche che quello stop era troppo stretto. */
export function raccontaPiano(riga: GaraDiPiano): string {
  const r = formatR(riga.r_multiple);
  const quando = giornoBreve(riga.resolved_date);
  const testa =
    riga.esito === "tp1"
      ? `Target colpito il ${quando} (${r})`
      : riga.esito === "stop"
        ? `Stop colpito il ${quando} (${r})`
        : riga.esito === "ambigua"
          ? `Stop e target nella stessa barra, il ${quando} (${r}): il dato giornaliero non dice quale sia venuto prima, si assegna lo stop`
          : `Orizzonte trascorso il ${quando} senza toccare né stop né target (${r})`;
  const dopo = sequenzaGambe(riga).filter((g) => g.dopo);
  if (dopo.length === 0) return `${testa}.`;
  const coda = dopo.map((g) => `${g.etichetta} il ${giornoBreve(g.data)}`).join(", ");
  const diagnosi = stopTroppoStretto(riga)
    ? " — il verso era giusto, la distanza dello stop no"
    : "";
  return `${testa}. Dopo la chiusura il prezzo ha toccato ${coda}${diagnosi}.`;
}
