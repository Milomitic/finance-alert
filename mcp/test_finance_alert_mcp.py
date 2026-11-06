import asyncio

import httpx
import pytest

import finance_alert_mcp as srv


def _client(gestore) -> httpx.Client:
    return httpx.Client(base_url="https://app.test", transport=httpx.MockTransport(gestore))


def test_chiama_manda_solo_get_e_toglie_i_parametri_vuoti() -> None:
    viste = []

    def gestore(req: httpx.Request) -> httpx.Response:
        viste.append(req)
        return httpx.Response(200, json={"ok": True})

    assert srv.chiama("/api/x", {"a": 1, "b": None}, client=_client(gestore)) == {"ok": True}
    assert viste[0].method == "GET"
    assert dict(viste[0].url.params) == {"a": "1"}


@pytest.mark.parametrize(("codice", "frase"), [(401, "Token rifiutato"), (404, "Non trovato"), (500, "ha risposto 500")])
def test_gli_errori_diventano_frasi(codice: int, frase: str) -> None:
    with pytest.raises(srv.ErroreApp, match=frase):
        srv.chiama("/api/x", client=_client(lambda r: httpx.Response(codice, text="no")))


def test_un_tempo_scaduto_nomina_l_allowlist() -> None:
    def gestore(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("lento", request=req)

    with pytest.raises(srv.ErroreApp, match="allowlist"):
        srv.chiama("/api/x", client=_client(gestore))


def test_il_token_mancante_lo_dice(tmp_path) -> None:
    with pytest.raises(srv.ErroreApp, match="Token non trovato"):
        srv.leggi_token(tmp_path / "manca")
    (tmp_path / "vuoto").write_text("  \n", encoding="utf-8")
    with pytest.raises(srv.ErroreApp, match="vuoto"):
        srv.leggi_token(tmp_path / "vuoto")


def test_sfoltisci_toglie_le_serie_e_dichiara_i_tagli() -> None:
    x = srv.sfoltisci({"ohlcv": [1, 2], "nome": "A", "lista": list(range(30))})
    assert "ohlcv" not in x
    assert x["lista"][:3] == [0, 1, 2]
    assert x["lista"][-1] == "... altri 5 elementi non mostrati"


def test_il_segnale_si_legge_all_emissione_non_all_ultima_revisione() -> None:
    a = {"id": 7, "rule_kind": "signal:candle_reversal", "ticker": "AAPL", "trigger_price": 120.0,
         "triggered_at": "2026-11-05T23:30:00", "signal_date": "2026-11-05", "currency": "USD",
         "archived_at": None,
         "snapshot": {"tone": "bull", "strength": 90, "first_strength": 71, "first_price": 100.0,
                      "first_emitted_at": "2026-11-02T23:30:00", "horizon": "short"}}
    r = srv.riassumi_segnale(a)
    assert r["detector"] == "candle_reversal"
    assert (r["prezzo_ingresso"], r["forza"], r["comparso_il"]) == (100.0, 71, "2026-11-02")


def test_ogni_strumento_e_dichiarato_di_sola_lettura() -> None:
    strumenti = asyncio.run(srv.mcp.list_tools())
    assert len(strumenti) >= 10
    for s in strumenti:
        assert s.annotations is not None and s.annotations.read_only_hint, s.name
        # E in rete esce col nome del protocollo, che e' quello che il client legge.
        assert s.annotations.model_dump(by_alias=True, exclude_none=True)["readOnlyHint"] is True
        assert s.annotations.destructive_hint is False


def _barra(d: str, c: float) -> dict:
    return {"date": d, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 10}


def test_storico_di_un_titolo_viene_dal_catalogo_con_l_intervallo(monkeypatch) -> None:
    chiamate = []

    def finto(percorso, parametri=None, **kw):
        chiamate.append((percorso, parametri))
        return [_barra("2020-01-02", 10.123456), _barra("2020-01-03", 11)]

    monkeypatch.setattr(srv, "chiama", finto)
    r = srv.leggi_storico("aapl", dal="2020-01-01", al="2020-12-31")
    assert chiamate == [("/api/stocks/AAPL/ohlcv", {"dal": "2020-01-01", "al": "2020-12-31"})]
    assert r["fonte"].startswith("catalogo")
    assert (r["barre"], r["dal"], r["al"]) == (2, "2020-01-02", "2020-01-03")
    assert r["colonne"] == ["data", "apertura", "massimo", "minimo", "chiusura", "volume"]
    assert r["righe"][0] == ["2020-01-02", 10.1235, 11.1235, 9.1235, 10.1235, 10]


def test_storico_di_un_indice_ripiega_sui_mercati_e_taglia_alle_date(monkeypatch) -> None:
    """Il catalogo risponde vuoto per ^IXIC; i mercati rendono TUTTA la
    storia, quindi l'intervallo si applica nel server MCP."""
    def finto(percorso, parametri=None, **kw):
        if percorso.startswith("/api/stocks/"):
            return []
        assert (percorso, parametri) == ("/api/markets/^IXIC/detail", {"range": "1d"})
        return {"bars": [_barra("1999-12-31", 1), _barra("2016-01-04", 2),
                         _barra("2016-01-05", 3), _barra("2026-01-02", 4)]}

    monkeypatch.setattr(srv, "chiama", finto)
    r = srv.leggi_storico("^ixic", dal="2016-01-01", al="2025-12-31", solo_chiusure=True)
    assert r["fonte"].startswith("mercati")
    assert r["colonne"] == ["data", "chiusura"]
    assert r["righe"] == [["2016-01-04", 2.0], ["2016-01-05", 3.0]]


def test_storico_senza_dal_copre_dieci_anni_piu_il_riscaldamento(monkeypatch) -> None:
    visti = {}

    def finto(percorso, parametri=None, **kw):
        visti.update(parametri or {})
        return [_barra("2020-01-02", 1)]

    monkeypatch.setattr(srv, "chiama", finto)
    srv.leggi_storico("AAPL")
    oggi = srv.date.today()
    dieci_anni_fa = srv.date(oggi.year - 10, oggi.month, 1).isoformat()
    assert visti["dal"] < dieci_anni_fa


def test_storico_di_un_simbolo_sconosciuto_elenca_i_mercati(monkeypatch) -> None:
    def finto(percorso, parametri=None, **kw):
        if percorso.startswith("/api/stocks/"):
            return []
        raise srv.ErroreApp("Non trovato")

    monkeypatch.setattr(srv, "chiama", finto)
    with pytest.raises(srv.ErroreApp, match=r"\^IXIC"):
        srv.leggi_storico("XYZ")
