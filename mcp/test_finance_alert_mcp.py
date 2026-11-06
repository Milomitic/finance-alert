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
