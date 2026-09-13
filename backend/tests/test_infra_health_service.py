"""Infrastructure health, read from Prometheus, surfaced inside the app.

The observability layer answered only to whoever could reach Grafana. That is
a second login for questions the app already has an opinion about — is every
scrape target up, is anything alerting, did the pod restart in the night — and
in practice it meant those questions got asked by hand, over kubectl, once
someone already suspected a problem.

The hard requirement here is the same one the rest of this codebase keeps
relearning: **a query that fails must read as unavailable, never as zero.**
"0 target giù" and "I could not ask" are opposite statements, and rendering
the second as the first is how a monitoring panel becomes an active lie —
green because it is blind.
"""
from __future__ import annotations

import pytest

from app.services import infra_health_service as infra


def _ok(*results: tuple[dict, str]) -> dict:
    """A Prometheus /api/v1/query success envelope."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": m, "value": [1757030000, v]} for m, v in results
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Parsing                                                                     #
# --------------------------------------------------------------------------- #

def test_scalar_reads_the_single_value():
    assert infra._scalar(_ok(({}, "18"))) == 18.0


def test_scalar_of_an_empty_vector_is_zero_not_none():
    """PromQL returns NO SERIES for `count(up == 0)` when nothing is down —
    that is a genuine zero, and the one case where empty means a number."""
    assert infra._scalar(_ok(), empty_is_zero=True) == 0.0


def test_scalar_of_an_empty_vector_is_none_when_absence_means_unknown():
    """`argocd_app_info` absent means nobody is scraping ArgoCD, not that the
    app is unhealthy. The two need different answers from the same shape."""
    assert infra._scalar(_ok()) is None


def test_a_failed_query_is_none_never_zero():
    assert infra._scalar(None) is None
    assert infra._scalar({"status": "error", "error": "boom"}) is None
    assert infra._scalar({"status": "success"}) is None


def test_a_non_numeric_value_is_none():
    assert infra._scalar(_ok(({}, "NaN"))) is None
    assert infra._scalar(_ok(({}, "quarantadue"))) is None


def test_series_returns_labels_with_values():
    got = infra._series(_ok(
        ({"job": "kps-grafana", "namespace": "monitoring"}, "1"),
        ({"job": "loki"}, "0"),
    ))
    assert got == [
        ({"job": "kps-grafana", "namespace": "monitoring"}, 1.0),
        ({"job": "loki"}, 0.0),
    ]


def test_series_of_a_failure_is_empty():
    assert infra._series(None) == []


# --------------------------------------------------------------------------- #
# The rollup                                                                  #
# --------------------------------------------------------------------------- #

def test_prometheus_unreachable_reports_unavailable_not_healthy():
    """The whole point. With no Prometheus every count must be None and the
    envelope must SAY the source is unreachable — a card full of zeros would
    read as a clean bill of health."""
    out = infra.compute_infra_health(fetch=lambda expr: None)

    assert out["available"] is False
    assert out["targets_up"] is None
    assert out["targets_down"] is None
    assert out["alerts_firing"] is None
    assert out["error"]


def test_a_healthy_cluster_reads_healthy():
    def fetch(expr: str):
        if expr.startswith("count(up == 1"):
            return _ok(({}, "18"))
        if expr.startswith("count(up == 0"):
            return _ok()                      # nothing down
        if "ALERTS" in expr and expr.startswith("count("):
            return _ok()                      # nothing firing besides Watchdog
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)

    assert out["available"] is True
    assert out["targets_up"] == 18
    assert out["targets_down"] == 0           # a real zero, from a real answer
    assert out["alerts_firing"] == 0
    assert out["error"] is None


def test_down_targets_are_named_not_just_counted():
    """"1 target giù" sends you to kubectl. The job name is the answer — the
    app's own metrics endpoint sat down for months behind exactly this."""
    def fetch(expr: str):
        if expr.startswith("count(up == 1"):
            return _ok(({}, "17"))
        if expr.startswith("count(up == 0"):
            return _ok(({}, "1"))
        if expr == "up == 0":
            return _ok((
                {
                    "job": "finance-alert",
                    "namespace": "finance-alert",
                    "instance": "10.42.0.9:8000",
                },
                "0",
            ))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)

    assert out["targets_down"] == 1
    # ⚠️ Oggetti e non piu' stringhe: il job da solo non basta quando ne ha
    # piu' endpoint — resta da scoprire QUALE e' caduto, che e' la stessa
    # domanda che il nome del job doveva chiudere.
    assert out["down_targets"] == [{
        "job": "finance-alert",
        "namespace": "finance-alert",
        "instance": "10.42.0.9:8000",
    }]


def test_un_target_senza_istanza_dice_assente_non_punto_interrogativo():
    """Prometheus puo' non esporre `instance`, ed e' diverso da un'istanza
    vuota. `None` lo dice; "?" lo travestirebbe da valore letto."""
    def fetch(expr: str):
        if expr.startswith("count(up == 0"):
            return _ok(({}, "1"))
        if expr == "up == 0":
            return _ok(({"job": "kubelet", "namespace": "monitoring"}, "0"))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)
    assert out["down_targets"][0]["instance"] is None


def test_the_watchdog_is_excluded_from_the_firing_count():
    """Watchdog fires forever BY DESIGN — it is the canary proving
    Alertmanager works. Counting it means the card is permanently red and
    stops being read at all."""
    assert 'alertname!="Watchdog"' in infra._ALERT_COUNT


def test_argocd_absent_is_unknown_rather_than_a_failure():
    """Nobody scrapes argocd-metrics unless a ServiceMonitor exists. Saying
    'non monitorato' is honest; inventing a sync status is not."""
    out = infra.compute_infra_health(fetch=lambda expr: _ok())
    assert out["argocd"] is None


