import type { DetectorPerformance } from "@/api/platformHealth";
import type { MetricTileProps } from "@/components/ui/metric-tile";

/* Le metriche in evidenza sopra la tabella dei segnali, derivate dal payload
 * del magazzino degli esiti. Separate dal componente perche' un file di
 * componenti che esporta anche funzioni rompe il Fast Refresh. */

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toFixed(1).replace(".", ",")}%`;

const VERDETTO: Record<string, string> = {
  above: "sopra il mercato",
  below: "sotto il mercato",
  inconclusive: "non concludente",
};

function giorno(iso: string | null): string {
  if (!iso) return "—";
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

export function signalStatTiles(d: DetectorPerformance): MetricTileProps[] {
  const o = d.overall;
  const verdetti = d.detectors.map((r) => r.total.skill_verdict);
  const sopra = verdetti.filter((v) => v === "above").length;
  const sotto = verdetti.filter((v) => v === "below").length;
  const incerti = verdetti.filter((v) => v === "inconclusive").length;

  return [
    {
      label: "Skill vs mercato",
      primary: true,
      value: pct(o?.mkt_neutral_hit_rate),
      hint:
        o?.skill_ci_low == null || o.skill_ci_high == null
          ? "nessun esito con benchmark"
          : `IC 95% ${pct(o.skill_ci_low)}–${pct(o.skill_ci_high)} · ${VERDETTO[o.skill_verdict ?? ""] ?? "—"}`,
      // Il colore segue il VERDETTO, non il numero: 54% su un intervallo che
      // contiene il 50% non e' un risultato.
      tone: o?.skill_verdict === "above" ? "ok" : o?.skill_verdict === "below" ? "bad" : null,
      note:
        "Quota di segnali che hanno battuto la mediana dell'universo nella propria direzione, su tutti gli esiti maturati. 50% = moneta. L'intervallo e' dimensionato sulle finestre indipendenti, non sulle righe.",
    },
    {
      label: "Detector sopra il mercato",
      primary: true,
      value: `${sopra} su ${d.detectors.length}`,
      hint: `${sotto} sotto · ${incerti} non concludenti`,
      tone: sopra > 0 && sotto === 0 ? "ok" : sotto > 0 && sopra === 0 ? "bad" : null,
      note:
        "Un detector e' «sopra il mercato» solo se l'intervallo al 95% della sua skill sta tutto sopra il 50%.",
    },
    {
      label: "Esiti maturati",
      primary: true,
      value: d.meta.total_rows.toLocaleString("it-IT"),
      hint:
        o?.effective_n == null
          ? undefined
          : `${o.effective_n} finestre indipendenti · dal ${giorno(d.meta.date_min)} al ${giorno(d.meta.date_max)}`,
      note:
        "Tutti gli esiti nel database, archiviati compresi. Le finestre indipendenti decidono quanto le percentuali siano affidabili: segnali vicini condividono la stessa finestra futura.",
    },
    {
      label: "Hit assoluto",
      value: pct(o?.abs_hit_rate),
      hint: "include il beta del mercato",
    },
    {
      label: "Detector con esiti",
      value: `${d.meta.n_detectors}/${d.meta.n_detectors_universe}`,
    },
  ];
}
