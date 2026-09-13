"""I rami di RIFIUTO della sicurezza, che nessun test percorreva.

⚠️ Trovati dalla sonda di mutazione, non a lettura: `app/core/security.py`
aveva NOVE mutanti e i test ne uccidevano ZERO. Non significa che il modulo
fosse sbagliato — significa che nessuna delle sue difese era verificata, e una
difesa non verificata e' indistinguibile da una assente finche' non serve.

I due mutanti che contano, e perche':

1. `verify_password`, `except ValueError: return False` -> `return True`.
   `bcrypt.checkpw` solleva `ValueError` su un hash MALFORMATO — colonna
   troncata, riga scritta da uno schema diverso, migrazione andata male. Col
   mutante quel ramo autentica CHIUNQUE. I test esistenti provavano solo la
   coppia giusta e quella sbagliata, cioe' due hash validi.

2. La validazione dello username estratto dal token,
   `isinstance(username, str) and 0 < len(username) <= 64` -> `or`.
   Con `or`, una stringa vuota o da duecento caratteri viene ACCETTATA (il
   primo termine corto-circuita), e un valore non-stringa fa esplodere `len()`
   invece di essere respinto: un rifiuto pulito diventa un 500.

⚠️ Questi test costruiscono token con payload anomali usando il serializzatore
VERO, non stringhe a caso: un token non firmato verrebbe respinto prima, da
`BadSignature`, e il test passerebbe senza mai raggiungere la riga che deve
verificare — la forma «un test puo' essere vero di niente» che CLAUDE.md
registra piu' volte.
"""

import pytest

from app.core import security

# ─── 1. verify_password sui hash che non sono hash ────────────────────────

@pytest.mark.parametrize("guasto", [
    "",                      # colonna vuota
    "non-un-hash",           # testo qualunque
    "$2b$12$troppo-corto",   # prefisso giusto, resto invalido
])
def test_un_hash_malformato_NON_autentica(guasto: str) -> None:
    """Il ramo che il mutante `return True` trasformava in un lasciapassare."""
    assert security.verify_password("qualsiasi", guasto) is False


def test_il_controllo_negativo_un_hash_VALIDO_funziona_ancora() -> None:
    """⚠️ Senza questo, «nessun hash autentica» sarebbe vero anche di una
    funzione rotta che rifiuta sempre — e i tre test sopra passerebbero in
    pieno."""
    h = security.hash_password("segreto")
    assert security.verify_password("segreto", h) is True
    assert security.verify_password("sbagliata", h) is False


# ─── 2. lo username dentro il token ───────────────────────────────────────

def _token_con(payload: object) -> str:
    """Un token FIRMATO che porta un payload arbitrario.

    ⚠️ Passa dal serializzatore vero: cosi' la firma e' valida e la verifica
    arriva davvero al controllo sullo username. Con una stringa inventata si
    fermerebbe a `BadSignature` e il test non proverebbe niente."""
    return security._serializer().dumps(payload)


def test_uno_username_vuoto_e_respinto() -> None:
    """`0 < len(username)`: col mutante `or` la stringa vuota passava."""
    assert security.read_session_token(_token_con({"u": "", "jti": "x"})) is None


def test_uno_username_lunghissimo_e_respinto() -> None:
    """`len(username) <= 64`. Il tetto esiste perche' quel valore finisce in
    una query: senza, un token valido puo' portarci dentro qualunque cosa."""
    assert security.read_session_token(_token_con({"u": "a" * 65, "jti": "x"})) is None


def test_il_bordo_esatto_di_64_e_ACCETTATO() -> None:
    """⚠️ L'altra meta' del confine, e senza di essa un `< 64` al posto di
    `<= 64` passerebbe inosservato: il fuori-di-uno piu' comune che esista."""
    u = "a" * 64
    assert security.read_session_token(_token_con({"u": u, "jti": "x"})) == u


def test_uno_username_di_un_carattere_e_ACCETTATO() -> None:
    """Fissa `0 <` e non `1 <`: il mutante spostava il minimo a due caratteri,
    che nessuna regola del prodotto chiede."""
    assert security.read_session_token(_token_con({"u": "a", "jti": "x"})) == "a"


@pytest.mark.parametrize("valore", [123, None, ["a"], {"x": 1}])
def test_uno_username_non_stringa_e_respinto_SENZA_eccezione(valore: object) -> None:
    """⚠️ Col mutante `or`, `len()` su un intero solleva `TypeError`: un
    rifiuto pulito diventerebbe un 500. Il test verifica il valore E l'assenza
    di eccezione, che qui sono due proprieta' diverse."""
    assert security.read_session_token(_token_con({"u": valore, "jti": "x"})) is None


def test_un_payload_che_non_e_un_oggetto_e_respinto() -> None:
    """`isinstance(data, dict)`: un token firmato puo' portare una lista."""
    assert security.read_session_token(_token_con(["non", "un", "dizionario"])) is None


