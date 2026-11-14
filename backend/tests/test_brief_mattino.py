"""Il brief del mattino (FA-147): con posizioni eToro aperte il digest apre con
conto, posizioni, trimestrali vicine ed eventi di oggi; senza, resta quello."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as NS

from app.models import EtoroConto, EtoroPosizione, EtoroStrumento, OhlcvDaily, Stock
from app.services import calendar_service, notifier_service
from app.services import stock_fundamentals_service as sfs

OGGI = date(2026, 11, 16)


def _posizioni(db):
    s = Stock(ticker="SOXL", exchange="NYSE", name="Direxion", country="US")
    db.add(s)
    db.flush()
    for i in range(30):
        c = 100.0
        db.add(OhlcvDaily(stock_id=s.id, date=OGGI - timedelta(days=30 - i), open=c,
                          high=c + 1, low=c - 1, close=c, volume=1e6))
    adesso = datetime.now(UTC)
    db.add(EtoroStrumento(instrument_id=1, simbolo="SOXL", stock_id=s.id, abbinamento="auto",
                          aggiornato_il=adesso))
    db.flush()
    for pid, stop in ((1, 90.0), (2, 95.0)):
        db.add(EtoroPosizione(position_id=pid, instrument_id=1, lato="long", leva=5,
                              regolamento="cfd", aperta_il=adesso, prezzo_apertura=100.0,
                              unita=1, importo_usd=100.0, stop=stop, prezzo_corrente=100.0,
                              vista_il=adesso))
    db.add(EtoroConto(id=1, aggiornato_il=adesso, valuta="USD", valore_totale=2030.0,
                      pnl_aperto=457.0))
    db.commit()


def test_il_brief_dice_posizioni_stop_piu_vicino_trimestrale_e_oggi(db, monkeypatch):
    _posizioni(db)
    monkeypatch.setattr(sfs, "trimestrali_cached", lambda t: ([], OGGI + timedelta(days=3)))
    monkeypatch.setattr(calendar_service, "get_events",
                        lambda *a, **k: [NS(label="CPI m/m", release_time="14:30")])
    righe = notifier_service._righe_brief(db, OGGI)
    testo = "\n".join(righe)
    assert "Conto 2,030 USD, P/L aperto +457 USD" in testo
    # Due posizioni sullo stesso titolo: una riga, lo stop piu' vicino (95 -> 5%).
    assert "<b>SOXL</b> long ×5 (2 posizioni)" in testo and "stop piu' vicino a 5.0%" in testo
    assert "ATR" in testo
    assert "SOXL: trimestrale fra 3 giorni" in testo
    assert "CPI m/m (14:30)" in testo


def test_senza_posizioni_il_brief_e_vuoto(db):
    assert notifier_service._righe_brief(db, OGGI) == []


def test_un_calendario_rotto_non_ferma_il_brief(db, monkeypatch):
    _posizioni(db)
    monkeypatch.setattr(sfs, "trimestrali_cached", lambda t: ([], None))
    monkeypatch.setattr(calendar_service, "get_events",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giu'")))
    assert any("SOXL" in r for r in notifier_service._righe_brief(db, OGGI))


def test_il_brief_parte_anche_senza_segnali_e_riassume_il_resto(db, monkeypatch):
    testi = []
    monkeypatch.setattr(notifier_service, "_telegram_enabled", lambda: True)
    monkeypatch.setattr(notifier_service, "_send_telegram", lambda t, what: testi.append(t) or True)
    monkeypatch.setattr(notifier_service, "_righe_brief", lambda db, oggi: ["<b>Le tue posizioni</b>"])
    r = notifier_service.send_daily_digest(db)
    assert r.sent and "Brief del" in testi[0] and "Digest del" not in testi[0]

    testo = notifier_service.build_digest_message(db, [], [], ["<b>Le tue posizioni</b>"])
    assert "/positions" in testo
