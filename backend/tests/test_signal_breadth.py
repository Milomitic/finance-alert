"""Was this signal about this stock, or about the whole market that morning?

Measured over the live alert table, the answer varies enormously by detector:

    trend_pullback    fires alongside 43 other stocks on average (max 127)
    candle_reversal   29
    gap_and_go         2.7 (max 8)

So a `trend_pullback` is almost never idiosyncratic — it is a market-wide
condition that happened to touch this name — while a `gap_and_go` really is
about the stock. The platform has always known this and never said it, so
every alert reads the same whether one stock moved or a hundred did.

⚠️ IT IS CONTEXT, NEVER CONFIRMATION. CLAUDE.md records two independent
studies finding concurrence NULL at h=1/2/3/5 — knowing that forty names did
the same thing does not make the signal better. It changes what the READER
should conclude: if it is sector-wide, the stock is telling you nothing of its
own. That is why the count is honest to show and would be dishonest to fold
into Forza or Probabilità.

⚠️ FA-064: the count is PER DIRECTION. It summed both ways, and in production
the count of 7.088 alerts out of 8.397 included stocks that fired the same
detector the opposite way.
"""

import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, Stock, User
from app.schemas.alert import AlertOut
from app.services.signal_breadth_service import breadth_for, peers_for


def _stock(db, ticker: str, sector: str | None = "Information Technology") -> Stock:
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, sector=sector)
    db.add(s)
    db.commit()
    return s


def _alert(db, stock: Stock, name: str, on: date | None, tone: str | None = "bull") -> Alert:
    a = Alert(
        stock_id=stock.id,
        signal_name=name,
        signal_date=on,
        triggered_at=datetime(2026, 9, 8, 10, 0),
        trigger_price=100.0,
        # Colonna Text, non JSON: il tono vive dentro lo snapshot.
        snapshot=json.dumps({"tone": tone}) if tone is not None else "{}",
    )
    db.add(a)
    db.commit()
    return a


D = date(2026, 9, 8)


class TestTheCount:
    def test_a_lone_signal_reports_no_company(self, db):
        me = _stock(db, "NVDA")
        a = _alert(db, me, "gap_and_go", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.opposite_tone) == (0, 0)

    def test_it_counts_the_other_stocks_that_fired_the_same_day(self, db):
        me = _stock(db, "NVDA")
        for t in ("AMD", "INTC", "MU"):
            _alert(db, _stock(db, t), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].same_tone == 3

    def test_the_stock_itself_is_never_one_of_the_others(self, db):
        me = _stock(db, "NVDA")
        a = _alert(db, me, "trend_pullback", D)
        # Same detector, same day, same stock — a re-fire, not a peer. Even the
        # OPPOSITE way: a stock is never its own company.
        _alert(db, me, "trend_pullback", D)
        _alert(db, me, "trend_pullback", D, tone="bear")

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]
        assert (got.same_tone, got.opposite_tone) == (0, 0)

    def test_a_different_detector_the_same_day_does_not_count(self, db):
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "candle_reversal", D)
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].same_tone == 0

    def test_the_same_detector_on_a_different_day_does_not_count(self, db):
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "trend_pullback", date(2026, 9, 7))
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].same_tone == 0


