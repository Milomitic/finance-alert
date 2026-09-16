"""Latenza di una rotta contata per VITA del processo, sui campioni grezzi di Prometheus.

Perche' esiste (FA-006, 2026-09-16). La prima misura di `/api/stocks/quotes`
dopo la correzione rispondeva «~0 richieste in 8,6 ore» con
`increase(http_request_duration_seconds_bucket[...])`, e la base di confronto
«121 richieste in 24 ore». Erano entrambe sbagliate, per la stessa ragione:

- l'instrumentator crea la serie di una rotta alla PRIMA richiesta che il
  processo riceve, quindi il primo campione raccolto vale gia' N;
- `increase()` misura differenze fra campioni e non ha uno zero da cui
  partire, quindi quelle N richieste non esistono per lui;
- in questo cluster ogni rilascio riavvia il pod (dieci il 16 settembre), e una
  pagina fa le sue richieste tutte insieme all'apertura: la prima raffica di
  ogni vita e' spesso TUTTO il traffico di quella vita.

Misurato: dopo la correzione `increase()` vedeva 0 richieste dove c'erano 7; la
base ne vedeva 121 dove ce n'erano 161, e le 40 perse erano quasi tutte LENTE
(cache fredde subito dopo un avvio), cioe' la base sembrava migliore del vero.

IL METODO. Ogni vita del processo (`process_start_time_seconds`) conta da zero:
il valore finale del contatore e' il numero di richieste di quella vita. Una
vita cominciata PRIMA della finestra si conta dal suo valore al bordo, ma solo
se la serie esisteva gia' al bordo; se e' nata dentro la finestra, da zero.

E riporta le RAFFICHE, non solo le richieste: sette richieste arrivate nello
stesso minuto sono UNA pagina aperta, cioe' un'osservazione. E' la stessa
regola di `independent_blocks` per gli esiti dei segnali.

USO — dal pod, perche' Prometheus e Loki sono raggiungibili solo nel cluster:

    ssh -i ~/.ssh/oci_finance_alert opc@80.225.80.141 \\
      "kubectl exec -i -n finance-alert finance-alert-finance-alert-0 -- python - \\
       --rotta /api/stocks/quotes --da 2026-09-16T10:28 --log 'batch deadline'" \\
      < backend/scripts/latenza_per_vita.py

`--da`/`--a` sono in UTC. Il file non entra nell'immagine: si passa da stdin.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime, timedelta

PROM = "http://kps-prometheus.monitoring.svc:9090"
LOKI = "http://loki.monitoring.svc:3100"
POD = 'namespace="finance-alert",pod="finance-alert-finance-alert-0"'
SOGLIE = ("0.5", "1.0", "2.5", "5.0", "10.0")
RAFFICA_S = 120  # incrementi entro due minuti = la stessa apertura di pagina


def _utc(testo: str) -> datetime:
    return datetime.fromisoformat(testo).replace(tzinfo=UTC)


def _grezzi(selettore: str, inizio: datetime, fine: datetime) -> list[dict]:
    sec = int((fine - inizio).total_seconds())
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode(
        {"query": f"{selettore}[{sec}s]", "time": fine.timestamp()})
    d = json.load(urllib.request.urlopen(url, timeout=60))
    if d["status"] != "success":
        raise RuntimeError(d)
    return d["data"]["result"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotta", required=True)
    ap.add_argument("--da", required=True, help="inizio finestra, UTC (es. 2026-09-16T10:28)")
    ap.add_argument("--a", help="fine finestra, UTC; predefinita: adesso")
    ap.add_argument("--log", help="sottostringa da contare in Loki nella stessa finestra")
    args = ap.parse_args()

    da = _utc(args.da)
    a = _utc(args.a) if args.a else datetime.now(UTC)
    # Un margine prima del bordo: serve a sapere se una serie ESISTEVA gia' li'.
    prima = da - timedelta(minutes=10)

    avvii = sorted({
        float(v)
        for s in _grezzi(f"process_start_time_seconds{{{POD}}}", da - timedelta(days=2), a)
        for _, v in s["values"]
    })

    def vita_di(ts: float) -> float | None:
        prec = [x for x in avvii if x <= ts]
        return prec[-1] if prec else None

    # Per (serie, vita): valore al bordo (se la serie c'era) e ultimo valore.
    # ⚠️ Si SOMMA sulle serie: una rotta ha una serie per stato (2xx, 5xx...).
    richieste = defaultdict(float)
    secchi = defaultdict(lambda: defaultdict(float))
    somma = defaultdict(float)
    salti: dict[float, list[float]] = defaultdict(list)
    def sel(nome: str) -> str:
        # Non `.format()`: le graffe dell'etichetta PromQL sarebbero lette come un campo.
        return f'http_request_duration_seconds_{nome}{{handler="{args.rotta}"}}'

    def conta(nome: str, chiave_serie) -> None:
        for s in _grezzi(sel(nome), prima, a):
            punti = [(float(t), float(v)) for t, v in s["values"]]
            per_vita: dict[float, list[tuple[float, float]]] = defaultdict(list)
            for t, v in punti:
                vita = vita_di(t)
                if vita is not None:
                    per_vita[vita].append((t, v))
            for vita, pv in per_vita.items():
                bordo = [v for t, v in pv if t <= da.timestamp()]
                # Nata dopo il bordo -> da zero. Esisteva al bordo -> dal suo valore.
                base = bordo[-1] if (vita < da.timestamp() and bordo) else 0.0
                fine_v = pv[-1][1]
                if fine_v - base <= 0:
                    continue
                chiave_serie(s, vita, fine_v - base)
                if nome == "count":
                    prec = base
                    for t, v in pv:
                        if t > da.timestamp() and v > prec:
                            salti[vita].append(t)
                        prec = v

    conta("count", lambda s, vita, n: richieste.__setitem__(vita, richieste[vita] + n))
    conta("sum", lambda s, vita, x: somma.__setitem__(vita, somma[vita] + x))
    conta("bucket", lambda s, vita, n: secchi[vita].__setitem__(
        s["metric"]["le"], secchi[vita][s["metric"]["le"]] + n))

    def raffiche(ts: list[float]) -> int:
        n, ultimo = 0, None
        for t in sorted(ts):
            if ultimo is None or t - ultimo > RAFFICA_S:
                n += 1
            ultimo = t
        return n

    print(f"{args.rotta}  {da:%d/%m %H:%M} -> {a:%d/%m %H:%M} UTC")
    print("vita (avvio UTC)   richieste raffiche  media s  " + "  ".join(f"<={x:>4}" for x in SOGLIE))
    tot_n = tot_s = 0.0
    tot_b = defaultdict(float)
    tot_r = 0
    for vita in sorted(richieste):
        n = richieste[vita]
        r = raffiche(salti[vita])
        tot_n, tot_s, tot_r = tot_n + n, tot_s + somma[vita], tot_r + r
        for le, v in secchi[vita].items():
            tot_b[le] += v
        nota = "  (cominciata prima della finestra)" if vita < da.timestamp() else ""
        print(f"{datetime.fromtimestamp(vita, UTC):%d/%m %H:%M}        {n:6.0f}  {r:6d}   {somma[vita] / n:6.2f}  "
              + "  ".join(f"{secchi[vita][le] / n * 100:5.0f}%" for le in SOGLIE) + nota)
    if not tot_n:
        print("nessuna richiesta nella finestra")
    else:
        print(f"TOTALE            {tot_n:6.0f}  {tot_r:6d}   {tot_s / tot_n:6.2f}  "
              + "  ".join(f"{tot_b[le] / tot_n * 100:5.0f}%" for le in SOGLIE))
        print(f"mediana entro 1 s: {'SI' if tot_b['1.0'] / tot_n >= 0.5 else 'NO'} "
              f"({tot_b['1.0']:.0f} su {tot_n:.0f}); osservazioni indipendenti = raffiche = {tot_r}")

    if args.log:
        url = f"{LOKI}/loki/api/v1/query_range?" + urllib.parse.urlencode({
            "query": '{namespace="finance-alert"} |= ' + json.dumps(args.log),
            "start": str(int(da.timestamp() * 1e9)), "end": str(int(a.timestamp() * 1e9)),
            "limit": "5000", "direction": "forward"})
        d = json.load(urllib.request.urlopen(url, timeout=60))
        righe = sorted((int(t), v) for s in d["data"]["result"] for t, v in s["values"])
        tetto = " (TETTO raggiunto: sono almeno tante)" if len(righe) >= 5000 else ""
        print(f"\nLoki «{args.log}»: {len(righe)} righe{tetto}")
        for _, v in righe[-5:]:
            print("   ", v[:160])


if __name__ == "__main__":
    main()
