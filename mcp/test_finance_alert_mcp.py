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
        assert (percorso, parametri) == ("/api/markets/^IXIC/detail",
                                         {"range": "1d", "storia": "completa"})
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


# ─── FA-159 ────────────────────────────────────────────────────────────────

def test_prestazioni_riassunte_e_dettaglio_su_richiesta(monkeypatch) -> None:
    cella = {"n": 100, "effective_n": 4, "horizon_days": 21, "mkt_neutral_hit_rate": 52.0,
             "skill_ci_low": 30.0, "skill_ci_high": 70.0, "skill_verdict": "inconclusive",
             "abs_hit_rate": 55.0, "avg_fwd_return": 0.4, "rumore": "x" * 1000}
    risposta = {"meta": {"total_rows": 100}, "overall": cella,
                "detectors": [{"detector": "sr_flip", "total": cella, "by_regime": [cella] * 5}]}
    monkeypatch.setattr(srv, "chiama", lambda p, q=None: risposta)
    r = srv.prestazioni_detector()
    assert r["detector"] == [{"detector": "sr_flip", **srv.riassumi_cella(cella)}]
    assert r["detector"][0]["effective_n"] == 4 and r["detector"][0]["giorni"] is None
    assert "rumore" not in str(r)
    assert srv.prestazioni_detector("sr_flip")["by_regime"]
    assert srv.prestazioni_detector("nessuno")["disponibili"] == ["sr_flip"]


def test_lo_screener_rifiuta_filtri_sconosciuti_e_riassume_le_righe(monkeypatch) -> None:
    chiamate = []

    def finto(p, q=None):
        chiamate.append((p, q))
        return {"total": 1, "items": [{"stock": {"ticker": "AAPL", "name": "Apple", "sector": "Tech"},
                                       "score": {"composite": 70}, "technical": {"composite": 60, "posture": "Forte"},
                                       "metrics": {"last_close": 200.0, "change_pct": 1.2, "rsi14": 55}}]}
    monkeypatch.setattr(srv, "chiama", finto)
    assert "accettati" in srv.screener({"settore": "x"})
    r = srv.screener({"min_score": 60, "sector": ["Technology"]}, limite=500)
    assert r["titoli"][0] == {"ticker": "AAPL", "nome": "Apple", "settore": "Tech", "qualita": 70,
                              "tecnico": 60, "postura": "Forte", "prezzo": 200.0,
                              "variazione_pct": 1.2, "rsi": 55}
    assert chiamate[-1] == ("/api/stocks", {"min_score": 60, "sector": ["Technology"], "limit": 100})


def test_primo_passaggio_rischio_e_confronti_chiamano_le_rotte_giuste(monkeypatch) -> None:
    chiamate = []

    def finto(p, q=None):
        chiamate.append((p, q))
        if p.endswith("variazione-punteggio"):
            raise srv.ErroreApp("404")
        return {"ok": True}
    monkeypatch.setattr(srv, "chiama", finto)
    srv.primo_passaggio(" soxl ", 0.05, 0.1, lato="short", sedute=10)
    assert chiamate[-1] == ("/api/etoro/primo-passaggio", {"simbolo": "SOXL", "stop_pct": 0.05,
                                                           "target_pct": 0.1, "lato": "short", "sedute": 10})
    srv.rischio_posizioni()
    assert chiamate[-1][0] == "/api/etoro/rischio"
    c = srv.confronti("aapl")
    assert c["pari"] == {"ok": True} and "404" in c["variazione_punteggio"]


def test_studio_sceglie_la_rotta_e_limita_l_orizzonte_dell_evento(monkeypatch) -> None:
    chiamate = []
    monkeypatch.setattr(srv, "chiama", lambda p, q=None: chiamate.append((p, q)) or {})
    srv.studio("evento", " aapl ", orizzonte=30)
    assert chiamate[-1] == ("/api/studio/evento", {"simbolo": "AAPL", "tipo": "trimestrali",
                                                   "serie_macro": None, "orizzonte": 10})
    srv.studio("stagionalita", "^GSPC")
    assert chiamate[-1][0] == "/api/studio/stagionalita"
    srv.studio("dopo_movimento", "SOXL", soglia_pct=-20)
    assert chiamate[-1][1]["soglia_pct"] == -20
    assert "modelli" in srv.studio("boh", "X")
