# Observability (M6) — Prometheus + Grafana + Loki + Alertmanager→Telegram

The full SRE stack on the single k3s A1 VM, deliberately sized small so it
co-exists with the app + ArgoCD on 2 OCPU / 12 GB (after everything: node
memory ~46%, `MemoryPressure: False`).

Deployed with Helm directly (not ArgoCD) — the observability layer iterates on
its own cadence and holds no app state. Bringing it under ArgoCD is a possible
M9 follow-up; the value files in `infra/observability/` are the source of truth.

## Components (namespace `monitoring`)

| Piece | Chart | Role |
|---|---|---|
| Prometheus + operator | `kube-prometheus-stack` | scrape app `/metrics` + cluster (node-exporter, kube-state-metrics, kubelet, apiserver, coredns), 3d retention |
| Grafana | (bundled) | dashboards (25 pre-loaded) + datasources |
| Alertmanager | (bundled) | routes alerts → Telegram |
| Loki + promtail | `loki-stack` | centralised pod logs, 72h retention (compactor) |

Sizing lives in `infra/observability/kube-prometheus-stack.values.yaml` and
`loki-stack.values.yaml` (short retention, modest limits, 60s scrape, small
`local-path` PVCs).

## App metrics
`backend/app/main.py` mounts `prometheus-fastapi-instrumentator` → `GET /metrics`
(registered BEFORE the SPA catch-all). Prometheus discovers it via
`infra/observability/app-podmonitor.yaml` (a **PodMonitor** — the chart ships two
Services with identical labels, which a ServiceMonitor would double-scrape). The
stack runs with `*SelectorNilUsesHelmValues: false` so it picks up PodMonitors in
any namespace.

## Access

- **Grafana**: `http://<vm-ip>/grafana` — path-based on the raw IP (port 80 is
  NSG-allowlisted). No hostname because the ISP DNS (Wind3 RPZ) sinkholes
  nip.io/sslip.io. `serve_from_sub_path=true` + Traefik routing `/grafana`→Grafana,
  `/`→app. Admin password: generated at install (not in git). Swap for a real
  host in M4.
- Prometheus/Alertmanager UIs: `kubectl -n monitoring port-forward svc/kps-prometheus 9090:9090` (or `kps-alertmanager 9093:9093`).

## Datasources (in Grafana)
`Prometheus` (default, healthy), `Alertmanager`, `Loki`. Loki was added via the
Grafana API (its chart's provisioning ConfigMap was malformed and collided with
the sidecar). Note: Grafana's *health-probe* for the Loki (400) and Alertmanager
(500) datasources returns errors — a **cosmetic quirk** of those datasource
types; real queries work (verified: Loki returns app logs, an Alertmanager test
alert delivered to Telegram).

## Alerting → Telegram
Alertmanager routes all non-Watchdog alerts to a `telegram` receiver reusing the
app's existing bot (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`). The token is
injected at `helm upgrade` from an **ephemeral values file kept out of git**
(scratch) → lands only in the Alertmanager config Secret. The `Watchdog`
always-on alert is routed to `null` so it doesn't spam.

## Install / re-apply

```bash
export KUBECONFIG=$PWD/kubeconfig-oci
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts

# stack (Prometheus/Grafana/Alertmanager/exporters)
helm upgrade --install kps prometheus-community/kube-prometheus-stack -n monitoring --create-namespace \
  -f infra/observability/kube-prometheus-stack.values.yaml \
  -f <ephemeral-telegram-values> \
  --set grafana.adminPassword=<pw>

# logs (Loki + promtail)
helm upgrade --install loki grafana/loki-stack -n monitoring \
  -f infra/observability/loki-stack.values.yaml

kubectl apply -f infra/observability/app-podmonitor.yaml
# then add the Loki datasource via the Grafana API (POST /api/datasources).
```

## Known follow-ups
- Health-probe cosmetics for Loki/Alertmanager datasources (functional, ignore).
- The Loki datasource is API-added, not provisioned — re-add if the Grafana PVC
  is wiped.
- Bring the stack under ArgoCD (declarative) — M9.
