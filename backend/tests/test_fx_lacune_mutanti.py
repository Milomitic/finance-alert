"""Le lacune di `fx_service` che la sonda di mutazione ha trovato.

⚠️ Ognuno di questi test uccide un mutante SOPRAVVISSUTO: una riga che i test
esistenti ESEGUIVANO senza verificarne la correttezza. E' la differenza che la
copertura non sa misurare — `test_fx_honesty.py` passa da quelle righe e non
noterebbe se cambiassero.

Il modulo merita questa attenzione piu' di altri: CLAUDE.md registra che un
errore di conversione qui ha gia' fatto passare **75 titoli per mega-cap** che
non lo erano (7270.T a 10,9 mld di dollari, 033780.KS a 14,4). Un tasso
sbagliato non produce un errore, produce una classifica plausibile.

⚠️ NON si testano i valori della tabella `FX_RATES_FALLBACK` uno per uno. Sono
una tabella di riferimento che va aggiornata ogni pochi mesi, e pinnare i numeri
esatti renderebbe rosso ogni aggiornamento legittimo — un cancello che punisce
la manutenzione viene spento. Si testa invece l'ORDINE DI GRANDEZZA su poche
ancore, che e' cio' che un refuso rompe e un aggiornamento no.
"""

import pytest

from app.services import fx_service


def _falsifica_yfinance(monkeypatch, chiusure):
    """Sostituisce `yfinance.Ticker` sul PACCHETTO, non sul modulo.

    ⚠️ `fx_service` fa `import yfinance as yf` DENTRO `_fetch_live_rate`, quindi
    `fx_service.yf` non esiste come attributo di modulo e `monkeypatch.setattr`
    su di esso solleva `AttributeError`. Un import locale si sostituisce alla
    sorgente: il pacchetto.

    `chiusure=None` simula una risposta assente, `[]` una vuota: sono due modi
    diversi in cui yfinance dice «non ho niente» e il codice li tratta insieme.
    """
    import pandas as pd
    import yfinance

    class _Ticker:
        def __init__(self, _simbolo):
            pass

        def history(self, period):  # noqa: A002
            if chiusure is None:
                return None
            return pd.DataFrame({"Close": chiusure})

    monkeypatch.setattr(yfinance, "Ticker", _Ticker)


@pytest.fixture(autouse=True)
def _cache_pulita():
    """La cache e' di modulo e sopravvive ai test: senza questo, il primo test
    che la popola decide l'esito dei successivi."""
    fx_service.clear_cache()
    yield
    fx_service.clear_cache()


class TestValutaIgnota:
    """⚠️ Mutanti su `to_usd_cached` e `rate_for`, riga 191 e 205: `or` -> `and`.

    Entrambe le funzioni aprono con `if x is None or y is None or not
    y.strip()`. Col mutante diventa `and`, cioe' la guardia scatta solo se
    TUTTE le condizioni valgono insieme: un importo valido con valuta `None`
    passerebbe oltre e finirebbe in `.strip()` su `None`.

    La docstring del modulo dice gia' la regola — «una valuta ignota resta
    ignota: assumere USD perche' il campo e' vuoto e' un'ipotesi presentata
    come un fatto» — e nessun test la esercitava su questi due percorsi.
    """

    @pytest.mark.parametrize("valuta", [None, "", "   "])
    def test_to_usd_cached_senza_valuta_torna_None(self, valuta):
        assert fx_service.to_usd_cached(100.0, valuta) is None

    def test_to_usd_cached_senza_importo_torna_None(self):
        assert fx_service.to_usd_cached(None, "EUR") is None

    @pytest.mark.parametrize("valuta", [None, "", "   "])
    def test_rate_for_senza_valuta_torna_None(self, valuta):
        assert fx_service.rate_for(valuta) is None

    def test_ma_una_valuta_VERA_converte(self):
        """Il controllo negativo dei quattro sopra: senza, una funzione che
        restituisce sempre `None` li passerebbe tutti."""
        assert fx_service.to_usd_cached(100.0, "USD") == pytest.approx(100.0)
        assert fx_service.rate_for("USD") == pytest.approx(1.0)


