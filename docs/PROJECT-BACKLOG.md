# Finance Alert — backlog unico

Ultimo aggiornamento: 2026-09-09  
Repository: `finance-alert-cloud`  
Branch di lavoro: `codex/security-performance-review`

Questo file è il backlog operativo canonico. Ogni nuova attività deve avere un ID qui; un’attività si chiude solo quando il codice è stato pushato, sincronizzato dal CD e verificato nell’ambiente target.

## Stati

- **DONE / PROD**: implementata, pushata e verificata in produzione.
- **READY / LOCAL**: implementata e committata localmente, ma non ancora presente in produzione.
- **IN PROGRESS**: implementazione o verifica in corso.
- **OPEN**: analizzata, da implementare.
- **WAITING DATA**: strumentazione presente; servono dati reali prima di decidere.
- **BLOCKED**: il prossimo passo richiede un’azione esterna o un’autorizzazione non disponibile.

## Stato corrente

| ID | Priorità | Area | Attività | Stato | Evidenza / criterio di chiusura |
|---|---:|---|---|---|---|
| FA-001 | P0 | Sicurezza | Proteggere `/metrics` dall’ingress pubblico con allowlist loopback | **DONE / PROD** | Commit `cb524d5` pushato; probe esterno 403, health 200, Prometheus interno `up=1`. |
| FA-002 | P1 | Backup | Portare la retention PostgreSQL da 7 a 30 giorni | **DONE / PROD** | ObjectStore pg-backups: retentionPolicy=30d verificata il 2026-09-09. La storia preesistente inizia il 2 settembre: 30d e la policy, non 30 giorni di backup retroattivi. |
| FA-003 | P1 | Backup | Migrare dal Barman integrato CNPG al Barman Cloud Plugin prima di CNPG 1.31 | **DONE / PROD** | Plugin chart 0.8.0/v0.15.0 installato, `pg-1` 2/2 Ready, WAL archiviati, `ScheduledBackup pg-daily` con `method=plugin` e backup `pg-plugin-verify-20260909` **completed** in 3m34s. Restore separato riuscito: cluster sano, dati verificati (stocks/alerts identici al live, ohlcv 2.476.821 contro 2.476.822 perche il live ha acquisito una barra dopo il backup; 28 tabelle, alembic `a3f71c9d2e40`, `fa_app` non superuser). Le risorse temporanee di restore e backup sono state eliminate e verificate come `NotFound`. |
| FA-004 | P1 | Osservabilità | Aggiornare gli alert ai metric name del plugin | **DONE / PROD** | PrometheusRule applicata, plugin scrape `up=1`, e la verifica che conta e fatta (2026-09-09): le tre serie `barman_cloud_cloudnative_pg_io_*` **esistono** in Prometheus, entrambe le regole sui backup le interrogano, tutte le 14 regole del gruppo valutano `ok/inactive` e l'ultimo backup disponibile risulta di 12,7 ore fa. Una regola che punta a un nome inesistente resta verde per assenza di serie, non per salute: e il guasto gia documentato in CLAUDE.md. |
| FA-005 | P2 | Kubernetes | Rimuovere `spec.monitoring.enablePodMonitor` deprecato | **DONE / PROD** | PodMonitor finance-alert-postgres presente in monitoring, scrape up=1; enablePodMonitor=false restituito dal default del server. |
| FA-006 | P2 | Performance | Analizzare i percorsi lenti sui percentili reali | **WAITING DATA** | Bucket/latenze già strumentati; attendere almeno 7 giorni e misurare p50/p95/p99 prima/dopo. |
| FA-007 | P2 | Frontend | Introdurre RUM per Web Vitals LCP/INP/CLS | **WAITING DATA** | `web-vitals` ufficiale per CLS/INP/LCP e route a cardinalita finita sono in produzione sull’immagine `42693fb`. Servono sessioni browser reali per popolare i percentili e validare il payload. |
| FA-008 | P2 | Frontend | Ridurre e presidiare i finding ESLint React Hooks | **OPEN** | Conteggio verificato: 39 errori e 8 warning su 306 file. Le ottimizzazioni principali sono state applicate; restano finding da classificare e correggere, inclusi 21 warning Fast Refresh. |
| FA-009 | P1 | UX | Correggere etichette valuta/prezzo nelle posizioni | **DONE / PROD** | Prezzi e P&L usano la valuta nativa con fallback USD; codice incluso nell’immagine `42693fb`, build e suite frontend verdi. |
| FA-010 | P1 | UX | Rendere visibili e recuperabili gli errori delle mutazioni | **DONE / PROD** | Hook posizioni con toast successo/errore e dettaglio API; form trade mantiene errore inline; codice incluso nell’immagine `42693fb`, build e suite frontend verdi. |
| FA-011 | P1 | UX mobile | Focus trap, ESC, scroll lock e restore del drawer | **IN PROGRESS** | Comportamento dialog deployato; manca la verifica manuale su browser/dispositivo reale per focus trap, ESC, scroll lock e restore. |
| FA-012 | P1 | UX/search | Stati errore e semantica combobox | **DONE / PROD** | Stato errore con retry e ruoli `combobox`/`listbox`/`option` implementati e inclusi nell’immagine `42693fb`; build e suite frontend verdi. |
| FA-013 | P2 | UX/navigation | Preservare filtri/calendar/search nell’URL e migliorare il 404 | **IN PROGRESS** | 404 e stato calendar/search serializzato in URL sono deployati; resta verifica browser di back/forward e serializzazione date locali. |
| FA-014 | P2 | Sessioni | Revoca server-side e logout tra schede | **OPEN** | Revoca in memoria e logout tra schede pubblicati. La blacklist si perde al riavvio anche con una sola replica: serve persistenza condivisa prima di chiudere la revoca server. |
| FA-015 | P3 | Logging/storage | Guardrail dimensione Loki e monitoraggio disco nodo | **OPEN** | Regole pubblicate; guardia filesystem root disponibile. Il kubelet local-path non espone volume_stats per Loki: la regola PVC non ha dati e non puo essere dichiarata operativa. |
| FA-016 | P2 | Prodotto | Decomporre le 72 proposte dell’audit UI/UX | **OPEN** | Il documento frontend-ux-audit-2026-09-09.md contiene 72 nuove proposte, non una riconciliazione verificata del precedente audit. Alcune capability sono gia presenti. Riconciliare prima di pianificare nuove funzionalita. |
| FA-017 | P2 | Sicurezza | Triage dei finding Bandit e hardening dei casi confermati | **DONE / PROD** | Validazione URL HTTP(S) aggiunta; classificazione in [docs/security-bandit-triage.md](security-bandit-triage.md). Nessun high; audit npm/pip e CI 34366785799 verdi; codice deployato nell’immagine `42693fb`. |
| FA-020 | P1 | Accessibilita | Lingua del documento, link di salto, nome del logout e titolo per rotta | **DONE / PROD** | `lang="it"`, link "Salta al contenuto" primo elemento focalizzabile, label logout `sr-only` e `document.title` derivato da `NAV`; 7 test dedicati, suite frontend 290 pass; immagine `42693fb` verificata in produzione. |
| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **DONE / PROD** | `PriceAlertDialog` espone `DialogDescription` screen-reader-only; warning Radix corretto, codice deployato e suite frontend verde. |
| FA-019 | P0 | Release | Push e sincronizzazione cloud dei commit locali | **DONE / PROD** | Push verificato; CI 34366785799 completata con tutti i job verdi, Argo `Synced/Healthy`, StatefulSet sull’immagine `42693fb1b09195be96065cfdc1bda0be176c014a`, health esterno 200 e `/metrics` esterno 403. |
| FA-021 | P2 | GitOps | Eliminare lo stato Argo `OutOfSync` del Cluster CNPG quando il diff effettivo è vuoto | **OPEN** | `postgres-cluster` è `Healthy` ma segnala `OutOfSync` solo su `Cluster/pg`; `argocd app diff --core` non produce diff. Va isolato il campo gestito dall’operatore e configurato un ignoreDifferences mirato, senza nascondere modifiche desiderate. |