class TestTheDirection:
    """⚠️ FA-064. The defect this class exists for."""

    def test_a_peer_that_fired_the_OTHER_way_is_not_company(self, db):
        """The case that was 84% of production: the same detector, the same
        morning, the opposite direction. Folding it into «altri titoli» said
        the opposite of what happened — a detector firing both ways is not a
        market condition in one direction."""
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone="bull")
        _alert(db, _stock(db, "XOM"), "trend_pullback", D, tone="bear")
        _alert(db, _stock(db, "CVX"), "trend_pullback", D, tone="bear")
        a = _alert(db, me, "trend_pullback", D, tone="bull")

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.opposite_tone) == (1, 2)

    def test_the_direction_is_the_alerts_own_not_a_majority(self, db):
        # The same group read from the bear side: counts swap, nothing else.
        me = _stock(db, "XOM")
        _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone="bull")
        _alert(db, _stock(db, "CVX"), "trend_pullback", D, tone="bear")
        a = _alert(db, me, "trend_pullback", D, tone="bear")

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.opposite_tone) == (1, 1)

    def test_the_sector_split_only_counts_the_same_direction(self, db):
        """Otherwise «di cui 2 nello stesso settore» could exceed the same-way
        count it claims to be a subset of."""
        me = _stock(db, "NVDA", "Information Technology")
        _alert(db, _stock(db, "AMD", "Information Technology"), "trend_pullback", D, tone="bull")
        _alert(db, _stock(db, "MU", "Information Technology"), "trend_pullback", D, tone="bear")
        a = _alert(db, me, "trend_pullback", D, tone="bull")

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.same_tone_sector, got.opposite_tone) == (1, 1, 1)

    def test_a_peer_with_no_direction_is_neither(self, db):
        # One such row exists in production. It is not «same», and calling it
        # «opposite» would be inventing a direction.
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone=None)
        a = _alert(db, me, "trend_pullback", D, tone="bull")

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.opposite_tone) == (0, 0)

    def test_an_alert_with_no_direction_gets_nothing(self, db):
        # No direction, no «same direction» — absent, not zero.
        me = _stock(db, "NVDA")
        _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone="bull")
        a = _alert(db, me, "trend_pullback", D, tone=None)

        assert a.id not in breadth_for(db, [a], stock_id=me.id, sector=me.sector)


class TestTheSectorSplit:
    """The whole point is telling a sector move from a market move."""

    def test_it_separates_peers_in_the_same_sector(self, db):
        me = _stock(db, "NVDA", "Information Technology")
        _alert(db, _stock(db, "AMD", "Information Technology"), "trend_pullback", D)
        _alert(db, _stock(db, "MU", "Information Technology"), "trend_pullback", D)
        _alert(db, _stock(db, "XOM", "Energy"), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.same_tone_sector) == (3, 2)

    def test_a_stock_with_no_sector_reports_others_but_no_split(self, db):
        me = _stock(db, "PURR", None)
        _alert(db, _stock(db, "AMD"), "trend_pullback", D)
        a = _alert(db, me, "trend_pullback", D)

        got = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id]

        assert (got.same_tone, got.same_tone_sector) == (1, 0)


class TestWhatItRefusesToDo:
    def test_it_does_NOT_exclude_archived_alerts(self, db):
        """A count that shrinks when the user files their inbox is not a count.

        CLAUDE.md's rule — never filter a measurement on a field the USER
        writes — was learned the expensive way: the outcome warehouse was
        showing 19 of its 4,880 rows because three consumers excluded archived
        alerts, and archival tracks AGE.
        """
        me = _stock(db, "NVDA")
        peer = _alert(db, _stock(db, "AMD"), "trend_pullback", D)
        peer.archived_at = datetime(2026, 9, 9, 12, 0)
        db.commit()
        a = _alert(db, me, "trend_pullback", D)

        assert breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].same_tone == 1

    def test_a_legacy_alert_without_a_signal_date_gets_nothing(self, db):
        me = _stock(db, "NVDA")
        a = _alert(db, me, "trend_pullback", None)

        assert a.id not in breadth_for(db, [a], stock_id=me.id, sector=me.sector)


def test_it_answers_a_whole_page_of_alerts_in_one_pass(db):
    # The detail card renders up to 50; this must not be 50 queries.
    me = _stock(db, "NVDA")
    _alert(db, _stock(db, "AMD"), "trend_pullback", D)
    _alert(db, _stock(db, "MU"), "candle_reversal", D)
    mine = [_alert(db, me, "trend_pullback", D), _alert(db, me, "candle_reversal", D)]

    got = breadth_for(db, mine, stock_id=me.id, sector=me.sector)

    assert {k: v.same_tone for k, v in got.items()} == {mine[0].id: 1, mine[1].id: 1}