class TestTassoNonPositivo:
    """⚠️ Mutante su riga 105: `if last_close <= 0` -> `< 0`.

    Un tasso di ESATTAMENTE zero passerebbe la guardia e verrebbe messo in
    cache. Da li' ogni conversione di quella valuta vale 0, e uno zero non
    somiglia a un errore: somiglia a un'azienda senza capitalizzazione.

    ⚠️ E' la distinzione fra assenza e zero che questo repo applica ovunque,
    vista dal lato della SORGENTE invece che da quello della visualizzazione.
    """

    @pytest.mark.parametrize("chiusura", [0.0, -1.0])
    def test_zero_e_negativi_vengono_rifiutati(self, monkeypatch, chiusura):
        """⚠️ Il guardiano vive DENTRO `_fetch_live_rate`, non in `_get_rate`.

        La prima stesura di questo test sostituiva `_fetch_live_rate` e
        asseriva che `_get_rate` ricadesse sulla tabella: falliva, perche'
        `_get_rate` si fida di cio' che riceve e lo zero passava. Sostituire la
        funzione che CONTIENE la guardia non puo' provare che la guardia
        esista — va sostituito cio' che sta SOTTO di essa.
        """
        _falsifica_yfinance(monkeypatch, [1.05, chiusura])
        assert fx_service._fetch_live_rate("EUR") is None
        # E il chiamante ricade sulla tabella invece di convertire a zero.
        assert fx_service._get_rate("EUR") == pytest.approx(
            fx_service.FX_RATES_FALLBACK["EUR"]
        )

    def test_un_tasso_positivo_dal_vivo_viene_usato(self, monkeypatch):
        """Controllo negativo: se `_get_rate` ignorasse sempre il valore vivo,
        il test sopra passerebbe per la ragione sbagliata."""
        monkeypatch.setattr(fx_service, "_fetch_live_rate", lambda cur: 1.234)
        assert fx_service._get_rate("EUR") == pytest.approx(1.234)


class TestScadenzaDellaCache:
    """⚠️ Due mutanti su riga 134, e uno e' grave.

    `if entry is not None and (now - entry[0]) < _TTL_SECONDS`.

    - `entry[0]` -> `entry[1]` legge il TASSO al posto dell'istante: la
      scadenza diventa un confronto fra un'ora e un cambio, cioe' rumore. Per
      JPY (~0.0067) la voce risulterebbe eternamente fresca; per una valuta con
      tasso alto, eternamente scaduta.
    - `<` -> `<=` e' il bordo, che nessun test toccava.

    Il difetto che questo protegge non e' un errore a schermo: e' un tasso
    vecchio di giorni presentato come fresco, che e' precisamente il modo in cui
    75 titoli sono diventati mega-cap.
    """

    def test_una_voce_fresca_NON_richiama_la_rete(self, monkeypatch):
        chiamate: list[str] = []
        monkeypatch.setattr(fx_service, "_fetch_live_rate",
                            lambda cur: chiamate.append(cur) or 2.0)
        monkeypatch.setattr(fx_service, "_now", lambda: 1000.0)

        assert fx_service._get_rate("EUR") == pytest.approx(2.0)
        assert len(chiamate) == 1
        # Stesso istante: la cache deve rispondere da sola.
        assert fx_service._get_rate("EUR") == pytest.approx(2.0)
        assert len(chiamate) == 1, "la seconda lettura ha richiamato la rete"

    def test_oltre_il_TTL_la_rete_viene_richiamata(self, monkeypatch):
        chiamate: list[float] = []
        tempo = {"t": 1000.0}
        monkeypatch.setattr(fx_service, "_now", lambda: tempo["t"])

        def _finto(cur: str):
            chiamate.append(tempo["t"])
            return 2.0 if tempo["t"] < 2000 else 3.0

        monkeypatch.setattr(fx_service, "_fetch_live_rate", _finto)
        assert fx_service._get_rate("EUR") == pytest.approx(2.0)

        # ⚠️ Il BORDO: esattamente a TTL la voce e' gia' scaduta, perche' il
        # confronto e' `< _TTL_SECONDS` e non `<=`. E' il mutante che
        # sopravviveva, ed e' il fuori-di-uno piu' comune che esista.
        tempo["t"] = 1000.0 + fx_service._TTL_SECONDS
        assert fx_service._get_rate("EUR") == pytest.approx(3.0)
        assert len(chiamate) == 2

    def test_e_un_istante_PRIMA_del_TTL_e_ancora_fresca(self, monkeypatch):
        """L'altra meta' del bordo: senza questa, `<` e `<=` restano
        indistinguibili e il test sopra non proverebbe nulla sul confronto."""
        chiamate: list[str] = []
        tempo = {"t": 1000.0}
        monkeypatch.setattr(fx_service, "_now", lambda: tempo["t"])
        monkeypatch.setattr(fx_service, "_fetch_live_rate",
                            lambda cur: chiamate.append(cur) or 2.0)

        fx_service._get_rate("EUR")
        tempo["t"] = 1000.0 + fx_service._TTL_SECONDS - 1
        fx_service._get_rate("EUR")
        assert len(chiamate) == 1, "una voce ancora fresca ha richiamato la rete"


