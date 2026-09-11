import { describe, expect, it } from "vitest";

/* ─── L'AbortSignal e una CONVENZIONE, non una passata una-tantum ─────────
 *
 * S-2 / FA-039. `api/client.ts` inoltra davvero `signal` a fetch, quindi il
 * supporto c'e da sempre: su 60 `queryFn` una sola lo passava.
 *
 * ⚠️ **Misurato prima, e ridimensiona il beneficio.** Il server negozia h2
 * (`ALPN protocol: h2`), quindi le richieste sono multiplexate e una
 * abbandonata non occupa uno dei sei slot per host — l'argomento classico non
 * si applica. Nessun handler REST osserva la disconnessione: `is_disconnected`
 * compare solo nei tre stream SSE, quindi un abort non ferma il backend. E
 * react-query scarta gia i risultati delle query smontate, quindi non c'e un
 * difetto di correttezza. Resta CPU e banda del client su risposte che nessuno
 * leggera, piu le connessioni del dev server Vite che e HTTP/1.1. E igiene, ed
 * e per questo che l'audit le ha dato P3: nessuno ha mai rivendicato altro.
 *
 * ⚠️ **Questo test esiste perche una passata non basta.** Senza, il prossimo
 * hook scritto senza `signal` riporta il conteggio verso uno e nessuno lo vede:
 * e la forma «una correzione parziale avvalora la convinzione che il caso sia
 * chiuso» che CLAUDE.md registra due volte. Qui il caso si riapre da solo.
 */

const SORGENTI = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Le `queryFn` che NON devono inoltrare il segnale, con il motivo.
 *  Una lista vuota sarebbe sospetta; una lista che cresce senza motivi lo e
 *  di piu. */
const ESENTI: Record<string, string> = {};

interface Sito {
  file: string;
  riga: number;
  testo: string;
}

function siti(): Sito[] {
  const out: Sito[] = [];
  for (const [file, testo] of Object.entries(SORGENTI)) {
    if (file.includes(".test.")) continue;
    testo.split("\n").forEach((riga, i) => {
      if (riga.includes("queryFn:")) out.push({ file, riga: i + 1, testo: riga });
    });
  }
  return out;
}

describe("ogni queryFn inoltra l'AbortSignal", () => {
  it("il censimento non e vuoto", () => {
    // ⚠️ Senza questo, l'asserzione sotto sarebbe vera di NIENTE: se il glob
    // smettesse di trovare file, «tutte inoltrano» passerebbe su zero query.
    expect(siti().length).toBeGreaterThanOrEqual(50);
  });

  it("nessuna queryFn lo omette senza essere nella lista delle esenti", () => {
    const mancanti = siti()
      .filter((s) => !s.testo.includes("signal"))
      .filter((s) => !(`${s.file}:${s.riga}` in ESENTI))
      .map((s) => `${s.file}:${s.riga}`);
    expect(mancanti).toEqual([]);
  });
});
