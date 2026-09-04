"""Generatore del cruscotto "Finance-Alert - Salute".

Il JSON e' generato invece che scritto a mano perche' la griglia di Grafana e'
posizionale: ogni pannello porta x/y/w/h assoluti, e spostarne uno a mano
significa ricalcolare quelli sotto. Qui le righe si accumulano da sole.
"""
import json

DS = {"type": "prometheus", "uid": "prometheus"}
panels = []
_next = [0]


def _id():
    _next[0] += 1
    return _next[0]


def target(expr, legend=None, instant=False):
    t = {"datasource": DS, "expr": expr, "refId": "A"}
    if legend:
        t["legendFormat"] = legend
    if instant:
        t["instant"] = True
    return t


def stat(title, expr, x, y, w=4, h=4, unit="none", steps=None, desc="",
         mappings=None, dec=0, text_mode="auto"):
    return {
        "id": _id(), "type": "stat", "title": title, "datasource": DS,
        "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, instant=True)],
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "textMode": text_mode, "colorMode": "background",
            "graphMode": "none", "justifyMode": "auto",
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit, "decimals": dec,
                "mappings": mappings or [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": steps or [{"color": "green", "value": None}],
                },
            },
            "overrides": [],
        },
    }


def ts(title, targets, x, y, w=8, h=7, unit="none", desc="", stack=False):
    return {
        "id": _id(), "type": "timeseries", "title": title, "datasource": DS,
        "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": targets,
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "fillOpacity": 18, "lineWidth": 2, "showPoints": "never",
                    "stacking": {"mode": "normal" if stack else "none"},
                },
            },
            "overrides": [],
        },
    }


def table(title, expr, x, y, w=4, h=5, desc="", renames=None, mappings=None):
    return {
        "id": _id(), "type": "table", "title": title, "datasource": DS,
        "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [target(expr, instant=True)],
        "transformations": [{
            "id": "organize",
            "options": {
                "excludeByName": {
                    "Time": True, "job": True, "instance": True, "namespace": True,
                    "pod": True, "service": True, "container": True,
                    "endpoint": True, "__name__": True,
                },
                "renameByName": renames or {},
            },
        }],
        "fieldConfig": {
            "defaults": {"mappings": mappings or [], "custom": {"align": "auto"}},
            "overrides": [],
        },
    }


def row(title, y):
    return {"id": _id(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


SI_NO = [{"type": "value", "options": {
    "0": {"color": "red", "text": "NO"},
    "1": {"color": "green", "text": "SI"}}}]

y = 0

# --- Riga 1: colpo d'occhio -------------------------------------------------
panels.append(row("Colpo d'occhio - le sei cose da guardare per prime", y))
y += 1
panels.append(stat(
    "App", 'min(up{namespace="finance-alert"})', 0, y, mappings=SI_NO,
    steps=[{"color": "red", "value": None}, {"color": "green", "value": 1}],
    desc="Prometheus raggiunge l'app. Rosso = il pod non risponde allo scrape."))
panels.append(stat(
    "Ultimo scan riuscito",
    '(time() - max(finance_alert_last_successful_run_timestamp_seconds{kind="alerts_scan"})) / 3600',
    4, y, unit="h", dec=1,
    steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 12},
           {"color": "red", "value": 26}],
    desc=("Ore dall'ultimo scan COMPLETATO. Il cron gira circa 3 volte al giorno, "
          "quindi oltre 12 ore e' sospetto e oltre 26 e' un guasto.")))
panels.append(stat(
    "Alert attivi",
    'count(ALERTS{alertstate="firing",alertname!="Watchdog"}) or vector(0)', 8, y,
    steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
    desc=("Alert Prometheus che stanno scattando. Watchdog e' escluso di proposito: "
          "e' il canarino che DEVE sempre suonare per certificare che Alertmanager funziona.")))
panels.append(stat(
    "Target non raggiungibili", 'count(up == 0) or vector(0)', 12, y,
    steps=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
    desc=("Endpoint che Prometheus non riesce a interrogare. Un target giu' non degrada "
          "nulla di visibile: e' cosi' che le metriche di Grafana sono rimaste assenti per mesi.")))
panels.append(stat(
    "Riavvii pod (24h)",
    'sum(increase(kube_pod_container_status_restarts_total{namespace="finance-alert"}[24h])) or vector(0)',
    16, y,
    steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 1},
           {"color": "red", "value": 3}],
    desc="Riavvii nelle ultime 24 ore. Un OOM-kill compare qui prima che altrove."))
panels.append(stat(
    "Memoria usata",
    '100 * max(container_memory_working_set_bytes{namespace="finance-alert",container="finance-alert"})'
    ' / max(kube_pod_container_resource_limits{namespace="finance-alert",container="finance-alert",resource="memory"})',
    20, y, unit="percent",
    steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 75},
           {"color": "red", "value": 90}],
    desc="Percentuale del LIMITE del container, non della memoria del nodo. Oltre il 90% l'OOM-kill e' vicino."))
y += 4

# --- Riga 2: freschezza dei dati -------------------------------------------
panels.append(row("Freschezza dei dati - il guasto che non si vede", y))
y += 1
panels.append(stat(
    "Prezzi (OHLCV)", 'max(finance_alert_data_age_days{dataset="ohlcv_daily"})', 0, y,
    unit="d", steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 4},
                     {"color": "red", "value": 8}],
    desc="Giorni dall'ultima barra memorizzata. Weekend e festivi giustificano 3-4 giorni."))