def test_argocd_sync_state_comes_from_the_metric_labels():
    def fetch(expr: str):
        if expr.startswith("count(up == 1"):
            return _ok(({}, "18"))
        if "argocd_app_info" in expr:
            return _ok((
                {"name": "finance-alert", "sync_status": "Synced",
                 "health_status": "Healthy"}, "1",
            ))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)

    assert out["argocd"] == {"sync": "Synced", "health": "Healthy"}


def test_one_broken_query_does_not_blank_the_others():
    """Sub-queries are isolated: a metric the cluster does not expose must
    cost its own row, not the whole card."""
    def fetch(expr: str):
        if "certmanager" in expr:
            raise RuntimeError("no cert-manager metrics here")
        if expr.startswith("count(up == 1"):
            return _ok(({}, "18"))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)

    assert out["targets_up"] == 18
    assert out["cert_days"] is None


def test_the_fetcher_is_never_allowed_to_raise_through():
    """This is a health endpoint. It failing is the one thing that must not
    happen — an exception here takes down the page that would have explained
    the outage."""
    def boom(expr: str):
        raise ConnectionError("connection refused")

    out = infra.compute_infra_health(fetch=boom)
    assert out["available"] is False
    assert "refused" in out["error"].lower() or out["error"]


@pytest.mark.parametrize("value,expected", [("0", 0.0), ("99.5", 99.5)])
def test_memory_percentage_passes_through(value: str, expected: float):
    def fetch(expr: str):
        if expr.startswith("count(up == 1"):
            return _ok(({}, "18"))
        return _ok(({}, value)) if "memory" in expr else _ok()

    assert infra.compute_infra_health(fetch=fetch)["memory_pct"] == expected


def test_un_alert_porta_severita_da_quando_e_che_cosa_dice():
    """⚠️ Il nome di un alert non e' una diagnosi.

    «KubePodCrashLooping» manda a cercare; «il pod app riavvia da 12 minuti,
    warning» dice gia' che fare. Le annotazioni vivono SOLO su
    `/api/v1/alerts`: la serie `ALERTS` porta le etichette e basta.
    """
    def fetch(expr: str):
        if "ALERTS" in expr and expr.startswith("count("):
            return _ok(({}, "1"))
        if expr.startswith("ALERTS"):
            return _ok((
                {"alertname": "KubePodCrashLooping", "severity": "warning",
                 "pod": "finance-alert-0"},
                "1",
            ))
        return _ok()

    def fetch_alerts():
        return [{
            "labels": {"alertname": "KubePodCrashLooping"},
            "annotations": {"summary": "Il pod app riavvia in ciclo"},
            "activeAt": "2026-09-13T01:00:00Z",
        }]

    out = infra.compute_infra_health(fetch=fetch, fetch_alerts=fetch_alerts)
    (a,) = out["firing_alerts"]
    assert a["name"] == "KubePodCrashLooping"
    assert a["severity"] == "warning"
    assert a["target"] == "finance-alert-0"
    assert a["summary"] == "Il pod app riavvia in ciclo"
    assert a["since"] == "2026-09-13T01:00:00Z"


def test_senza_annotazioni_resta_il_NOME_e_non_si_inventa_nulla():
    """⚠️ `/api/v1/alerts` puo' non rispondere. Il nome da solo e' meno utile,
    mai sbagliato — e i campi mancanti restano `None`, non stringhe finte."""
    def fetch(expr: str):
        if "ALERTS" in expr and expr.startswith("count("):
            return _ok(({}, "1"))
        if expr.startswith("ALERTS"):
            return _ok(({"alertname": "TargetDown"}, "1"))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch, fetch_alerts=lambda: None)
    (a,) = out["firing_alerts"]
    assert a["name"] == "TargetDown"
    assert a["summary"] is None
    assert a["since"] is None
    assert a["severity"] is None


def test_i_riavvii_dicono_QUALE_contenitore_e_PERCHE():
    """«3 riavvii» manda a kubectl; «app OOMKilled ×3» e' la risposta."""
    def fetch(expr: str):
        if expr.startswith("sum by (pod, container)"):
            return _ok((
                {"pod": "finance-alert-finance-alert-0", "container": "app"}, "3",
            ))
        if expr.startswith("kube_pod_container_status_last_terminated_reason"):
            return _ok((
                {"pod": "finance-alert-finance-alert-0", "container": "app",
                 "reason": "OOMKilled"},
                "1",
            ))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)
    (r,) = out["restart_details"]
    assert r["container"] == "app"
    assert r["count"] == 3
    assert r["reason"] == "OOMKilled"


def test_un_motivo_mancante_resta_None_e_non_diventa_Unknown():
    """Un pod ricreato da zero non ha un'ultima terminazione. Inventare una
    parola la farebbe sembrare letta — stessa regola fra assenza e zero che il
    repo applica ai numeri, qui applicata a una stringa."""
    def fetch(expr: str):
        if expr.startswith("sum by (pod, container)"):
            return _ok(({"pod": "p", "container": "app"}, "1"))
        return _ok()

    out = infra.compute_infra_health(fetch=fetch)
    (r,) = out["restart_details"]
    assert r["reason"] is None


def test_zero_riavvii_non_produce_una_riga():
    """⚠️ Il controllo negativo dei due sopra: senza, una funzione che elenca
    sempre qualcosa li passerebbe comunque. E una riga «app ×0» sarebbe rumore
    permanente nella scheda."""
    def fetch(expr: str):
        if expr.startswith("sum by (pod, container)"):
            return _ok(({"pod": "p", "container": "app"}, "0"))
        return _ok()

    assert infra.compute_infra_health(fetch=fetch)["restart_details"] == []
