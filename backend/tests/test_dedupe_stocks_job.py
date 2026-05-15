"""Verifica che il wrapper APScheduler chiami dedupe() in modalità non-dry-run e
loggi il risultato. Non verifica la logica di dedup vera (già coperta da
test_dedupe_stocks.py); verifica solo l'orchestrazione."""
from unittest.mock import patch

from app.scheduler.jobs.dedupe_stocks_job import run_dedupe_stocks


def test_run_dedupe_stocks_invokes_dedupe_in_commit_mode():
    with patch("app.scheduler.jobs.dedupe_stocks_job.dedupe", return_value=3) as m:
        run_dedupe_stocks()
        m.assert_called_once_with(dry_run=False)


def test_run_dedupe_stocks_swallows_exceptions_and_logs():
    """Un fallimento del job non deve crashare lo scheduler."""
    with patch(
        "app.scheduler.jobs.dedupe_stocks_job.dedupe",
        side_effect=RuntimeError("boom"),
    ):
        # Non deve sollevare
        run_dedupe_stocks()
