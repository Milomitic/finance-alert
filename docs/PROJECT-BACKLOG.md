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
| FA-003 | P1 | Backup | Migrare dal Barman integrato CNPG al Barman Cloud Plugin prima di CNPG 1.31 | **IN PROGRESS** | Plugin chart 0.8.0/v0.15.0 installato, pg 2/2 Ready, WAL archiviati e Backup pg-plugin-verify-20260909 completed. Restore separato pg-restore-fa003 in verifica. |
| FA-004 | P1 | Osservabilità | Aggiornare gli alert ai metric name del plugin | **IN PROGRESS** | PrometheusRule applicata e plugin scrape up=1. Verificare aggiornamento timestamp dopo backup e caricamento regole. |
| FA-005 | P2 | Kubernetes | Rimuovere `spec.monitoring.enablePodMonitor` deprecato | **DONE / PROD** | PodMonitor finance-alert-postgres presente in monitoring, scrape up=1; enablePodMonitor=false restituito dal default del server. |
| FA-006 | P2 | Performance | Analizzare i percorsi lenti sui percentili reali | **WAITING DATA** | Bucket/latenze già strumentati; attendere almeno 7 giorni e misurare p50/p95/p99 prima/dopo. |
| FA-007 | P2 | Frontend | Introdurre RUM per Web Vitals LCP/INP/CLS | **IN PROGRESS** | Endpoint pubblicato. Revisione: usare web-vitals ufficiale per CLS/INP e un solo observer per documento; route normalizzate a un insieme finito. Secondo rilascio in preparazione. |
| FA-008 | P2 | Frontend | Ridurre e presidiare i finding ESLint React Hooks | **OPEN** | 47 finding residui (39 errori, 8 warning). Ridotte allocazioni ripetute e rimossi timer a 1Hz sulle pagine; build e 283 test frontend passati. Non tutte le segnalazioni provengono da React Hooks: 21 sono Fast Refresh. |
| FA-009 | P1 | UX | Correggere etichette valuta/prezzo nelle posizioni | **READY / LOCAL** | Prezzi e P&L usano la valuta nativa con fallback USD; build/test frontend passano. |
| FA-010 | P1 | UX | Rendere visibili e recuperabili gli errori delle mutazioni | **READY / LOCAL** | Hook posizioni con toast successo/errore e dettaglio API; form trade mantiene errore inline. |
| FA-011 | P1 | UX mobile | Focus trap, ESC, scroll lock e restore del drawer | **READY / LOCAL** | Comportamento dialog implementato; verifica browser reale dopo deploy. |
| FA-012 | P1 | UX/search | Stati errore e semantica combobox | **READY / LOCAL** | Stato errore con retry e ruoli `combobox`/`listbox`/`option` implementati. |
| FA-013 | P2 | UX/navigation | Preservare filtri/calendar/search nell’URL e migliorare il 404 | **OPEN** | 404 e URL calendar pubblicati. Restano verifica back/forward e serializzazione date locali: il solo passaggio della build non chiude il comportamento browser. |
| FA-014 | P2 | Sessioni | Revoca server-side e logout tra schede | **OPEN** | Revoca in memoria e logout tra schede pubblicati. La blacklist si perde al riavvio anche con una sola replica: serve persistenza condivisa prima di chiudere la revoca server. |
| FA-015 | P3 | Logging/storage | Guardrail dimensione Loki e monitoraggio disco nodo | **OPEN** | Regole pubblicate; guardia filesystem root disponibile. Il kubelet local-path non espone volume_stats per Loki: la regola PVC non ha dati e non puo essere dichiarata operativa. |
| FA-016 | P2 | Prodotto | Decomporre le 72 proposte dell’audit UI/UX | **OPEN** | Il documento frontend-ux-audit-2026-09-09.md contiene 72 nuove proposte, non una riconciliazione verificata del precedente audit. Alcune capability sono gia presenti. Riconciliare prima di pianificare nuove funzionalita. |
| FA-017 | P2 | Sicurezza | Triage dei finding Bandit e hardening dei casi confermati | **READY / LOCAL** | Validazione URL HTTP(S) aggiunta; classificazione in [docs/security-bandit-triage.md](security-bandit-triage.md). Nessun high; audit npm/pip senza vulnerabilità note. |
| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **READY / LOCAL** | `PriceAlertDialog` espone ora `DialogDescription` screen-reader-only; il warning Radix di descrizione mancante e stato corretto. |
| FA-019 | P0 | Release | Push e sincronizzazione cloud dei commit locali | **DONE / PROD** | Blocco superato: push f908721 riuscito, CI 34364844218 completata con tutti i job verdi; immagine f908721 osservata nel StatefulSet in produzione. Non occorrono ulteriori autorizzazioni al push. |

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
- La pipeline CI 34364844218 e verde; produzione verificata sull'immagine f908721. Gli aggiornamenti successivi richiedono la propria verifica CI/CD.
- La revoca sessioni e attualmente in memoria; non resiste a riavvii. FA-014 resta aperto.
- I valori RUM raccolti dal precedente reporter non vanno usati come Core Web Vitals validati; attendere la versione corretta e campioni reali.
- Il Python globale non contiene le dipendenze backend: usare uv run --project backend pytest.
