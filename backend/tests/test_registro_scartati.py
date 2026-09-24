"""Il registro dei match che i cancelli dello scan scartano.

⚠️ Fino al 2026-09-24 di cio' che un cancello scartava non restava traccia:
si osservavano solo gli esiti di cio' che passava, quindi l'effetto di un
cancello non era misurabile dal vivo per costruzione. Lo studio sulla storia
aveva trovato che la soglia di Forza non ordina gli esiti e che il cancello del
trend scarta, se qualcosa, segnali un po' migliori; il registro e' la conferma
fuori campione.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import select

from app.models import Alert, OhlcvDaily, SignalCandidate, SignalOutcome, Stock
from app.services import signal_outcome_service as sos
from app.signals.detectors.base import SignalMatch
from app.signals.signal_scan_service import _registra_scartato, evaluate_signals

_OGGI = date(2026, 5, 30)


def _df() -> pd.DataFrame:
    """Una serie che scambia (la guardia sui titoli fermi non deve intervenire)."""
    righe = []
    for i in range(40):
        d = _OGGI - timedelta(days=39 - i)
        c = 100.0 + (i % 5)
        righe.append({"date": d.isoformat(), "open": c, "high": c + 2, "low": c - 2,
                      "close": c, "volume": 1000})
    return pd.DataFrame(righe)


def _match(*, nome="sr_flip", tono="bull", forza=70, data=_OGGI) -> SignalMatch:
    return SignalMatch(name=nome, tone=tono, signal_date=data.isoformat(),
                       chain=[{"date": data.isoformat(), "label": "x"}],
                       invalidation={"level": 90.0}, factors={"retest_proximity": 0.42},
                       strength=forza, probability=50)


@dataclass
class _Ctx:
    trend_sign: int
    atr: float = 2.0
    last_close: float = 100.0


@pytest.fixture
def scan(db, monkeypatch):
    """Lo scan con un match e un trend scelti dal test."""
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 60)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", True)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", True)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_max_age_days", 7)
    stato: dict = {"matches": [], "trend": 1}
    monkeypatch.setattr("app.signals.signal_scan_service.build_context",
                        lambda _o: _Ctx(trend_sign=stato["trend"]))
    monkeypatch.setattr("app.signals.signal_scan_service.detect_signals_and_setups",
                        lambda *a, **k: (list(stato["matches"]), []))
    s = Stock(ticker="SCART", exchange="NASDAQ", name="Scartati", country="US")
    db.add(s)
    db.flush()

    def gira(*matches: SignalMatch, trend: int = 1, df: pd.DataFrame | None = None) -> int:
        stato["matches"], stato["trend"] = matches, trend
        return evaluate_signals(db, s, df if df is not None else _df())

    gira.stock = s  # type: ignore[attr-defined]
    return gira


def _righe(db) -> list[SignalCandidate]:
    return list(db.execute(select(SignalCandidate).order_by(SignalCandidate.id)).scalars())


# ─── Che cosa entra ────────────────────────────────────────────────────────

def test_un_match_con_forza_bassa_si_registra_col_suo_cancello(db, scan) -> None:
    assert scan(_match(forza=40)) == 0

    (r,) = _righe(db)
    assert (r.passa_forza, r.passa_trend, r.passa_follow) == (False, True, True)
    assert r.strength == 40 and r.detector == "sr_flip" and r.tone == "bull"
    assert r.signal_date == _OGGI and r.bar_date == _OGGI
    assert json.loads(r.factors) == {"retest_proximity": 0.42}
    assert db.query(Alert).count() == 0


def test_si_registrano_TUTTI_i_cancelli_non_il_primo_che_fallisce(db, scan) -> None:
    """Forza bassa E trend contrario: il registro deve dirle entrambe, perche'
    sapere quale dei due lo avrebbe fermato da solo e' la domanda."""
    scan(_match(forza=40, tono="bull"), trend=-1)

    (r,) = _righe(db)
    assert (r.passa_forza, r.passa_trend) == (False, False)


