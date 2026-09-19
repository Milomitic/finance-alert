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
