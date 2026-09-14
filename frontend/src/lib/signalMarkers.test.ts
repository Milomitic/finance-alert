import { describe, expect, it } from "vitest";

import type { Alert, OhlcvBar } from "@/api/types";
import { buildEarningsMarkers, buildSignalOverlay } from "@/lib/signalMarkers";

function bar(date: string, close = 100): OhlcvBar {
  return { date, open: 100, high: 101, low: 99, close, volume: 1000 };
}

let nextId = 1;
function signal(
  signal_date: string | null,
  tone: "bull" | "bear",
  extra: Partial<Alert> = {},
): Alert {
  return {
    id: nextId++,
    signal_date,
    rule_kind: "signal:trend_pullback",
    stock_id: 1,
    ticker: "AAPL",
    name: "Apple",
    triggered_at: `${signal_date ?? "2026-07-10"}T12:00:00Z`,
    trigger_price: 100,
    snapshot: { tone, strength: 77 },
    read_at: null,
    archived_at: null,
    ...extra,
  };
}

const OHLCV: OhlcvBar[] = [
  bar("2026-07-06"),
  bar("2026-07-07"),
  bar("2026-07-08"),
  bar("2026-07-09"),
  bar("2026-07-10"),
];

describe("buildSignalOverlay", () => {
  it("returns empty overlay for empty inputs", () => {
    expect(buildSignalOverlay([], []).markers).toEqual([]);
    expect(buildSignalOverlay(OHLCV, []).markers).toEqual([]);
    expect(buildSignalOverlay([], [signal("2026-07-08", "bull")]).markers).toEqual([]);
  });

  it("anchors a signal to the exact daily bar it fired on", () => {
    const { markers } = buildSignalOverlay(OHLCV, [signal("2026-07-08", "bull")]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-08") / 1000));
    expect(markers[0].shape).toBe("arrowUp");
    expect(markers[0].position).toBe("belowBar");
  });

  it("snaps a signal with no exact bar to the enclosing (previous) candle", () => {
    // Weekly-style gap: bars on the 6th and 13th, signal on the 9th → 6th.
    const weekly = [bar("2026-07-06"), bar("2026-07-13")];
    const { markers } = buildSignalOverlay(weekly, [signal("2026-07-09", "bear")]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-06") / 1000));
    expect(markers[0].shape).toBe("arrowDown");
    expect(markers[0].position).toBe("aboveBar");
  });

  it("drops alerts older than the first visible bar", () => {
    const { markers } = buildSignalOverlay(OHLCV, [signal("2020-01-01", "bull")]);
    expect(markers).toEqual([]);
  });

  it("collapses several same-day signals into ONE marker, detail in byTime", () => {
    const { markers, byTime } = buildSignalOverlay(OHLCV, [
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bear"),
    ]);
    expect(markers).toHaveLength(1);
    // Changed deliberately 2026-09-09. This used to assert "" on the reasoning
    // that the count belongs in the hover panel — but three signals on a bar
    // and one signal on a bar drew the IDENTICAL glyph, so the busiest days on
    // the chart looked like the quietest and the only way to find them was to
    // hover every arrow. The detector name is still kept off the chart; it is
    // the part that buried the candles.
    expect(markers[0].text).toBe("3");
    // ⚠️ Cambiato deliberatamente 2026-09-14 (FA-063). Questa riga asseriva
    // `arrowUp` con la ragione «2 bull vs 1 bear → maggioranza rialzista»:
    // codificava il difetto. Due segnali CORRELATI — due detector della stessa
    // famiglia sullo stesso titolo, il caso ordinario — coprivano il
    // ribassista, che spariva dal grafico. Il glifo misto dice che su quella
    // barra il motore ha detto due cose opposte; i singoli toni stanno nel
    // pannello di dettaglio, che e' dove una lista si legge.
    expect(markers[0].shape).toBe("circle");
    const t = Math.floor(Date.parse("2026-07-09") / 1000);
    expect(byTime.get(t)).toHaveLength(3);
    expect(byTime.get(t)?.[0].forza).toBe(77);
  });

  it("uses the trigger day when signal_date is null (legacy rows)", () => {
    const legacy = signal(null, "bull", { triggered_at: "2026-07-07T09:00:00Z" });
    const { markers } = buildSignalOverlay(OHLCV, [legacy]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-07") / 1000));
  });

  it("emits markers sorted ascending by time", () => {
    const { markers } = buildSignalOverlay(OHLCV, [
      signal("2026-07-10", "bull"),
      signal("2026-07-06", "bear"),
      signal("2026-07-08", "bull"),
    ]);
    const times = markers.map((m) => m.time as number);
    expect(times).toEqual([...times].sort((a, b) => a - b));
  });
});

describe("buildEarningsMarkers", () => {
  it("returns empty for empty inputs", () => {
    expect(buildEarningsMarkers([], [])).toEqual([]);
    expect(buildEarningsMarkers(OHLCV, [])).toEqual([]);
  });

  it("flags an in-window earnings date, tone by surprise", () => {
    const beat = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: 4.2 }]);
    expect(beat).toHaveLength(1);
    expect(beat[0].shape).toBe("square");
    expect(beat[0].text).toBe("E");
    expect(beat[0].color).toBe("#0d9488"); // beat → teal

    const miss = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: -1.5 }]);
    // Rose, not red: a miss is a DIRECTIONAL fact, and CLAUDE.md reserves
    // red/green for "something is broken". Teal stays for the beat rather than
    // moving to emerald, so an earnings flag and a bull signal on the same bar
    // stay distinguishable.
    expect(miss[0].color).toBe("#e11d48");

    const unknown = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: null }]);
    expect(unknown[0].color).toBe("#64748b"); // unknown → slate
  });

  it("skips a future earnings date past the last bar", () => {
    expect(buildEarningsMarkers(OHLCV, [{ date: "2027-01-01", surprise_pct: 0 }])).toEqual([]);
  });

  it("skips an earnings date before the first bar", () => {
    expect(buildEarningsMarkers(OHLCV, [{ date: "2020-01-01", surprise_pct: 0 }])).toEqual([]);
  });

  it("emits at most one flag per bar", () => {
    const m = buildEarningsMarkers(OHLCV, [
      { date: "2026-07-08", surprise_pct: 1 },
      { date: "2026-07-08", surprise_pct: 2 },
    ]);
    expect(m).toHaveLength(1);
  });
});