def test_un_trend_contrario_da_solo_basta_a_registrarlo(db, scan) -> None:
    scan(_match(forza=80, tono="bull"), trend=-1)

    (r,) = _righe(db)
    assert (r.passa_forza, r.passa_trend, r.passa_follow) == (True, False, True)
    assert db.query(Alert).count() == 0


def test_adx_confirmation_non_emette_e_non_finisce_fra_gli_scartati(db, scan) -> None:
    """Declassato (2026-09-24): anti-skill di direzione. Lo stesso match che
    sotto diventa un alert, col nome di adx, non produce niente."""
    assert scan(_match(nome="adx_confirmation", forza=80)) == 0
    assert _righe(db) == []
    assert db.query(Alert).count() == 0


def test_la_catena_degli_altri_riconosce_ancora_l_evento_adx() -> None:
    """Il declassamento toglie l'ALERT, non l'evento: `adx_trend` resta una
    conferma per gli altri detector."""
    from app.signals.chain_enrichment import _CONFIRMATION_TYPES
    from app.signals.detectors.registry import DETECTORS, NON_EMESSI

    assert "adx_trend" in _CONFIRMATION_TYPES
    assert "adx_confirmation" in {d.name for d in DETECTORS}
    assert {"adx_confirmation"} == NON_EMESSI


def test_un_match_che_passa_tutto_diventa_un_alert_e_NON_un_registro(db, scan) -> None:
    """Controllo negativo: senza, il registro potrebbe accogliere tutto e i
    test sopra passerebbero lo stesso."""
    assert scan(_match(forza=80)) == 1

    assert _righe(db) == []
    assert db.query(Alert).count() == 1


def test_un_match_vecchio_non_e_una_decisione_di_un_cancello(db, scan) -> None:
    """Oltre la finestra di recenza lo scan non lo emetterebbe comunque: non e'
    un cancello di qualita' ad averlo fermato, quindi nel registro non entra."""
    scan(_match(forza=40, data=_OGGI - timedelta(days=20)))

    assert _righe(db) == []


# ─── Una condizione che persiste non gonfia il campione ────────────────────

def test_la_stessa_condizione_rivista_a_ogni_scansione_resta_UNA_riga(db, scan) -> None:
    scan(_match(forza=40, data=_OGGI))
    scan(_match(forza=40, data=_OGGI))                          # stessa barra
    scan(_match(forza=40, data=_OGGI + timedelta(days=3)),      # la barra avanza
         df=_df().assign(date=lambda d: pd.to_datetime(d.date).add(pd.Timedelta(days=3))
                         .dt.strftime("%Y-%m-%d")))

    assert len(_righe(db)) == 1


def test_oltre_il_cooldown_e_un_episodio_nuovo(db, scan, monkeypatch) -> None:
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_dedup_cooldown_days", 14)
    scan(_match(forza=40, data=_OGGI))
    dopo = _OGGI + timedelta(days=20)
    scan(_match(forza=40, data=dopo),
         df=_df().assign(date=lambda d: pd.to_datetime(d.date).add(pd.Timedelta(days=20))
                         .dt.strftime("%Y-%m-%d")))

    assert [r.signal_date for r in _righe(db)] == [_OGGI, dopo]


def test_un_doppione_non_fa_esplodere_la_scansione(db, scan) -> None:
    """⚠️ Il caso che conta. Lo scan cattura l'eccezione di un titolo SENZA
    rollback, e su Postgres una scrittura fallita lascia la sessione abortita:
    tutti i titoli successivi fallirebbero. Qui la riga esiste gia' ma il
    promemoria in memoria non lo sa (due scansioni insieme): l'inserimento deve
    tacere, non sollevare."""
    scan(_match(forza=40))
    _registra_scartato(db, scan.stock.id, _match(forza=40), _OGGI, _OGGI, 100.0,
                       False, True, True, scartati={})
    db.flush()

    assert len(_righe(db)) == 1


