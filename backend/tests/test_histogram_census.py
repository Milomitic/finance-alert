"""Nessun istogramma puo' comparire con un tetto che nessuno ha scelto.

⚠️ Generalizza `test_latency_buckets.py`, che pinna UN istogramma. Il difetto
che quel file registra — nove handler con p95 esattamente 1.000, cioe' il bordo
finito piu' alto restituito come se fosse una misura — non era una proprieta' di
quella serie: e' una proprieta' di QUALUNQUE istogramma i cui bucket finiscano
prima di dove vive il fenomeno. `histogram_quantile` non ha modo di dire «non
lo so», quindi restituisce il tetto, e un tetto somiglia a un numero.

Questo file impedisce che la prossima serie nasca con lo stesso difetto: ogni
famiglia esposta da `/metrics` deve essere DICHIARATA qui insieme al p99
realistico che deve poter rappresentare. Una famiglia nuova rende il test rosso
con l'istruzione di classificarla — che costa trenta secondi al momento in cui
la si scrive, e costa una diagnosi sbagliata sei mesi dopo.

⚠️ Il censimento ha un PAVIMENTO. Se `/metrics` smettesse di esporre
istogrammi — un middleware disattivato, un client rotto — l'asserzione «ogni
famiglia e' dichiarata» sarebbe vera di un insieme vuoto, che e' la forma «un
test puo' essere vero di niente» registrata quattro volte in CLAUDE.md.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

#: Famiglia -> tetto finito MINIMO che deve avere, e perche'.
#:
#: Il numero non e' un gusto: e' la domanda «qual e' il p99 plausibile di questa
#: cosa?». Se il tetto sta sotto, il quantile alto e' un ceiling travestito.
ATTESE: dict[str, tuple[float, str]] = {
    "http_request_duration_seconds": (
        30.0,
        "Le rotte quote dipendono da yfinance, misurato a 43-50s sotto rate "
        "limiting (CLAUDE.md). Un tetto a 1s ha gia' prodotto nove p95 falsi.",
    ),
    "finance_alert_web_vital_value": (
        4000.0,
        "LCP e INP sono millisecondi, CLS un punteggio 0..1: la stessa serie "
        "deve reggere due scale. Un tetto basso qui non si vede, perche' i "
        "Web Vital brutti sono proprio quelli in coda.",
    ),
    "http_request_duration_highr_seconds": (
        30.0,
        "Stessa scala della sorella, ma senza etichetta handler: dice che "
        "l'app e' lenta e non quale rotta. Il tetto deve comunque reggere "
        "l'upstream piu' lento, o anche l'aggregato mente.",
    ),
}

#: Sotto questo numero il censimento non sta misurando l'app.
MINIMO_FAMIGLIE = 2
#: ⚠️ Le famiglie compaiono solo DOPO che qualcosa le ha osservate, quindi il
#: censimento dipende da quali test hanno gia' girato nel processo. Da sola
#: questa suite ne vede due; con l'intera suite ne vede tre, perche' i test
#: della RUM registrano `finance_alert_web_vital_value`. Ecco perche' ATTESE
#: elenca anche famiglie che un'esecuzione isolata non incontra: una
#: dichiarazione in piu' non fa danno, una in meno rende il test ordine-
#: dipendente — e un test che cambia esito con l'ordine non e' un cancello.


@pytest.fixture(scope="module")
def testo_metriche() -> str:
    client = TestClient(app)
    client.get("/api/health")  # una richiesta, o gli istogrammi non esistono
    return client.get("/metrics").text


def _famiglie(testo: str) -> dict[str, list[float]]:
    """Nome famiglia -> bordi finiti, ordinati."""
    out: dict[str, set[float]] = {}
    for riga in testo.splitlines():
        if "_bucket" not in riga or 'le="' not in riga:
            continue
        nome = riga.split("_bucket", 1)[0]
        grezzo = riga.split('le="', 1)[1].split('"', 1)[0]
        if grezzo in ("+Inf", "Inf"):
            continue
        out.setdefault(nome, set()).add(float(grezzo))
    return {n: sorted(b) for n, b in out.items()}


def test_il_censimento_vede_qualcosa(testo_metriche):
    """Il pavimento: senza, ogni asserzione sotto e' vera di un insieme vuoto."""
    assert len(_famiglie(testo_metriche)) >= MINIMO_FAMIGLIE


def test_ogni_istogramma_e_dichiarato(testo_metriche):
    """Una famiglia nuova non puo' entrare senza che qualcuno scelga il tetto.

    ⚠️ Il rosso qui non significa «hai rotto qualcosa»: significa «hai aggiunto
    un istogramma e non hai ancora detto fin dove deve saper misurare». La
    risposta e' una riga in ATTESE.
    """
    trovate = set(_famiglie(testo_metriche))
    non_dichiarate = sorted(trovate - set(ATTESE))
    assert not non_dichiarate, (
        f"istogrammi non dichiarati: {non_dichiarate}. Aggiungili a ATTESE con "
        "il p99 plausibile del fenomeno che misurano — un tetto piu' basso "
        "rende ogni quantile alto un ceiling travestito da misura."
    )


@pytest.mark.parametrize("famiglia", sorted(ATTESE))
def test_il_tetto_regge_il_fenomeno(famiglia, testo_metriche):
    famiglie = _famiglie(testo_metriche)
    if famiglia not in famiglie:
        pytest.skip(
            f"{famiglia} non e' stata ancora osservata in questo processo. "
            "Legittimo: un istogramma compare in /metrics solo dopo la prima "
            "osservazione, e questa suite non esercita ogni percorso."
        )
    minimo, perche = ATTESE[famiglia]
    tetto = famiglie[famiglia][-1]
    assert tetto >= minimo, f"{famiglia}: tetto {tetto}s, serve >= {minimo}s. {perche}"


def test_i_bucket_non_sono_due(testo_metriche):
    """Un istogramma con pochissimi bordi non distingue niente.

    Controllo indipendente dal tetto: si puo' avere un tetto altissimo e tre
    bucket, e la distribuzione resta illeggibile. Cinque e' il minimo sotto il
    quale un p50 e un p95 finiscono quasi sempre nello stesso intervallo.
    """
    for nome, bordi in _famiglie(testo_metriche).items():
        assert len(bordi) >= 5, f"{nome}: solo {len(bordi)} bucket finiti"