describe("i marker sono leggibili senza classificare i segnali", () => {
  it("usa la tavolozza direzionale, non quella degli errori", () => {
    // rose/emerald = direzione, red/green = qualcosa e rotto (CLAUDE.md). Un
    // segnale bull/bear e direzione, e prima parlava la tavolozza sbagliata.
    const bull = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]).markers;
    const bear = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bear")]).markers;

    expect(bull[0].color).toBe("#059669");
    expect(bear[0].color).toBe("#e11d48");
  });

  it("non usa piu il verde e il rosso di sistema", () => {
    const bull = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]).markers;
    const bear = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bear")]).markers;

    expect([bull[0].color, bear[0].color]).not.toContain("#17b551");
    expect([bull[0].color, bear[0].color]).not.toContain("#dc2626");
  });

  it("un solo segnale non porta un conteggio", () => {
    // "1" accanto a ogni freccia sarebbe rumore: il conteggio serve solo dove
    // aggiunge qualcosa che la freccia non dice.
    const { markers } = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]);

    expect(markers[0].text).toBe("");
  });

  it("NON dimensiona i marker in base alla Forza", () => {
    // La regressione da impedire, non una svista. Un marker piu grande dice
    // "guarda questo", cioe la stessa affermazione che il playbook faceva
    // dimensionando il rischio sulla Forza — rimossa perche la banda 90-99
    // realizza 42,3% contro 52-53% delle altre. Tutti leggibili, nessuno
    // classificato.
    const weak = { snapshot: { tone: "bull", strength: 12 } };
    const strong = { snapshot: { tone: "bull", strength: 98 } };
    const debole = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull", weak)]).markers;
    const forte = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull", strong)]).markers;

    expect(debole[0].size).toBe(forte[0].size);
  });
});