# ─── L'esito, con la stessa aritmetica degli alert ─────────────────────────

def _barre(db, stock: Stock, chiusure: list[float], dal: date) -> None:
    for i, c in enumerate(chiusure):
        db.add(OhlcvDaily(stock_id=stock.id, date=dal + timedelta(days=i), open=c,
                          high=c + 1, low=c - 1, close=c, volume=1_000_000))
    db.flush()


def test_l_esito_di_uno_scartato_e_quello_che_avrebbe_avuto_un_alert(db, monkeypatch) -> None:
    """Lo stesso titolo, la stessa data, lo stesso verso: uno scartato e un
    alert devono maturare allo STESSO numero. E' il confronto che il registro
    serve a fare, e due aritmetiche diverse lo renderebbero una misura dei
    metodi invece che dei cancelli."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    s = Stock(ticker="PARI", exchange="NASDAQ", name="Pari", country="US")
    db.add(s)
    db.flush()
    dal = date(2026, 1, 1)
    _barre(db, s, [10, 11, 12, 13, 14, 15, 16, 17], dal)
    giorno = dal + timedelta(days=2)
    db.add(SignalCandidate(stock_id=s.id, detector="sr_flip", tone="bull", signal_date=giorno,
                           bar_date=giorno, close=12.0, strength=40, passa_forza=False,
                           passa_trend=True, passa_follow=True, factors="{}"))
    db.add(Alert(stock_id=s.id, trigger_price=12.0, signal_date=giorno, signal_name="sr_flip",
                 snapshot=json.dumps({"tone": "bull", "strength": 70})))
    db.commit()

    assert sos.mature_candidate_outcomes(db) == 1
    sos.mature_outcomes(db)

    cand = db.execute(select(SignalCandidate)).scalars().one()
    alert = db.execute(select(SignalOutcome)).scalars().one()
    assert cand.horizon_days == 3
    assert cand.fwd_return == pytest.approx(15 / 12 - 1)
    assert cand.fwd_return == pytest.approx(alert.fwd_return)
    assert cand.mkt_neutral_hit == alert.mkt_neutral_hit
    assert cand.matured_at is not None


def test_un_orizzonte_non_ancora_trascorso_non_matura(db, monkeypatch) -> None:
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 21)
    s = Stock(ticker="PRESTO", exchange="NASDAQ", name="Presto", country="US")
    db.add(s)
    db.flush()
    dal = date(2026, 1, 1)
    _barre(db, s, [10, 11, 12, 13, 14], dal)
    db.add(SignalCandidate(stock_id=s.id, detector="sr_flip", tone="bull", signal_date=dal,
                           bar_date=dal, close=10.0, strength=40, passa_forza=False,
                           passa_trend=True, passa_follow=True, factors="{}"))
    db.commit()

    assert sos.mature_candidate_outcomes(db) == 0
    assert db.execute(select(SignalCandidate)).scalars().one().matured_at is None


def test_la_maturazione_e_idempotente(db, monkeypatch) -> None:
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    s = Stock(ticker="IDEM", exchange="NASDAQ", name="Idem", country="US")
    db.add(s)
    db.flush()
    dal = date(2026, 1, 1)
    _barre(db, s, [10, 11, 12, 13, 14, 15, 16, 17], dal)
    db.add(SignalCandidate(stock_id=s.id, detector="sr_flip", tone="bear", signal_date=dal,
                           bar_date=dal, close=10.0, strength=40, passa_forza=False,
                           passa_trend=True, passa_follow=True, factors="{}"))
    db.commit()

    assert sos.mature_candidate_outcomes(db) == 1
    assert sos.mature_candidate_outcomes(db) == 0


def test_matura_ESATTAMENTE_quando_l_orizzonte_e_trascorso(db, monkeypatch) -> None:
    """Il bordo: la barra del segnale piu' H barre dopo, e non una di piu'.

    Il filtro SQL dei maturabili deve dire la stessa cosa di `_label` (che
    vuole `ti + H < len`): un confine sfasato di uno lascerebbe ogni scartato
    in attesa una seduta in piu', o lo farebbe maturare su una barra che non
    c'e'. Scritto dopo che la sonda di mutazione ha trovato scoperti sia `>=`
    contro `>` sulla data sia `H + 1` contro `H + 2`."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    s = Stock(ticker="BORDO", exchange="NASDAQ", name="Bordo", country="US")
    db.add(s)
    db.flush()
    dal = date(2026, 1, 1)
    _barre(db, s, [10, 11, 12, 13], dal)          # segnale + esattamente 3 barre
    db.add(SignalCandidate(stock_id=s.id, detector="sr_flip", tone="bull", signal_date=dal,
                           bar_date=dal, close=10.0, strength=40, passa_forza=False,
                           passa_trend=True, passa_follow=True, factors="{}"))
    db.commit()

    assert sos.mature_candidate_outcomes(db) == 1
    c = db.execute(select(SignalCandidate)).scalars().one()
    assert c.fwd_return == pytest.approx(13 / 10 - 1)