## Ordine operativo

1. FA-002: push, sync Argo e verifica retention effettiva a 30 giorni.
2. FA-003: installare plugin, creare ObjectStore, migrare Cluster/ScheduledBackup, verificare backup e restore.
3. FA-004 e FA-005: chiudere alert e warning dopo la migrazione.
4. FA-006: attendere dati reali e intervenire solo sui percorsi con percentili significativi.
5. FA-007 e FA-008: RUM reale e pulizia lint.
6. FA-009–FA-013: tranche UX ad alto impatto.
7. FA-014–FA-018: sessioni, storage, triage sicurezza, accessibilita e roadmap prodotto.
8. FA-019: push/CD sbloccato; verificare ogni successivo rilascio.

## Evidenze e limiti

- Il 2026-09-09 il cluster e stato verificato via SSH: CNPG 1.30.0, plugin Barman installato; nessun aggiornamento dell'operatore eseguito.
- La pipeline CI 34366785799 e verde; produzione verificata sull'immagine `42693fb` con Argo `Synced/Healthy`. Gli aggiornamenti successivi richiedono la propria verifica CI/CD.
- La revoca sessioni e attualmente in memoria; non resiste a riavvii. FA-014 resta aperto.
- I valori RUM raccolti dal precedente reporter non vanno usati come Core Web Vitals validati; attendere la versione corretta e campioni reali.
- Il Python globale non contiene le dipendenze backend: usare uv run --project backend pytest.
