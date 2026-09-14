"""I confini del cubo delle prestazioni, che nessun test percorreva.

⚠️ `detector_performance_service` uccideva 19 dei suoi 50 mutanti. E' il modulo
che decide COSA l'app afferma di sapere sull'efficacia dei detector: il verdetto
«sopra il caso», l'intervallo di Wilson dimensionato sulle finestre indipendenti
e la pastiglia «campione scarso». Un suo difetto non solleva eccezioni — fa
affermare al prodotto piu' di quanto la misura regga, che e' la cosa che questo
progetto passa il tempo a non fare.

I due che contano:

1. Riga 184, `"above" if ci_low > 50.0 else "below" if ci_high < 50.0 else
   "inconclusive"`, coi bordi ESCLUSI. Un intervallo il cui estremo tocca
   esattamente il 50 NON ha superato il lancio di moneta: coi mutanti `>=` e
   `<=` il cubo emetterebbe un verdetto proprio nel caso in cui i dati non lo
   reggono.
2. Righe 378-382, i filtri della curva di equity: `detector == detector` ->
   `!=` seleziona TUTTO TRANNE quello che l'utente ha chiesto. Il pannello si
   riempie, i numeri sono plausibili, e riguardano gli altri.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.models import Alert, SignalOutcome, Stock
from app.services import detector_performance_service as perf
from app.services.detector_performance_service import _replay_block, _replay_cell


def _riga(giorno: date, *, colpo_mkt: int | None, orizzonte: int = 1):
    """Una riga d'esito ridotta a cio' che `_cell` legge davvero."""
    return SimpleNamespace(
        signal_date=giorno, horizon_days=orizzonte,
        abs_hit=1, mkt_neutral_hit=colpo_mkt, fwd_return=0.01,
    )


def _righe_distanziate(n: int, colpi: int):
    """n righe, ognuna nella PROPRIA finestra indipendente.

    ⚠️ Con orizzonte 1 la finestra vale `max(1, ceil(1 * _TRADING_TO_CALENDAR))`
    giorni: distanziandole di dieci si garantisce che `independent_blocks` ne
    conti esattamente n. Senza questo l'intervallo verrebbe dimensionato su un
    numero diverso da quello cercato e il bordo non cadrebbe dove serve.
    """
    d0 = date(2026, 1, 1)
    return [_riga(d0 + timedelta(days=10 * i), colpo_mkt=1 if i < colpi else 0)
            for i in range(n)]


# ─── 1. Il verdetto: il bordo del lancio di moneta e' ESCLUSO ─────────────


def test_un_estremo_inferiore_ESATTAMENTE_a_50_non_e_un_verdetto() -> None:
    """`ci_low > 50.0`, bordo escluso.

    ⚠️ I numeri non sono scelti a caso: 15 colpi su 21 finestre indipendenti
    danno un estremo inferiore di Wilson pari a **esattamente 50,0** dopo
    l'arrotondamento a un decimale che `sized_interval` applica. E' l'unico
    modo di provare il bordo invece di sfiorarlo — cercato per enumerazione su
    (n, colpi), non indovinato.

    Col mutante `>=` questa cella direbbe «sopra il caso» con un intervallo che
    parte dal caso."""
    lo, _hi = perf.sized_interval(rate_pct=15 / 21 * 100.0, effective_n=21)
    assert lo == 50.0, "il caso di prova non e' piu' sul bordo: rifare la ricerca"

    cella = perf._cell("k", _righe_distanziate(21, 15), min_n=1)
    assert cella["effective_n"] == 21
    assert cella["skill_ci_low"] == 50.0
    assert cella["skill_verdict"] == "inconclusive"


def test_un_estremo_superiore_ESATTAMENTE_a_50_non_e_un_verdetto() -> None:
    """L'altra meta', `ci_high < 50.0`: 6 colpi su 21 finestre danno un estremo
    superiore di esattamente 50,0. Col mutante `<=` la cella direbbe «sotto il
    caso» con un intervallo che ci arriva."""
    _lo, hi = perf.sized_interval(rate_pct=6 / 21 * 100.0, effective_n=21)
    assert hi == 50.0, "il caso di prova non e' piu' sul bordo: rifare la ricerca"

    cella = perf._cell("k", _righe_distanziate(21, 6), min_n=1)
    assert cella["skill_ci_high"] == 50.0
    assert cella["skill_verdict"] == "inconclusive"


def test_un_intervallo_che_STACCA_il_caso_da_un_verdetto() -> None:
    """⚠️ Il controllo positivo, senza il quale i due test sopra sarebbero veri
    anche di un cubo che non emette MAI un verdetto — e «non concludente» e'
    esattamente cio' che tutte le celle vive dicono oggi, quindi un difetto del
    genere non si noterebbe."""
    cella = perf._cell("k", _righe_distanziate(30, 30), min_n=1)
    assert cella["skill_ci_low"] > 50.0
    assert cella["skill_verdict"] == "above"


# ─── 2. La pastiglia «campione scarso» ────────────────────────────────────


def test_il_campione_e_scarso_SOTTO_la_soglia_non_SU() -> None:
    """`"low_confidence": eff_n < min_n`, bordo escluso: con esattamente
    `min_n` finestre indipendenti il campione NON e' scarso.

    ⚠️ Il commento accanto a quella riga racconta che la pastiglia fu spostata
    dal conteggio di righe a quello di finestre, e che ora e' accesa su ogni
    cella viva. Proprio per questo il bordo va fissato: un flag sempre acceso
    non si distingue da un flag rotto."""
    assert perf._cell("k", _righe_distanziate(5, 3), min_n=5)["low_confidence"] is False
    assert perf._cell("k", _righe_distanziate(4, 2), min_n=5)["low_confidence"] is True


# ─── 3. I filtri della curva di equity ────────────────────────────────────


def _esito(db, stock_id, *, detector, tono, giorno, rendimento, regime="bull",
           forza=70, orizzonte=21):
    """⚠️ `signal_outcomes.alert_id` NON e' nullable: ogni esito vuole il suo
    avviso. Il magazzino e' append-only e ancorato all'avviso che lo ha
    generato — una riga senza non e' un esito, e' un numero orfano."""
    a = Alert(stock_id=stock_id, trigger_price=100.0, signal_name=detector,
              signal_date=giorno,
              snapshot=json.dumps({"tone": tono, "strength": forza}))
    db.add(a)
    db.flush()
    db.add(SignalOutcome(
        alert_id=a.id, stock_id=stock_id, detector=detector, signal_date=giorno,
        tone=tono, horizon_days=orizzonte, entry_close=100.0,
        forward_close=100.0 * (1 + rendimento), fwd_return=rendimento,
        abs_hit=1 if rendimento > 0 else 0, mkt_neutral_hit=1,
        mkt_neutral_excess=rendimento, regime_at_signal=regime, strength=forza,
        probability=50,
    ))


@pytest.fixture
def titolo(db):
    s = Stock(ticker="EQT", exchange="NASDAQ", name="Equity Co", country="US")
    db.add(s)
    db.flush()
    return s


def test_il_filtro_per_detector_seleziona_QUEL_detector(db, titolo) -> None:
    """`SignalOutcome.detector == detector` -> `!=`.

    ⚠️ Col mutante il pannello mostra la curva di TUTTI GLI ALTRI detector
    sotto il nome di quello scelto. Non si svuota e non sbaglia forma: si
    riempie di numeri plausibili che riguardano qualcun altro — il difetto
    peggiore da vedere a occhio."""
    d0 = date(2026, 1, 1)
    _esito(db, titolo.id, detector="scelto", tono="bull", giorno=d0, rendimento=0.10)
    _esito(db, titolo.id, detector="altro", tono="bull",
           giorno=d0 + timedelta(days=1), rendimento=-0.50)
    db.commit()

    c = perf.compute_equity_curve(db, horizon_days=21, detector="scelto")
    assert c["n_signals"] == 1
    assert c["total_return_pct"] == pytest.approx(10.0, abs=0.01)


def test_il_filtro_per_TONO_seleziona_quel_tono(db, titolo) -> None:
    """Stessa forma sul tono. I due esiti hanno rendimenti opposti, quindi se
    il filtro seleziona il complemento il segno del risultato si inverte."""
    d0 = date(2026, 1, 1)
    _esito(db, titolo.id, detector="d", tono="bull", giorno=d0, rendimento=0.10)
    _esito(db, titolo.id, detector="d", tono="bear",
           giorno=d0 + timedelta(days=1), rendimento=0.10)
    db.commit()

    c = perf.compute_equity_curve(db, horizon_days=21, tone="bull")
    assert c["n_signals"] == 1
    # Rialzista su un +10% e' un guadagno; ribassista sarebbe una perdita.
    assert c["total_return_pct"] > 0


def test_il_filtro_per_REGIME_seleziona_quel_regime(db, titolo) -> None:
    """E sul regime causale."""
    d0 = date(2026, 1, 1)
    _esito(db, titolo.id, detector="d", tono="bull", giorno=d0,
           rendimento=0.10, regime="bull")
    _esito(db, titolo.id, detector="d", tono="bull", giorno=d0 + timedelta(days=1),
           rendimento=-0.50, regime="bear")
    db.commit()

    c = perf.compute_equity_curve(db, horizon_days=21, regime="bull")
    assert c["n_signals"] == 1
    assert c["total_return_pct"] > 0


def test_una_forza_ESATTAMENTE_al_minimo_e_inclusa(db, titolo) -> None:
    """`SignalOutcome.strength >= strength_min`, bordo INCLUSO. Col mutante `>`
    il filtro «Forza almeno 70» escluderebbe proprio i segnali a 70."""
    _esito(db, titolo.id, detector="d", tono="bull", giorno=date(2026, 1, 1),
           rendimento=0.10, forza=70)
    db.commit()

    assert perf.compute_equity_curve(
        db, horizon_days=21, strength_min=70)["n_signals"] == 1


def test_una_curva_SEMPRE_in_perdita_ha_comunque_un_drawdown(db, titolo) -> None:
    """`if peak > 0` -> `if peak > 1`.

    ⚠️ Il picco parte da 1.0 ed e' un massimo, quindi non scende mai sotto:
    `> 0` e' sempre vero e il mutante `>=` e' equivalente. Ma `> 1` NON lo e' —
    una curva che perde dalla prima operazione tiene il picco esattamente a 1.0
    e il drawdown non verrebbe mai calcolato. Il pannello mostrerebbe
    «drawdown massimo 0%» accanto a un rendimento negativo: due numeri che si
    contraddicono in una schermata sola."""
    d0 = date(2026, 1, 1)
    for i in range(3):
        _esito(db, titolo.id, detector="d", tono="bull",
               giorno=d0 + timedelta(days=i), rendimento=-0.10)
    db.commit()

    s = perf.compute_equity_curve(db, horizon_days=21)
    assert s["total_return_pct"] < 0
    assert s["max_drawdown_pct"] > 0, "una curva in perdita senza drawdown"


# ─── 4. Il sommario di replay: una struttura malformata va RIFIUTATA ──────


def test_un_sommario_di_replay_malformato_viene_rifiutato(tmp_path, monkeypatch) -> None:
    """`if not isinstance(data, dict) or not isinstance(data.get("detectors"),
    dict)` -> `and`.

    Col mutante basta che UNA delle due condizioni sia falsa perche' la
    validazione passi: un file in cui `detectors` e' una lista invece di un
    dizionario entrerebbe nel cubo e romperebbe a valle, lontano dal punto in
    cui il dato era gia' riconoscibile come sbagliato."""
    rotto = tmp_path / "replay.json"
    rotto.write_text(json.dumps({"detectors": ["non", "un", "dizionario"]}),
                     encoding="utf-8")
    # ⚠️ `raising` resta al suo default (True) DI PROPOSITO. La prima
    # versione usava `raising=False` e il nome sbagliato (`_REPLAY_SUMMARY`
    # invece di `_REPLAY_ARTIFACT`): monkeypatch ha creato un attributo nuovo
    # invece di sostituire quello vero, il test ha letto il file di produzione
    # e ha fallito per una ragione che non c'entrava. `raising=False` spegne
    # l'unico controllo che verifica di aver scritto il nome giusto.
    monkeypatch.setattr(perf, "_REPLAY_ARTIFACT", rotto)
    assert perf._load_replay_summary() is None