/* ─── FA-063: dove cade il marker, e di che colore ────────────────────────── */

/** Una seduta intraday: barre da 30 minuti dalle 13:30 UTC (09:30 a New York). */
function intraday(giorno: string, ore: string[]): OhlcvBar[] {
  return ore.map((h) => bar(`${giorno}T${h}:00Z`));
}

describe("buildSignalOverlay — collocamento su serie intraday", () => {
  const SERIE = [
    ...intraday("2026-07-08", ["13:30", "14:00", "14:30", "19:30"]),
    ...intraday("2026-07-09", ["13:30", "14:00", "14:30", "19:30"]),
  ];

  it("⚠️ un segnale datato al giorno X cade su una barra del giorno X", () => {
    /* Il difetto: `signal_date` e' una data GIORNALIERA, e `Date.parse` la
     * rende mezzanotte UTC. Su una serie intraday quella mezzanotte precede
     * ogni barra della seduta, quindi «l'ultima barra <= t» e' l'ultima barra
     * del giorno PRECEDENTE — il marker scivolava di una seduta.
     *
     * Una data giornaliera non contiene l'ora di emissione, e il codice non
     * deve fingere che la contenga: si aggancia all'APERTURA del giorno. */
    const { markers } = buildSignalOverlay(SERIE, [signal("2026-07-09", "bull")]);
    expect(markers).toHaveLength(1);
    const t = markers[0].time as number;
    const giorno = new Date(t * 1000).toISOString().slice(0, 10);
    expect(giorno).toBe("2026-07-09");
    // ⚠️ Il controllo negativo, che e' la meta' che conta: la forma vecchia
    // rendeva ESATTAMENTE l'ultima barra dell'8, e senza questa riga il test
    // passerebbe anche su una serie giornaliera dove i due comportamenti
    // coincidono.
    expect(t).not.toBe(Math.floor(Date.parse("2026-07-08T19:30:00Z") / 1000));
    expect(t).toBe(Math.floor(Date.parse("2026-07-09T13:30:00Z") / 1000));
  });

  it("un giorno SENZA barre ricade sulla barra che lo contiene", () => {
    /* Il ripiego resta, ed e' giusto: su una serie settimanale un segnale di
     * mercoledi' appartiene alla barra di lunedi'. Toglierlo per aggiustare
     * l'intraday romperebbe settimanale e mensile. */
    const settimanali = [bar("2026-07-06"), bar("2026-07-13")];
    const { markers } = buildSignalOverlay(settimanali, [signal("2026-07-08", "bull")]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-06") / 1000));
  });
});

describe("buildSignalOverlay — il verso non si decide a maggioranza", () => {
  it("⚠️ due rialzisti e un ribassista danno un marker MISTO, non una freccia su", () => {
    /* Il difetto: il colore veniva dalla maggioranza, quindi due segnali
     * CORRELATI — due detector della stessa famiglia sullo stesso titolo —
     * coprivano un ribassista, che spariva dal grafico.
     *
     * E' una logica diversa da quella che `confluence_service` applica
     * altrove, dove N segnali della stessa famiglia contano ~1,3 e non N.
     * Qui il contrasto e' un FATTO: su quella barra il motore ha detto due
     * cose opposte, e il grafico deve dirlo. */
    const { markers } = buildSignalOverlay(OHLCV, [
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bear"),
    ]);
    expect(markers).toHaveLength(1);
    expect(markers[0].shape).toBe("circle");
    expect(markers[0].shape).not.toBe("arrowUp");
    expect(markers[0].position).toBe("inBar");
  });

  it("un verso solo resta una freccia — il misto non e' il default", () => {
    /* ⚠️ Il pavimento: senza, un componente che rendesse SEMPRE un cerchio
     * soddisferebbe il test sopra. */
    const su = buildSignalOverlay(OHLCV, [
      signal("2026-07-09", "bull"), signal("2026-07-09", "bull"),
    ]);
    expect(su.markers[0].shape).toBe("arrowUp");
    const giu = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bear")]);
    expect(giu.markers[0].shape).toBe("arrowDown");
  });
});
