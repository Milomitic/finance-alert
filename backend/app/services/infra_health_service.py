"""Infrastructure health, read from Prometheus, for the in-app Salute page.

Everything the observability stack knows was reachable only through Grafana —
a second login, for questions the app already has an opinion about. In
practice that meant nobody asked them until something already looked wrong,
and the answers came from kubectl by hand.

Prometheus is the single dependency on purpose. It already scrapes the
cluster (kube-state-metrics), Grafana, Loki, Alertmanager, cert-manager and
the app itself, so ONE unauthenticated in-cluster HTTP client answers for all
of them. Talking to each component directly would mean four clients, four
failure modes and, for ArgoCD, a token.

THE RULE THIS MODULE IS BUILT AROUND: a query that fails reads as UNAVAILABLE,
never as zero. "0 target giù" and "I could not ask" are opposite statements,
and rendering the second as the first turns a monitoring panel into an active
lie — green because it is blind. That is not hypothetical here: the app's own
metrics endpoint was a down target for months while every dashboard was calm.

So every value is `int | float | None`, sub-queries are isolated (one missing
metric costs its own row, not the card), and the envelope carries
`available` + `error` so the UI can say WHY a row is empty.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from loguru import logger

from app.core.config import settings

# Reachable from any pod in the cluster; overridden by PROMETHEUS_URL for
# local runs (where it is simply absent and the card says so).
_DEFAULT_PROM = "http://kps-prometheus.monitoring.svc:9090"

# A user is waiting on this. Prometheus answers these in milliseconds, so a
# short deadline costs nothing and a hung monitoring stack must not hang the
# health page along with it.
_TIMEOUT_S = 3.0

_NS = 'namespace="finance-alert"'

# Watchdog fires forever BY DESIGN — it is the canary that proves Alertmanager
# is delivering. Counting it leaves the card permanently red, which is the
# fastest way to make people stop reading it.
_ALERT_COUNT = 'count(ALERTS{alertstate="firing",alertname!="Watchdog"})'
_ALERT_LIST = 'ALERTS{alertstate="firing",alertname!="Watchdog"}'

_UP_COUNT = "count(up == 1)"
_DOWN_COUNT = "count(up == 0)"
_DOWN_LIST = "up == 0"
_RESTARTS = (
    f"sum(increase(kube_pod_container_status_restarts_total{{{_NS}}}[24h]))"
)
_MEMORY_PCT = (
    f'100 * max(container_memory_working_set_bytes{{{_NS},container="finance-alert"}})'
    f' / max(kube_pod_container_resource_limits{{{_NS},container="finance-alert",'
    'resource="memory"})'
)
_CERT_DAYS = (
    "min((certmanager_certificate_expiration_timestamp_seconds - time()) / 86400)"
)
_ARGOCD = 'argocd_app_info{name="finance-alert"}'
# One row per scraped component, so the card can name what is down instead of
# only counting it.
_COMPONENTS = 'up{namespace=~"monitoring|argocd|cert-manager|finance-alert"}'


def _prom_url() -> str:
    return (getattr(settings, "prometheus_url", None) or _DEFAULT_PROM).rstrip("/")


def _fetch(expr: str) -> dict | None:
    """One instant query. Returns the decoded envelope, or None on any
    failure — the caller distinguishes "no answer" from "answered zero"."""
    url = f"{_prom_url()}/api/v1/query?query={urllib.parse.quote(expr)}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as r:  # noqa: S310
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        # Debug, not warning: on a laptop with no cluster this fires on every
        # page load and would drown the log in expected noise.
        logger.debug(f"prometheus query failed: {expr}")
        return None


def _result(payload: dict | None) -> list[dict] | None:
    """The `data.result` list, or None when the envelope is not a success."""
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    res = data.get("result")
    return res if isinstance(res, list) else None


def _scalar(payload: dict | None, *, empty_is_zero: bool = False) -> float | None:
    """The single value of a one-series vector.

    `empty_is_zero` is the difference between two shapes that look identical
    over the wire. `count(up == 0)` returns NO SERIES when nothing is down —
    a genuine zero. `argocd_app_info` returns no series when nobody scrapes
    ArgoCD — genuinely unknown. Same payload, opposite meanings, so the caller
    has to say which one it is asking.
    """
    res = _result(payload)
    if res is None:
        return None
    if not res:
        return 0.0 if empty_is_zero else None
    try:
        v = float(res[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return None if v != v else v  # NaN is not an answer


def _series(payload: dict | None) -> list[tuple[dict, float]]:
    """(labels, value) pairs; empty on any failure."""
    out: list[tuple[dict, float]] = []
    for row in _result(payload) or []:
        try:
            out.append((dict(row.get("metric") or {}), float(row["value"][1])))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def _int(v: float | None) -> int | None:
    return None if v is None else int(round(v))


def compute_infra_health(
    *, fetch: Callable[[str], dict | None] | None = None
) -> dict:
    """Cluster + observability rollup. Never raises.

    `fetch` is injectable so the honesty rules above can be tested without a
    Prometheus — which is also the state this runs in on a laptop.
    """
    do_fetch = fetch or _fetch

    def ask(expr: str, *, empty_is_zero: bool = False) -> float | None:
        """Isolated sub-query: a metric this cluster does not expose costs its
        own row, not the whole card."""
        try:
            return _scalar(do_fetch(expr), empty_is_zero=empty_is_zero)
        except Exception:
            return None

    def ask_series(expr: str) -> list[tuple[dict, float]]:
        try:
            return _series(do_fetch(expr))
        except Exception:
            return []

    # The reachability probe is the same query as the first real one, so this
    # costs nothing extra.
    error: str | None = None
    try:
        probe = do_fetch(_UP_COUNT)
    except Exception as e:  # noqa: BLE001 — a health endpoint may not throw
        probe, error = None, f"{type(e).__name__}: {e}"

    # Availability is decided by whether Prometheus ANSWERED, not by what the
    # answer was. Deciding on the value confuses "I could not ask" with the
    # (real, and far more alarming) case where zero targets are up: PromQL
    # returns an empty vector for both.
    answered = _result(probe) is not None
    up = _scalar(probe, empty_is_zero=True)
    if not answered:
        return {
            "available": False,
            "error": error or f"Prometheus non raggiungibile ({_prom_url()})",
            "prometheus_url": _prom_url(),
            "targets_up": None,
            "targets_down": None,
            "down_targets": [],
            "alerts_firing": None,
            "firing_alerts": [],
            "restarts_24h": None,
            "memory_pct": None,
            "cert_days": None,
            "argocd": None,
            "components": [],
        }

    down = ask(_DOWN_COUNT, empty_is_zero=True)
    # Naming the down target is the whole value of the row: "1 target giù"
    # sends you to kubectl, "finance-alert/finance-alert" is the answer.
    down_targets = [
        f"{m.get('namespace', '?')}/{m.get('job', '?')}"
        for m, _ in ask_series(_DOWN_LIST)
    ]
    firing = ask(_ALERT_COUNT, empty_is_zero=True)
    firing_alerts = sorted(
        {m.get("alertname", "?") for m, _ in ask_series(_ALERT_LIST)}
    )

    argocd = None
    for m, _ in ask_series(_ARGOCD):
        argocd = {
            "sync": m.get("sync_status") or "?",
            "health": m.get("health_status") or "?",
        }
        break

    components = sorted(
        (
            {
                "job": m.get("job") or "?",
                "namespace": m.get("namespace") or "?",
                "up": v == 1.0,
            }
            for m, v in ask_series(_COMPONENTS)
        ),
        key=lambda c: (c["up"], c["namespace"], c["job"]),
    )

    return {
        "available": True,
        "error": None,
        "prometheus_url": _prom_url(),
        "targets_up": _int(up),
        "targets_down": _int(down),
        "down_targets": down_targets,
        "alerts_firing": _int(firing),
        "firing_alerts": firing_alerts,
        "restarts_24h": _int(ask(_RESTARTS, empty_is_zero=True)),
        "memory_pct": ask(_MEMORY_PCT),
        "cert_days": ask(_CERT_DAYS),
        "argocd": argocd,
        "components": components,
    }