def test_una_finestra_dura_ALMENO_un_giorno() -> None:
    """`span = max(1, ceil(horizon * _TRADING_TO_CALENDAR))`.

    Col mutante `max(2, ...)` la finestra minima raddoppia e due segnali di
    giorni consecutivi collassano in un blocco solo: il conteggio delle
    finestre indipendenti scende, l'intervallo di Wilson si allarga, e l'app
    dichiara MENO evidenza di quanta ne abbia. ⚠️ Sbaglia nella direzione
    prudente, che e' il motivo per cui nessuno se ne accorgerebbe."""
    d0 = date(2026, 1, 1)
    due = [d0, d0 + timedelta(days=1)]
    assert perf.independent_blocks(due, horizon_trading_days=0) == 2


# ─── 5. Il segmento di replay ─────────────────────────────────────────────


def test_una_cella_di_replay_SENZA_conteggio_e_a_bassa_fiducia() -> None:
    """`int(cell.get("n", 0)) < min_n`: il valore di ripiego e' ZERO.

    ⚠️ Col mutante `1` una cella a cui manca il conteggio verrebbe trattata
    come se ne avesse uno — e se `min_n` fosse 1, come se il campione bastasse.
    Un dato assente non e' un dato piccolo."""
    assert _replay_cell({"key": "totale"}, 1)["low_confidence"] is True