# ─── 3. I confini che la prima passata aveva lasciato scoperti ────────────
#
# ⚠️ I quattro mutanti qui sotto NON erano fra i due difetti veri: sono righe
# la cui aritmetica non era fissata da niente. Vale la pena chiuderli lo
# stesso, perche' il mutante «+1» e' innocuo e l'errore che la stessa riga
# invita e' uno zero di troppo o di meno — `8640` al posto di `86400` accorcia
# ogni sessione a due ore e mezza senza che nessun test se ne accorga.


def test_una_revoca_scaduta_ESATTAMENTE_ora_viene_rimossa() -> None:
    """`_purge_revoked`: `expires_at <= cutoff`, col bordo INCLUSO.

    Il mutante `<` la terrebbe un istante in piu'. Sbaglia nella direzione
    sicura — un token revocato resta revocato — ma e' il fuori-di-uno che
    questo progetto ha gia' incontrato su `image_provenance`, e il confine va
    deciso da un test invece che da chi legge."""
    prima = dict(security._REVOKED)
    try:
        security._REVOKED.clear()
        security._REVOKED["chiave"] = 1000.0
        security._purge_revoked(now=1000.0)
        assert "chiave" not in security._REVOKED
    finally:
        security._REVOKED.clear()
        security._REVOKED.update(prima)


def test_una_revoca_che_scade_un_istante_dopo_SOPRAVVIVE() -> None:
    """L'altra meta' del confine: senza, `<=` -> `<` non e' l'unico modo di
    passare — lo sarebbe anche una purga che svuota tutto."""
    prima = dict(security._REVOKED)
    try:
        security._REVOKED.clear()
        security._REVOKED["chiave"] = 1000.1
        security._purge_revoked(now=1000.0)
        assert "chiave" in security._REVOKED
    finally:
        security._REVOKED.clear()
        security._REVOKED.update(prima)


def test_la_scadenza_di_una_revoca_e_esattamente_i_giorni_configurati() -> None:
    """`revocation_expiry`: `giorni * 86400`.

    ⚠️ Il secondo membro e' scritto come `24 * 60 * 60` di proposito. Copiare
    `86400` renderebbe l'asserzione una tautologia: cambierebbe insieme alla
    riga che deve sorvegliare, e il test resterebbe verde su qualunque
    valore."""
    from app.core.config import settings

    atteso = settings.session_max_age_days * 24 * 60 * 60
    assert security.revocation_expiry(now=0.0) == atteso


def test_la_durata_predefinita_di_una_sessione_e_i_giorni_configurati() -> None:
    """`read_session_token` senza `max_age_seconds` esplicito.

    Si spia l'argomento passato a `loads` invece di invecchiare un token vero:
    per distinguere 86400 da 86401 servirebbe un token vecchio ESATTAMENTE
    `giorni * 86400 + 1` secondi, cioe' manomettere l'orologio dentro
    itsdangerous. Il valore e' cio' che il mutante cambia, ed e' cio' che il
    test legge."""
    from app.core.config import settings

    visti: dict[str, int] = {}

    class SerializzatoreSpia:
        def loads(self, token: str, max_age: int) -> dict[str, str]:
            visti["max_age"] = max_age
            return {"u": "admin", "jti": "x"}

    originale = security._serializer
    try:
        security._serializer = lambda: SerializzatoreSpia()  # type: ignore[assignment]
        assert security.read_session_token("token-qualunque") == "admin"
    finally:
        security._serializer = originale  # type: ignore[assignment]

    assert visti["max_age"] == settings.session_max_age_days * 24 * 60 * 60


# ─── 4. I due pavimenti che NESSUN mutante puo' chiedere ──────────────────
#
# ⚠️ L'operatore numerico della sonda INCREMENTA soltanto: su un parametro di
# sicurezza puo' quindi esplorare solo la direzione innocua. `rounds=12 -> 13`
# e `token_urlsafe(16) -> 17` sopravvivono perche' sono piu' FORTI
# dell'originale, e stanno in `EQUIVALENTI` per quello. Ma i mutanti che
# contano — `12 -> 11`, `16 -> 15` — la sonda non li genera, e sarebbero
# sopravvissuti nello stesso identico modo. I due test qui sotto non uccidono
# nessun mutante: chiudono il buco che la sonda non sa nominare.


def test_il_costo_di_bcrypt_non_scende_sotto_12() -> None:
    """Il fattore di costo e' scritto nel prefisso dell'hash: `$2b$12$...`.
    E' un PAVIMENTO, non un valore esatto — alzarlo e' una scelta legittima,
    abbassarlo indebolisce ogni password del catalogo in silenzio."""
    costo = int(security.hash_password("una-password").split("$")[2])
    assert costo >= 12


def test_il_nonce_di_sessione_ha_almeno_16_byte_di_entropia() -> None:
    """`secrets.token_urlsafe(16)` rende 22 caratteri base64url.

    Il jti e' cio' che rende ogni accesso revocabile per conto suo: se si
    accorciasse, due sessioni potrebbero collidere e revocarne una ne
    revocherebbe due."""
    jti = security._serializer().loads(security.create_session_token("admin"))["jti"]
    assert len(jti) >= 22
