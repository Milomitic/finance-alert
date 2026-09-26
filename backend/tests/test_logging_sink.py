"""Verify that loguru's logger.info/warning/error writes into the
in-memory ring buffer via the configured sink."""
from loguru import logger

from app.core.log_buffer import _INSTANCE as log_buffer
from app.core.logging import configure_logging


def test_logger_warning_lands_in_buffer():
    configure_logging()
    before = len(log_buffer.get_snapshot(limit=0))
    logger.warning("test-marker-from-test-logging-sink-warning")
    snap = log_buffer.get_snapshot(limit=0)
    matches = [r for r in snap if "test-marker-from-test-logging-sink-warning" in r["message"]]
    assert len(matches) == 1, f"expected 1 match, got {len(matches)}; buffer grew by {len(snap)-before}"
    rec = matches[0]
    assert rec["level"] == "WARNING"
    assert isinstance(rec["ts"], float)
    assert "module" in rec
    assert "line" in rec


def test_logger_error_includes_exception_traceback():
    configure_logging()
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("test-marker-exception-line-xyz")
    snap = log_buffer.get_snapshot(limit=0)
    matches = [r for r in snap if "test-marker-exception-line-xyz" in r["message"]]
    assert matches
    rec = matches[-1]
    assert rec["exception"] is not None
    assert "ValueError" in rec["exception"]
    assert "boom" in rec["exception"]


def _invia(credenziale: str) -> None:
    raise ValueError("richiesta rifiutata, senza dati")


def _fallisce_con_un_segreto_in_mano():
    # ⚠️ La credenziale sta SULLA RIGA che fallisce, come in una chiamata HTTP
    # che riceve il token: `diagnose` annota i valori dei nomi che compaiono
    # nella riga del traceback, non ogni variabile del frame. Con la chiave
    # definita e poi non usata sulla riga dell'errore il test passava anche
    # col difetto dentro — vero di niente.
    chiave_api = "sk-segreto-9f3a-non-deve-uscire"
    _invia(chiave_api)


def test_il_traceback_non_scrive_i_valori_delle_variabili(capsys):
    """⚠️ FA-102 (2026-09-26). `diagnose` di loguru e' attivo di default e
    stampa, sotto ogni riga del traceback, il VALORE di ogni variabile del
    frame. Il traceback del rinnovo catalogo di quella notte lo faceva, e
    un'eccezione in una funzione che maneggia un token lo scriverebbe in chiaro
    su stdout (quindi in Loki) e nel file su disco.

    Il pavimento conta quanto l'asserzione: il traceback DEVE esserci (tipo
    d'eccezione e marcatore), altrimenti «il segreto non compare» sarebbe vero
    anche di un log che non ha scritto niente."""
    from pathlib import Path

    configure_logging()
    registro = Path("./data/logs/app.log")
    # Il file si ACCUMULA fra un'esecuzione e l'altra: si legge solo cio' che
    # questo test ci scrive, altrimenti un giro precedente col difetto dentro
    # lo farebbe fallire per sempre (e uno senza lo farebbe passare comunque).
    partenza = registro.stat().st_size if registro.exists() else 0
    try:
        _fallisce_con_un_segreto_in_mano()
    except ValueError:
        logger.exception("marcatore-fa102-traceback")

    stdout = capsys.readouterr().out
    assert "marcatore-fa102-traceback" in stdout and "ValueError" in stdout
    assert "sk-segreto-9f3a" not in stdout, "il traceback su stdout espone una variabile locale"

    coda = registro.read_bytes()[partenza:].decode("utf-8", errors="replace")
    assert "marcatore-fa102-traceback" in coda
    assert "sk-segreto-9f3a" not in coda, "il traceback nel file espone una variabile locale"