def test_una_cella_di_replay_ESATTAMENTE_al_minimo_e_affidabile() -> None:
    """Il bordo escluso, come ovunque nel cubo: con `n == min_n` il campione
    NON e' scarso."""
    assert _replay_cell({"n": 30}, 30)["low_confidence"] is False
    assert _replay_cell({"n": 29}, 30)["low_confidence"] is True


def test_il_segmento_di_replay_ordina_per_conteggio_poi_per_NOME() -> None:
    """`key=lambda kv: (-int(kv[1].get("total", {}).get("n", 0)), kv[0])`.

    Tre mutanti in una riga: il ripiego a zero quando manca il totale, e
    l'indice del secondo criterio — col mutante `kv[1]` la parita' verrebbe
    sciolta confrontando due DIZIONARI invece dei nomi, cioe' per un dettaglio
    che l'utente non vede e che puo' cambiare da una rigenerazione all'altra."""
    sommario = {
        "detectors": {
            "zeta": {"total": {"n": 5}},
            "alfa": {"total": {"n": 5}},      # pari merito con zeta
            "molti": {"total": {"n": 99}},
            "senza_totale": {},               # niente `total`: vale zero
        },
    }
    nomi = [d["detector"] for d in _replay_block(sommario, 30)["detectors"]]
    assert nomi == ["molti", "alfa", "zeta", "senza_totale"]


def test_un_sommario_senza_conteggio_segnali_legge_ZERO() -> None:
    """`int(summary.get("n_signals", 0))`: il ripiego e' zero, non uno. Col
    mutante un artefatto privo del campo dichiarerebbe un segnale che non
    esiste."""
    assert _replay_block({"detectors": {}}, 30)["n_signals"] == 0


def test_i_detector_a_PARI_MERITO_si_ordinano_per_nome(db, titolo) -> None:
    """`sorted(by_detector.items(), key=lambda kv: (-len(kv[1]), kv[0]))` nella
    lista VIVA. Stessa forma del replay: col mutante la parita' si scioglie
    confrontando le liste di righe invece dei nomi — e in Python due liste di
    oggetti ORM non sono nemmeno confrontabili, quindi si passa da un ordine
    stabile a un `TypeError` durante il rendering della pagina."""
    d0 = date(2026, 1, 1)
    for nome in ("zulu", "alfa"):
        _esito(db, titolo.id, detector=nome, tono="bull", giorno=d0, rendimento=0.05)
    db.commit()

    cubo = perf.compute_detector_performance(db)
    nomi = [d["detector"] for d in cubo["detectors"]]
    assert nomi == sorted(nomi), nomi
    assert nomi[0] == "alfa"
