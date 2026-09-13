"""I confini della confluenza, che nessun test percorreva.

⚠️ Trovati dalla sonda di mutazione: `confluence_service` ne uccideva 17 su 38.
Il servizio decide COSA compare in cima alla pagina Segnali e con che forza, e
i suoi difetti non sollevano eccezioni — riordinano una lista.

I tre che contano, e perche':

1. Riga 180, `_dir_strength([(c[3], c[1]) for c in bear])` -> `c[2]`. La tupla
   e' `(aid, sname, sdate, conf, tone, hz)`: il mutante passa la DATA al posto
   del nome del detector, quindi `_FAMILY` non riconosce piu' niente e la
   de-correlazione per famiglia — «N segnali correlati contano ~1,3, non N»,
   cioe' l'intera ragione d'essere del servizio — smette di funzionare. ⚠️ Il
   gemello rialzista una riga sopra era gia' ucciso: i test coprivano una
   direzione e non l'altra.

2. Righe 197 e 213, `reverse=True`. Col mutante la pagina mostra le confluenze
   PIU' DEBOLI in cima, e dentro ogni gruppo i segnali dal meno forte al piu'
   forte. Nessun errore: solo una lista girata.

3. Riga 167, il filtro di validita' `conf is None or tone not in (...) or not
   sname` -> `and`. Col mutante le righe malformate entrano nei gruppi: due
   segnali senza tono formano una confluenza di forza zero, che a schermo e'
   comunque una confluenza — porta un ticker, un conteggio e una scheda.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.models import Alert, Stock
from app.services import confluence_service as cs
from app.services.confluence_service import compute_confluence


def _titolo(db, ticker: str) -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    return s


def _segnale(db, stock_id, nome, forza, tono, *, orizzonte="medium", giorno=None,
             snapshot=None) -> None:
    db.add(Alert(
        stock_id=stock_id, trigger_price=10,
        signal_date=giorno if giorno is not None else date.today(),
        signal_name=nome,
        snapshot=json.dumps(snapshot if snapshot is not None else
                            {"tone": tono, "strength": forza, "horizon": orizzonte}),
    ))


# ─── 1. La de-correlazione vale per ENTRAMBE le direzioni ─────────────────


def test_la_decorrelazione_funziona_anche_sul_lato_RIBASSISTA(db) -> None:
    """⚠️ Il gemello rialzista era coperto e questo no: una simmetria del
    codice non e' una simmetria dei test, ed e' la sonda a mostrarlo.

    Tre detector della STESSA famiglia devono valere meno di tre di famiglie
    diverse. Col mutante che passa la data al posto del nome, `_FAMILY` non
    riconosce piu' niente, ogni data diventa la sua famiglia e i due casi
    collassano sullo stesso numero.
    """
    a = _titolo(db, "STESSA")
    for nome in ("trend_pullback", "volume_breakout", "adx_confirmation"):
        _segnale(db, a.id, nome, 70, "bear")          # tutti famiglia "trend"
    b = _titolo(db, "DIVERSE")
    for nome in ("trend_pullback", "rsi_divergence", "oversold_reversal"):
        _segnale(db, b.id, nome, 70, "bear")          # trend / divergence / level
    db.commit()

    per_ticker = {c.ticker: c for c in compute_confluence(db, days=30)}
    stessa, diverse = per_ticker["STESSA"], per_ticker["DIVERSE"]
    assert stessa.effective_n == pytest.approx(1.30)
    assert diverse.effective_n == pytest.approx(3.00)
    assert diverse.strength > stessa.strength


# ─── 2. L'ordine e' cio' che l'utente legge ───────────────────────────────


def test_i_gruppi_PIU_FORTI_stanno_in_cima(db) -> None:
    """`clusters.sort(..., reverse=True)`. Col mutante la pagina Segnali
    mostra le confluenze piu' deboli per prime — nessun errore, solo una lista
    girata, che e' il difetto piu' difficile da vedere a occhio.
    """
    forte = _titolo(db, "FORTE")
    _segnale(db, forte.id, "trend_pullback", 90, "bull")
    _segnale(db, forte.id, "rsi_divergence", 88, "bull")
    debole = _titolo(db, "DEBOLE")
    _segnale(db, debole.id, "trend_pullback", 40, "bull")
    _segnale(db, debole.id, "rsi_divergence", 38, "bull")
    db.commit()

    gruppi = compute_confluence(db, days=30)
    assert [c.ticker for c in gruppi] == ["FORTE", "DEBOLE"]


def test_dentro_un_gruppo_i_segnali_scendono_per_FORZA(db) -> None:
    """`sorted(items, key=lambda c: c[3], reverse=True)`: il componente piu'
    forte per primo. Col mutante il gruppo si apre sul segnale piu' debole.
    """
    s = _titolo(db, "ORD")
    _segnale(db, s.id, "trend_pullback", 55, "bull")
    _segnale(db, s.id, "rsi_divergence", 91, "bull")
    _segnale(db, s.id, "oversold_reversal", 73, "bull")
    db.commit()

    comp = compute_confluence(db, days=30)[0].components
    forze = [c.confidence for c in comp]
    assert forze == sorted(forze, reverse=True), forze
    assert forze[0] == pytest.approx(91.0)


# ─── 3. Le righe malformate non fanno una confluenza ──────────────────────


def test_due_segnali_SENZA_TONO_non_formano_una_confluenza(db) -> None:
    """`if conf is None or tone not in ("bull","bear") or not sname: continue`.

    Col mutante `and` la riga passa il filtro, finisce nel gruppo e contribuisce
    a `n_signals`: due segnali malformati diventano una confluenza di forza
    zero. ⚠️ A schermo una confluenza a forza zero e' comunque una confluenza.
    """
    s = _titolo(db, "ROTTI")
    _segnale(db, s.id, "trend_pullback", 80, "bull",
             snapshot={"strength": 80, "horizon": "medium"})          # tono assente
    _segnale(db, s.id, "rsi_divergence", 70, "bull",
             snapshot={"tone": "laterale", "strength": 70})           # tono non valido
    db.commit()
    assert compute_confluence(db, days=30) == []


def test_un_segnale_senza_FORZA_viene_scartato(db) -> None:
    """L'altro termine dello stesso filtro: senza, il test sopra sarebbe vero
    anche di un filtro che guarda soltanto il tono.
    """
    s = _titolo(db, "NOFORZA")
    _segnale(db, s.id, "trend_pullback", 0, "bull", snapshot={"tone": "bull"})
    _segnale(db, s.id, "rsi_divergence", 0, "bull", snapshot={"tone": "bull"})
    db.commit()
    assert compute_confluence(db, days=30) == []


# ─── 4. I bordi delle soglie ──────────────────────────────────────────────


def test_a_PARITA_di_forza_la_direzione_e_rialzista(db) -> None:
    """`direction = "bull" if bs >= rs else "bear"`, col bordo INCLUSO.

    ⚠️ La scelta e' ARBITRARIA — a parita' esatta nessuna delle due direzioni
    prevale davvero. Il test la rende esplicita: se un giorno si decide che il
    pari vale «bear», questo deve rompersi e costringere a dirlo, invece di
    lasciare che il confine si sposti da solo.
    """
    s = _titolo(db, "PARI")
    _segnale(db, s.id, "trend_pullback", 70, "bull")
    _segnale(db, s.id, "trend_pullback", 70, "bear")
    db.commit()

    c = compute_confluence(db, days=30)[0]
    assert c.bull_strength == c.bear_strength
    assert c.direction == "bull"


def test_uno_scarto_ESATTAMENTE_pari_alla_soglia_non_e_conteso(db) -> None:
    """`abs(bs - rs) < _CONTESTED_GAP`, col bordo ESCLUSO: venticinque punti
    esatti NON sono contesi.

    ⚠️ Le forze si costruiscono con un solo detector per lato, dove il termine
    di bonus e' esattamente zero (n_eff = 1) e la forza coincide con la Forza
    del segnale: cosi' lo scarto e' quello scritto, non un'approssimazione.
    """
    s = _titolo(db, "BORDO")
    _segnale(db, s.id, "trend_pullback", 80.0, "bull")
    _segnale(db, s.id, "rsi_divergence", 80.0 - cs._CONTESTED_GAP, "bear")
    db.commit()

    c = compute_confluence(db, days=30)[0]
    assert abs(c.bull_strength - c.bear_strength) == pytest.approx(cs._CONTESTED_GAP)
    assert c.contested is False


def test_un_segnale_datato_ESATTAMENTE_al_limite_della_finestra_ENTRA(db) -> None:
    """`Alert.signal_date >= cutoff`, col bordo INCLUSO. Col mutante una
    finestra di N giorni ne copre N-1, e i segnali del giorno piu' vecchio
    spariscono dalla pagina senza che niente lo dica.
    """
    s = _titolo(db, "LIMITE")
    limite = date.today() - timedelta(days=7)
    _segnale(db, s.id, "trend_pullback", 80, "bull", giorno=limite)
    _segnale(db, s.id, "rsi_divergence", 75, "bull", giorno=limite)
    db.commit()

    gruppi = compute_confluence(db, days=7)
    assert len(gruppi) == 1
    assert gruppi[0].n_signals == 2


def test_a_PARITA_di_forza_il_multi_orizzonte_RIALZISTA_passa_avanti(db) -> None:
    """`key=lambda c: (c.strength, c.multi_horizon and c.direction == "bull", ...)`.

    Il vantaggio multi-orizzonte e' misurato SOLO al rialzo (~+0,8%/30g), e il
    commento accanto al codice lo dice: i ribassisti non ricevono priorita'.
    Col mutante `!=` la precedenza passa ai ribassisti — cioe' la pagina
    applica un vantaggio dove il backtest non ne ha trovato nessuno.
    """
    su = _titolo(db, "SU")
    _segnale(db, su.id, "trend_pullback", 80, "bull", orizzonte="short")
    _segnale(db, su.id, "trend_pullback", 80, "bull", orizzonte="long")
    giu = _titolo(db, "GIU")
    _segnale(db, giu.id, "trend_pullback", 80, "bear", orizzonte="short")
    _segnale(db, giu.id, "trend_pullback", 80, "bear", orizzonte="long")
    db.commit()

    gruppi = compute_confluence(db, days=30)
    assert len({c.strength for c in gruppi}) == 1, "le due forze non sono pari"
    assert all(c.multi_horizon for c in gruppi)
    assert gruppi[0].ticker == "SU"


def test_i_tre_orizzonti_hanno_un_ordine_STRETTO() -> None:
    """I valori di `_HORIZON_ORDER` devono essere distinti e crescenti.

    ⚠️ Non fissa i NUMERI — 0/1/2 potrebbero essere 10/20/30 — ma la proprieta'
    da cui dipende la correttezza: l'ingresso di `sorted` e' un SET, quindi due
    orizzonti a pari chiave lascerebbero l'ordine all'iterazione del set, cioe'
    variabile fra esecuzioni.

    E' anche il motivo per cui i mutanti su quella riga NON si uccidono
    attraverso il comportamento: un test che ci provasse sarebbe intermittente,
    che e' peggio di un mutante vivo. Si asserisce la struttura.
    """
    valori = cs._HORIZON_ORDER
    assert set(valori) == {"short", "medium", "long"}
    assert len(set(valori.values())) == 3, f"orizzonti a pari chiave: {valori}"
    assert valori["short"] < valori["medium"] < valori["long"]
