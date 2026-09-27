"""Niente rilascio durante una scansione (FA-109).

Due meta' che devono restare d'accordo: `/api/health` dice `scan_running`, e
l'hook PreSync (`charts/finance-alert/files/attesa-scansione.sh`) lo legge
prima di un rilascio. Lo script si ESEGUE davvero, con `sh` e `curl`, contro
un server finto — e il server finto, nel test che conta di piu', serve i byte
esatti che l'endpoint produce: una risposta scritta a mano qui renderebbe il
test vero anche con uno script che non legge piu' quella vera.

⚠️ La proprieta' da cui dipende tutto e' che lo script esca SEMPRE 0: un hook
che fallisce ferma il rilascio, e ArgoCD non riprova la stessa revisione.
Ogni caso qui sotto la asserisce.
"""
import http.server
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import scan_lock

CHART = Path(__file__).resolve().parents[2] / "charts" / "finance-alert"
SCRIPT = CHART / "files" / "attesa-scansione.sh"

_STRUMENTI = shutil.which("sh") and shutil.which("curl")
if not _STRUMENTI and os.environ.get("CI"):
    # In CI devono esserci: uno skip li' renderebbe questi test veri di niente.
    raise RuntimeError("sh e curl servono a test_attesa_scansione e in CI mancano")
serve_sh = pytest.mark.skipif(not _STRUMENTI, reason="servono sh e curl")


# ── /api/health ───────────────────────────────────────────────────────────


def _salute() -> bytes:
    return TestClient(app).get("/api/health").content


def test_la_salute_dice_se_c_e_una_scansione() -> None:
    assert b'"scan_running":false' in _salute()
    with scan_lock.scan_slot() as preso:
        assert preso
        assert b'"scan_running":true' in _salute()
    assert b'"scan_running":false' in _salute()


# ── lo script, contro un server finto ─────────────────────────────────────


class _Finto:
    """Un server che serve le risposte in sequenza (l'ultima si ripete) e conta
    le chiamate."""

    def __init__(self, risposte: list[tuple[int, bytes]]) -> None:
        self.risposte, self.chiamate = risposte, 0
        finto = self

        class Gestore(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                stato, corpo = finto.risposte[min(finto.chiamate, len(finto.risposte) - 1)]
                finto.chiamate += 1
                self.send_response(stato)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/health"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def chiudi(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _esegui(url: str, *, attesa_max: int = 30, passo: int = 1) -> tuple[subprocess.CompletedProcess, float]:
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env.update(URL=url, ATTESA_MAX_S=str(attesa_max), PASSO_S=str(passo), NO_PROXY="127.0.0.1,localhost")
    t0 = time.monotonic()
    r = subprocess.run(
        [shutil.which("sh"), str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60,
    )
    return r, time.monotonic() - t0


@pytest.fixture
def finto():
    creati: list[_Finto] = []

    def crea(*risposte: tuple[int, bytes]) -> _Finto:
        f = _Finto(list(risposte))
        creati.append(f)
        return f

    yield crea
    for f in creati:
        f.chiudi()


LIBERO = (200, b'{"status":"ok","scan_running":false}')
OCCUPATO = (200, b'{"status":"ok","scan_running":true}')


@serve_sh
def test_senza_scansione_il_rilascio_passa_subito(finto) -> None:
    f = finto(LIBERO)
    r, durata = _esegui(f.url)
    assert (r.returncode, f.chiamate) == (0, 1)
    assert "nessuna scansione in corso" in r.stdout
    assert durata < 5


@serve_sh
def test_aspetta_la_fine_della_scansione(finto) -> None:
    f = finto(OCCUPATO, OCCUPATO, LIBERO)
    r, durata = _esegui(f.url)
    assert (r.returncode, f.chiamate) == (0, 3)
    # «nessuna scansione in corso» contiene «scansione in corso»: si conta la
    # riga dell'attesa dal suo inizio.
    assert sum(riga.startswith("scansione in corso (") for riga in r.stdout.splitlines()) == 2
    assert "nessuna scansione in corso" in r.stdout
    assert durata >= 2


@serve_sh
def test_oltre_il_tetto_il_rilascio_procede_comunque(finto) -> None:
    f = finto(OCCUPATO)
    r, _ = _esegui(f.url, attesa_max=2)
    assert r.returncode == 0
    assert "procede comunque" in r.stdout
    # Ha aspettato almeno un giro. Il numero esatto dipende da `date +%s`, che
    # ha la risoluzione del secondo: due o tre chiamate sono entrambe giuste.
    assert f.chiamate >= 2


@serve_sh
@pytest.mark.parametrize(
    ("risposta", "messaggio"),
    [
        ((200, b'{"status":"ok","scheduler_running":true,"version":"0.1.0"}'), "versione precedente"),
        ((500, b'{"detail":"boom"}'), "non raggiungibile"),
    ],
    ids=["app-vecchia", "errore-500"],
)
def test_nel_dubbio_il_rilascio_passa(finto, risposta, messaggio) -> None:
    """Il primo rilascio dopo questa modifica trova l'app VECCHIA, che non
    dice `scan_running`: deve passare, non aspettare fino al tetto."""
    f = finto(risposta)
    r, durata = _esegui(f.url)
    assert r.returncode == 0 and messaggio in r.stdout
    assert durata < 10


@serve_sh
def test_un_app_giu_non_ferma_il_rilascio() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    r, _ = _esegui(f"http://127.0.0.1:{porta}/api/health")
    assert r.returncode == 0 and "non raggiungibile" in r.stdout


@serve_sh
def test_lo_script_legge_la_risposta_VERA_dell_endpoint(finto) -> None:
    """Il gemello: il server finto serve i byte che `/api/health` produce.
    Se l'endpoint cambiasse forma — spazi, nome del campo — lo script
    passerebbe al ramo «versione precedente» e il cancello si spegnerebbe
    senza un errore."""
    with scan_lock.scan_slot():
        occupato = _salute()
    libero = _salute()
    f = finto((200, occupato), (200, libero))
    r, _ = _esegui(f.url)
    assert r.returncode == 0
    assert "versione precedente" not in r.stdout
    assert f.chiamate == 2 and "nessuna scansione in corso" in r.stdout


# ── il template ───────────────────────────────────────────────────────────


def test_il_template_e_un_hook_presync_che_non_puo_fermare_il_rilascio() -> None:
    """jsdom non fa layout e pytest non fa helm: si fissa la sorgente. Il
    render vero e' stato provato con `helm template` e un dry-run sul cluster."""
    t = (CHART / "templates" / "hook-attesa-scansione.yaml").read_text(encoding="utf-8")
    # Il commento cita l'etichetta vietata proprio per spiegare perche': si
    # controlla il YAML, non la spiegazione.
    t = t[: t.index("{{- /*")] + t[t.index("*/}}") + 4:]
    assert "argocd.argoproj.io/hook: PreSync" in t
    assert 'Files.Get "files/attesa-scansione.sh"' in t
    # la scadenza del Job sta SOPRA il tetto dello script, non sotto
    assert "activeDeadlineSeconds: {{ add .Values.deployGate.maxWaitSeconds 300 }}" in t
    # nessuna etichetta del selettore dell'app: la lezione della sonda di parita'
    assert "selectorLabels" not in t and "app.kubernetes.io/name" not in t
    assert "deployGate:\n  enabled: true" in (CHART / "values-oci.yaml").read_text(encoding="utf-8")
