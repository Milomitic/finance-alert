"""Infrastructure logs from Loki, beside the app's own log stream.

The health page already shows the app's logs, pushed over SSE from an in-process
ring buffer. Everything ELSE that runs on this node -- ArgoCD, Postgres,
Traefik, cert-manager, Prometheus, Grafana, Alertmanager -- writes to stdout, is
collected into Loki, and has been visible only in Grafana. So diagnosing "the
deploy did not arrive" meant leaving the health page and switching tools.

Three decisions, each of which could have gone the wrong way:

**The source set is CLOSED and the selectors live here.** The endpoint takes a
key, never LogQL. Accepting a query string would turn this into an
authenticated proxy for arbitrary reads of every namespace's logs, which
includes whatever a component happens to print. A key absent from the table is
refused before a request is built.

**Unreachable is not empty.** `query()` returns None when Loki cannot be
reached, and a list -- possibly empty -- when it answers. Those mean opposite
things: "I could not look" versus "I looked and there was nothing". The
identical Prometheus distinction is spelled out in
`infra_health_service._scalar`, and collapsing it here would render a broken
log pipeline as a quiet period.

**An empty window is not a broken source, and Alertmanager proves it.** Its
selector returned nothing over six hours and looked wrong; over thirty days it
returns plenty. The component had simply been silent for nine days, which for
an alert router is the desired state. Loki retains about 23 days here, so the
UI has to name the window it searched — otherwise "quiet" and "misconfigured"
render identically, which is the same confusion this module exists to prevent
one level up.

**The level is a HEURISTIC and callers must know it.** These components share
no log format: ArgoCD and Traefik use logfmt (`level=error`), CNPG emits JSON
(`"level":"info"`), and many lines carry no level at all. `_parse_level`
recognises what it can and falls back to INFO. So it is NOT safe to filter
these records at WARNING and conclude a component is quiet -- an unclassified
error would be hidden. The UI opens infra sources at the lowest threshold for
exactly that reason.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.core.config import settings

_DEFAULT_LOKI = "http://loki.monitoring.svc:3100"

# Matches infra_health_service: this is user-facing, so it must stay bounded.
# Loki is slower than Prometheus on a range query, hence 5s rather than 3s.
_TIMEOUT_S = 5.0

_LEVEL_ORDER = {
    "DEBUG": 10, "INFO": 20, "SUCCESS": 25,
    "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}


@dataclass(frozen=True)
class LokiSource:
    key: str
    label: str
    selector: str
    note: str


# The whole allowlist. Selectors are LogQL stream matchers written here and
# never assembled from a request. `namespace` and `app` are labels the
# collector attaches; both were confirmed present on the live instance before
# this table was written, rather than assumed from a chart's defaults.
_SOURCE_LIST: tuple[LokiSource, ...] = (
    LokiSource(
        "argocd", "ArgoCD",
        '{namespace="argocd"}',
        "sincronizzazioni, differenze rilevate, errori di applicazione",
    ),
    LokiSource(
        "postgres", "PostgreSQL",
        '{namespace="finance-alert", app="postgresql"}',
        "connessioni, checkpoint e la traccia di pgaudit",
    ),
    LokiSource(
        "cnpg", "Operatore Postgres",
        '{namespace="cnpg-system"}',
        "backup, WAL, riconciliazione del cluster",
    ),
    LokiSource(
        "traefik", "Traefik",
        '{namespace="kube-system", app="traefik"}',
        "ingress, TLS, instradamento",
    ),
    LokiSource(
        "cert-manager", "cert-manager",
        '{namespace="cert-manager"}',
        "emissione e rinnovo dei certificati",
    ),
    LokiSource(
        "prometheus", "Prometheus",
        '{namespace="monitoring", app="prometheus"}',
        "raccolta metriche e valutazione delle regole",
    ),
    LokiSource(
        "grafana", "Grafana",
        '{namespace="monitoring", app="grafana"}',
        "accessi e caricamento delle dashboard",
    ),
    LokiSource(
        "alertmanager", "Alertmanager",
        '{namespace="monitoring", app="alertmanager"}',
        "instradamento degli allarmi e consegna su Telegram — spesso silenzioso",
    ),
    LokiSource(
        "loki", "Loki",
        '{namespace="monitoring", app="loki"}',
        "il raccoglitore stesso: se questa finestra e vuota guarda qui",
    ),
)

SOURCES: dict[str, LokiSource] = {s.key: s for s in _SOURCE_LIST}


def sources_payload() -> list[dict]:
    """The picker's options, served from the same table the queries use — so a
    source can never be offered that the backend would then refuse."""
    return [{"key": s.key, "label": s.label, "note": s.note} for s in _SOURCE_LIST]


def _loki_url() -> str:
    return (getattr(settings, "loki_url", None) or _DEFAULT_LOKI).rstrip("/")


# logfmt (`level=error`), bracketed (`[ERROR]`), JSON (`"level":"info"`) and the
# bare word. Ordered widest-LAST so a structured field wins over the same word
# appearing inside a message.
_LEVEL_PATTERNS = (
    re.compile(r'"level"\s*:\s*"(\w+)"', re.I),
    re.compile(r"\blevel=([A-Za-z]+)", re.I),
    re.compile(r"\[(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\]", re.I),
    re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b"),
)

_LEVEL_MAP = {
    "TRACE": "DEBUG", "DEBUG": "DEBUG", "INFO": "INFO", "INFORMATION": "INFO",
    "NOTICE": "INFO", "WARN": "WARNING", "WARNING": "WARNING",
    "ERROR": "ERROR", "ERR": "ERROR", "FATAL": "CRITICAL",
    "CRITICAL": "CRITICAL", "PANIC": "CRITICAL",
}


def _parse_level(line: str) -> str:
    """Best-effort level. INFO when nothing is recognisable — see the module
    docstring for why a caller must not read that as "not an error"."""
    for pattern in _LEVEL_PATTERNS:
        m = pattern.search(line)
        if m:
            mapped = _LEVEL_MAP.get(m.group(1).upper())
            if mapped:
                return mapped
    return "INFO"


def _fetch(selector: str, *, limit: int, minutes: int) -> dict | None:
    """One range query. None on any failure, so the caller can say
    "unreachable" rather than showing an empty list."""
    end = datetime.now(UTC)
    start = end - timedelta(minutes=minutes)
    params = urllib.parse.urlencode({
        "query": selector,
        "limit": str(limit),
        "start": str(int(start.timestamp() * 1_000_000_000)),
        "end": str(int(end.timestamp() * 1_000_000_000)),
        "direction": "backward",
    })
    url = f"{_loki_url()}/loki/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as r:  # noqa: S310
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        # Debug for the same reason as the Prometheus fetch: on a laptop with
        # no cluster this would fire on every page load.
        logger.debug(f"loki query failed: {selector}")
        return None


def _stream_name(labels: dict) -> str:
    """What fills the `module` column. The pod is the useful identity — the
    container name is usually just a duplicate of the app label."""
    for key in ("pod", "container", "app", "job"):
        v = labels.get(key)
        if isinstance(v, str) and v:
            return v
    return "?"


def query(
    source_key: str,
    *,
    level: str | None = None,
    limit: int = 300,
    minutes: int = 60,
) -> list[dict] | None:
    """Records for one source, newest first. None means Loki did not answer.

    `level` is a minimum threshold applied AFTER parsing, in Python: the
    parsing is heuristic, so pushing it down into LogQL would make a guess look
    authoritative while silently dropping every line it failed to classify.
    """
    source = SOURCES.get(source_key)
    if source is None:
        return None

    payload = _fetch(source.selector, limit=limit, minutes=minutes)
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    result = data.get("result")
    if not isinstance(result, list):
        return None

    floor = _LEVEL_ORDER.get((level or "").upper()) if level else None
    out: list[dict] = []
    for stream in result:
        labels = stream.get("stream") if isinstance(stream, dict) else None
        labels = labels if isinstance(labels, dict) else {}
        module = _stream_name(labels)
        for entry in stream.get("values") or []:
            try:
                ts = int(entry[0]) / 1_000_000_000
                line = entry[1]
            except (TypeError, ValueError, IndexError):
                continue
            if not isinstance(line, str):
                continue
            lvl = _parse_level(line)
            if floor is not None and _LEVEL_ORDER.get(lvl, 20) < floor:
                continue
            out.append({
                "ts": ts,
                "level": lvl,
                "module": module,
                "function": labels.get("container") or source.key,
                "line": 0,
                "message": line.rstrip("\n"),
                "exception": None,
            })

    out.sort(key=lambda r: r["ts"], reverse=True)
    return out[:limit]
