# Cruscotto "Finance-Alert · Salute"

Consolida in un posto solo tutto ciò che un controllo manuale di salute
guardava: pod, alert, target di scrape, freschezza dei dati, stato del motore,
memoria, certificati. Ogni riquadro porta una `description` che dice cosa
significa e **quando preoccuparsi** — visibile passando il mouse sulla `i` in
alto a sinistra del riquadro.

## File

| file | cos'è |
|---|---|
| `dashboard-salute.gen.py` | il generatore — **la sorgente da modificare** |
| `dashboard-salute.json` | l'output, quello che viene deployato |

Il JSON è generato e non scritto a mano perché la griglia di Grafana è
posizionale: ogni pannello porta `x/y/w/h` assoluti, quindi spostarne uno a
mano obbliga a ricalcolare tutti quelli sotto. Nel generatore le righe si
accumulano da sole.

```bash
# rigenerare dopo una modifica al .gen.py
cd backend && ./.venv/Scripts/python.exe ../infra/observability/dashboard-salute.gen.py \
  > ../infra/observability/dashboard-salute.json
```

## Deploy

⚠️ **`kps` NON è gestito da ArgoCD** (lo sono solo `cert-manager`,
`cnpg-operator`, `finance-alert`, `postgres-cluster`), quindi committare
questo file non deploya nulla. Il sidecar di Grafana raccoglie qualunque
ConfigMap etichettata `grafana_dashboard=1`, in qualsiasi namespace:

```bash
kubectl create configmap finance-alert-dashboard-salute -n monitoring \
  --from-file=salute.json=infra/observability/dashboard-salute.json \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl label configmap -n monitoring finance-alert-dashboard-salute \
  grafana_dashboard=1 --overwrite
```

Grafana rilegge `/tmp/dashboards` ogni 30 secondi (`updateIntervalSeconds` nel
provider), quindi compare da solo entro mezzo minuto.

Nota: il sidecar prova anche un POST a
`/api/admin/provisioning/dashboards/reload` che risponde **401** — le sue
`REQ_USERNAME`/`REQ_PASSWORD` sono vuote. È rumore innocuo, non un blocco: il
rescan a 30 secondi fa comunque il lavoro. Sistemarlo richiederebbe un
`helm upgrade`, che con la password admin fuori da git è più rischioso del
problema che risolve.

## Le metriche che alimentano la riga "Freschezza dei dati"

Non esistevano: sono state aggiunte in `app/core/app_metrics.py` insieme al
cruscotto, perché la maggior parte di ciò che si controlla a mano non era una
metrica.

| gauge | aggiornata da |
|---|---|
| `finance_alert_data_age_days{dataset}` | avvio app + fine scan |
| `finance_alert_setups{status}` | avvio app + fine scan |
| `finance_alert_api_key_configured{provider}` | avvio app + fine scan |
| `finance_alert_catalog_stocks` | avvio app + fine scan |
| `finance_alert_basis_breaks` | job giornaliero `repair_ohlcv_gaps` (03:30) |

`basis_breaks` sta sul job giornaliero e non a ogni scan perché esegue il
detector VERO su tutta la storia: costa un minuto o due. Non è approssimata in
SQL di proposito — una query `rapporto >= 3` ne trova 11 dove il detector ne
trova 2, e aggiungere il discriminante di volume dà 3 perdendo per giunta INDV
(volume nullo). Un indicatore che segna 3 quando la verità è 2 è il tipo di
numero che questo progetto continua a rimuovere.