@pytest.mark.parametrize("alerts", [[], None])
def test_no_alerts_asks_nothing_of_the_database(db, alerts):
    assert breadth_for(db, alerts or [], stock_id=1, sector="Energy") == {}


# ─── The components: the list must be the number ─────────────────────────


def _mondo_di_bordo(db):
    """Every edge case where a count and a list could quietly disagree."""
    me = _stock(db, "NVDA")
    a = _alert(db, me, "trend_pullback", D, tone="bull")
    # counted
    _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone="bull")
    archiviato = _alert(db, _stock(db, "MU"), "trend_pullback", D, tone="bull")
    archiviato.archived_at = datetime(2026, 9, 9)
    doppio = _stock(db, "INTC")
    _alert(db, doppio, "trend_pullback", D, tone="bull")
    _alert(db, doppio, "trend_pullback", D, tone="bull")  # stesso titolo due volte
    # NOT counted
    _alert(db, me, "trend_pullback", D, tone="bull")           # se stesso
    _alert(db, _stock(db, "XOM"), "trend_pullback", D, tone="bear")
    _alert(db, _stock(db, "PURR"), "trend_pullback", D, tone=None)
    _alert(db, _stock(db, "QCOM"), "candle_reversal", D, tone="bull")
    _alert(db, _stock(db, "TXN"), "trend_pullback", date(2026, 9, 7), tone="bull")
    db.commit()
    return me, a


def test_la_lista_e_il_numero_contano_la_stessa_popolazione(db):
    """⚠️ Il test che tiene insieme il conteggio e i suoi componenti.

    Il conteggio applica il predicato RAGGRUPPATO su una pagina intera e la
    lista lo applica per un solo alert: sono due query, equivalenti per lettura
    e non per costruzione. Qui si mettono insieme tutti i casi dove una deriva
    si nasconderebbe — un archiviato, un titolo che scatta due volte, un
    compagno senza direzione, la direzione opposta, un altro detector, un
    altro giorno — e si pretende che contino le stesse cose.
    """
    me, a = _mondo_di_bordo(db)

    numero = breadth_for(db, [a], stock_id=me.id, sector=me.sector)[a.id].same_tone
    lista = peers_for(db, a)

    assert numero == 3
    assert [p.ticker for p in lista] == ["AMD", "INTC", "MU"]
    assert len(lista) == numero


def test_un_alert_senza_data_o_direzione_non_ha_componenti(db):
    me = _stock(db, "NVDA")
    _alert(db, _stock(db, "AMD"), "trend_pullback", D, tone="bull")

    assert peers_for(db, _alert(db, me, "trend_pullback", None)) == []
    assert peers_for(db, _alert(db, me, "trend_pullback", D, tone=None)) == []


@pytest.fixture
def client(db):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_l_endpoint_restituisce_i_componenti(client, db):
    _, a = _mondo_di_bordo(db)

    r = client.get(f"/api/alerts/{a.id}/peers")

    assert r.status_code == 200
    assert [p["ticker"] for p in r.json()] == ["AMD", "INTC", "MU"]


def test_l_endpoint_su_un_alert_inesistente_e_404(client, db):
    assert client.get("/api/alerts/999999/peers").status_code == 404


def test_i_nomi_vecchi_non_esistono_piu():
    """⚠️ I nomi sono cambiati INSIEME al significato, di proposito.

    `same_day_others` contava i due versi. Tenere il nome con il significato
    nuovo lascerebbe un consumatore rimasto indietro a mostrare un numero che
    vuol dire un'altra cosa senza accorgersene; togliendolo legge `undefined`
    e non mostra niente. Stessa scelta di FA-031 con `unit`."""
    campi = set(AlertOut.model_fields)

    assert "same_day_others" not in campi
    assert "same_day_sector" not in campi
    assert {"same_day_same_tone", "same_day_same_tone_sector", "same_day_opposite_tone"} <= campi