def test_senza_commit_non_scrive(db, monkeypatch) -> None:
    """Lo scan passa `commit=False` quando scrive tutto in una transazione sola:
    la maturazione non deve fare commit per conto suo. Trovato scoperto dalla
    sonda (`commit and scritte` -> `commit or scritte`)."""
    monkeypatch.setattr(sos, "_horizon_days", lambda _d: 3)
    s = Stock(ticker="NOCOMMIT", exchange="NASDAQ", name="Senza commit", country="US")
    db.add(s)
    db.flush()
    dal = date(2026, 1, 1)
    _barre(db, s, [10, 11, 12, 13, 14], dal)
    db.add(SignalCandidate(stock_id=s.id, detector="sr_flip", tone="bull", signal_date=dal,
                           bar_date=dal, close=10.0, strength=40, passa_forza=False,
                           passa_trend=True, passa_follow=True, factors="{}"))
    db.commit()

    assert sos.mature_candidate_outcomes(db, commit=False) == 1
    db.rollback()
    assert db.execute(select(SignalCandidate)).scalars().one().matured_at is None


# ─── I modelli in ombra (fase 3) ───────────────────────────────────────────

def test_scartati_e_alert_portano_contesto_e_punteggi_in_ombra(db, scan, monkeypatch) -> None:
    """Il modello di selezione sceglie fra TUTTI i match, prima dei cancelli:
    va valutato anche sugli scartati, quindi anche loro portano contesto e
    punteggio. E l'alert li fissa nello snapshot come le altre variabili
    dell'ingresso."""
    finto = {"vol": {"fattore": 1.2, "versione": "t"}, "sel": {"p": 0.6, "top30": True, "versione": "t"}}
    monkeypatch.setattr("app.signals.signal_scan_service.ombra.punteggi_per_match",
                        lambda *a, **k: finto)
    scan(_match(forza=40))
    (r,) = _righe(db)
    assert json.loads(r.ombra) == finto
    assert "atr_pct" in json.loads(r.contesto)

    scan(_match(nome="trend_pullback", forza=80))
    (a,) = db.query(Alert).all()
    assert json.loads(a.snapshot)["first_ombra"] == finto


def test_senza_modelli_nessuna_chiave_in_ombra(db, scan) -> None:
    """Controllo negativo: un punteggio assente non diventa un dizionario
    vuoto scritto come se fosse stato calcolato."""
    scan(_match(forza=40))
    scan(_match(nome="trend_pullback", forza=80))
    (r,) = _righe(db)
    assert r.ombra is None and r.contesto is not None
    (a,) = db.query(Alert).all()
    assert "first_ombra" not in json.loads(a.snapshot)