panels.append(stat(
    "Calendario macro", 'max(finance_alert_data_age_days{dataset="macro_observations"})', 4, y,
    unit="d", steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 8},
                     {"color": "red", "value": 20}],
    desc=("Giorni dall'ultima osservazione FRED. E' rimasto fermo 60 giorni senza che nulla "
          "lo segnalasse: la chiave API non era configurata e la pagina continuava a disegnarsi.")))
panels.append(stat(
    "Ultimo alert", 'max(finance_alert_data_age_days{dataset="alerts"})', 8, y,
    unit="d", steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 3},
                     {"color": "red", "value": 7}],
    desc=("Giorni dall'ultimo segnale emesso. Uno scan puo' completare senza emettere nulla: "
          "questo riquadro distingue i due casi.")))
panels.append(stat(
    "Titoli con prezzi vecchi", 'max(finance_alert_stale_ohlcv_stocks)', 12, y,
    steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 15},
           {"color": "red", "value": 40}],
    desc=("Titoli la cui barra piu' recente supera la finestra di staleness. Una manciata e' "
          "normale (simboli delistati): conta la TENDENZA, non il valore assoluto.")))
panels.append(stat(
    "Rotture di basis", 'max(finance_alert_basis_breaks)', 16, y,
    steps=[{"color": "green", "value": None}, {"color": "yellow", "value": 1},
           {"color": "red", "value": 4}],
    desc=("Titoli con uno split non riparato nella storia memorizzata. Contamina ATR, range 52 "
          "settimane, lente Tecnico e ogni detector il cui lookback attraversa la data. "
          "Ricalcolato dal job giornaliero delle 03:30.")))
panels.append(table(
    "Chiavi API", 'finance_alert_api_key_configured', 20, y, w=4, h=5,
    desc="Una chiave mancante degrada un'intera funzione a un WARNING nei log e nient'altro.",
    renames={"provider": "fornitore", "Value": "configurata"}, mappings=SI_NO))
y += 5

# --- Riga 3: motore --------------------------------------------------------
panels.append(row("Motore - cosa sta effettivamente producendo", y))
y += 1
panels.append(ts(
    "Setup per stato", [target("finance_alert_setups", "{{status}}")], 0, y, w=12, h=7,
    desc=("Gli scaduti sono la meta' onesta del tasso di conversione: senza di essi solo le "
          "conversioni si risolvono e il tasso legge 100%."), stack=True))
panels.append(stat(
    "Tasso di conversione setup",
    '100 * max(finance_alert_setups{status="converted"})'
    ' / (max(finance_alert_setups{status="converted"}) + max(finance_alert_setups{status="expired"}))',
    12, y, w=6, h=7, unit="percent", dec=1, text_mode="value_and_name",
    steps=[{"color": "blue", "value": None}],
    desc=("Convertiti sui risolti. Neutro di colore per scelta: e' una misura descrittiva, "
          "non un obiettivo da superare.")))
panels.append(stat(
    "Titoli nel catalogo", 'max(finance_alert_catalog_stocks)', 18, y, w=6, h=7,
    steps=[{"color": "blue", "value": None}], text_mode="value_and_name",
    desc="Dimensione dell'universo. Un calo improvviso significa che qualcosa ha cancellato righe."))
y += 7

# --- Riga 4: infrastruttura ------------------------------------------------
panels.append(row("Infrastruttura - andamento nel tempo", y))
y += 1
panels.append(ts(
    "Memoria: uso contro limite", [
        target('container_memory_working_set_bytes{namespace="finance-alert",container="finance-alert"}', "in uso"),
        target('kube_pod_container_resource_limits{namespace="finance-alert",container="finance-alert",resource="memory"}', "limite"),
    ], 0, y, w=8, h=7, unit="bytes",
    desc="Una crescita monotona che non si appiattisce mai e' una perdita; un plateau non lo e'."))
panels.append(ts(
    "Latenza HTTP (p95)", [target(
        "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
        "p95")], 8, y, w=8, h=7, unit="s",
    desc=("Le richieste sincrone lente saturano il threadpool: e' cosi' che il pod e' stato "
          "ucciso dalla liveness probe nel luglio 2026.")))
panels.append(ts(
    "Scadenza certificati TLS", [target(
        "(certmanager_certificate_expiration_timestamp_seconds - time()) / 86400", "{{name}}")],
    16, y, w=8, h=7, unit="d",
    desc=("Giorni alla scadenza. cert-manager rinnova da solo intorno ai 30 giorni: se questa "
          "linea scende sotto i 20, il rinnovo non sta funzionando.")))

dash = {
    "uid": "finance-alert-salute",
    "title": "Finance-Alert - Salute",
    "tags": ["finance-alert"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "1m",
    "time": {"from": "now-24h", "to": "now"},
    "editable": True,
    "description": (
        "Tutto cio' che un controllo manuale di salute guardava, in un posto solo. "
        "Ogni riquadro porta una descrizione che dice cosa significa e quando preoccuparsi: "
        "passa il mouse sulla i in alto a sinistra del riquadro."
    ),
    "panels": panels,
}

print(json.dumps(dash, indent=2, ensure_ascii=False))