class TestFetchVivoSenzaDati:
    """⚠️ Mutante su riga 100: `if hist is None or hist.empty` -> `and`.

    Col mutante, una risposta vuota ma non-`None` prosegue fino a
    `hist["Close"].iloc[-1]` su un frame vuoto. Sono due modi diversi in cui
    yfinance dice «non ho niente» e vanno trattati uguale.
    """

    @pytest.mark.parametrize("risposta", ["none", "vuoto"])
    def test_entrambe_le_forme_di_vuoto_tornano_None(self, monkeypatch, risposta):
        _falsifica_yfinance(monkeypatch, None if risposta == "none" else [])
        assert fx_service._fetch_live_rate("EUR") is None

    def test_con_dati_veri_torna_l_ULTIMO_close(self, monkeypatch):
        """⚠️ Uccide anche il mutante di riga 104 (`iloc[-1]` -> `iloc[-2]`).

        Un tasso vecchio di un giorno non somiglia a un difetto: somiglia a un
        tasso. Le due chiusure sono deliberatamente diverse, o il mutante
        sopravvivrebbe anche a questo test."""
        _falsifica_yfinance(monkeypatch, [1.05, 1.10, 1.20])
        assert fx_service._fetch_live_rate("EUR") == pytest.approx(1.20)


class TestAliasPence:
    """⚠️ Mutante su riga 179: `if maggiore and maggiore in out` -> `or`.

    Col mutante, un alias la cui valuta maggiore NON e' nella mappa finirebbe
    comunque in `out[alias] = out[maggiore]`, cioe' un KeyError — oppure, con
    `maggiore` a `None`, un alias mappato su una chiave inesistente.

    Gli alias contano: yfinance restituisce `GBp` per le azioni di Londra, e
    CLAUDE.md registra sei righe rimaste con quell'etichetta grezza.
    """

    @pytest.mark.parametrize("alias", ["GBp", "GBX", "gbp", "gbx"])
    def test_ogni_alias_pence_prende_il_tasso_della_sterlina(self, alias):
        tassi = fx_service.cached_rates()
        assert alias in tassi, f"{alias} non e' fra i tassi in cache"
        assert tassi[alias] == pytest.approx(tassi["GBP"])

    def test_e_USD_vale_esattamente_uno(self):
        """Non e' pignoleria: ogni conversione passa di qui, e un USD diverso
        da 1.0 sposterebbe OGNI importo dell'app insieme."""
        assert fx_service.cached_rates()["USD"] == 1.0


class TestOrdineDiGrandezzaDeiRipieghi:
    """⚠️ Uccide i mutanti sulle costanti `1 / X` della tabella di ripiego.

    Raddoppiare il numeratore di `1 / 150.0` da' 0,0133 invece di 0,0067: un
    errore del 100% su un cambio reale, e un valore ancora perfettamente
    plausibile a occhio.

    ⚠️ Si asserisce una BANDA larga, non il numero. Le bande sono scelte per
    sopravvivere ad anni di deriva valutaria e per rompersi su un fattore due,
    che e' la differenza fra un aggiornamento legittimo e un refuso. Pinnare i
    valori esatti renderebbe rosso ogni manutenzione — e un cancello che
    punisce la manutenzione viene spento.
    """

    #: valuta -> (minimo, massimo) in USD per unita'. Ancore stabili da anni.
    BANDE = {
        "JPY": (0.004, 0.011),
        "KRW": (0.0004, 0.0012),
        "HKD": (0.10, 0.15),
        "CNY": (0.10, 0.18),
        "INR": (0.008, 0.016),
        "HUF": (0.0018, 0.0040),
        "IDR": (0.00004, 0.00010),
        "TWD": (0.025, 0.040),
        "THB": (0.021, 0.035),
        "PHP": (0.012, 0.023),
    }

    @pytest.mark.parametrize("valuta", sorted(BANDE))
    def test_il_ripiego_e_nell_ordine_di_grandezza_giusto(self, valuta):
        minimo, massimo = self.BANDE[valuta]
        tasso = fx_service.FX_RATES_FALLBACK[valuta]
        assert minimo <= tasso <= massimo, (
            f"{valuta} vale {tasso} USD, fuori dalla banda {minimo}-{massimo}. "
            "O il cambio si e' mosso di piu' di quanto la banda preveda — e "
            "allora si allarga QUI, dopo aver guardato il cambio vero — oppure "
            "e' un refuso, ed e' esattamente cio' che questo test cerca."
        )

    def test_ogni_tasso_e_positivo(self):
        """Uno zero o un negativo in tabella farebbe valere zero, o negativo,
        ogni capitalizzazione di quella valuta."""
        fuori = {c: r for c, r in fx_service.FX_RATES_FALLBACK.items() if r <= 0}
        assert not fuori, f"tassi non positivi: {fuori}"

    def test_le_bande_coprono_valute_che_esistono_davvero(self):
        """Il pavimento: se qualcuno rinominasse le chiavi, i test sopra
        fallirebbero con KeyError invece di passare — ma se qualcuno SVUOTASSE
        BANDE, passerebbero tutti senza verificare niente."""
        assert len(self.BANDE) >= 8
        assert set(self.BANDE) <= set(fx_service.FX_RATES_FALLBACK)
