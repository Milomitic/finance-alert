# Finance Alert — backlog unico

Ultimo aggiornamento: 2026-09-09  
Repository: `finance-alert-cloud`  
Branch di lavoro: `codex/security-performance-review`

Questo file è il backlog operativo canonico. Ogni nuova attività deve avere un ID qui; un’attività si chiude solo quando il codice è stato pushato, sincronizzato dal CD e verificato nell’ambiente target.

## Stati

- **DONE / PROD**: implementata, pushata e verificata in produzione.
- **READY / LOCAL**: implementata e committata localmente, ma non ancora presente in produzione.
- **OPEN**: analizzata, da implementare.
- **WAITING DATA**: strumentazione presente; servono dati reali prima di decidere.
- **BLOCKED**: il prossimo passo richiede un’azione esterna o un’autorizzazione non disponibile.

## Stato corrente

| ID | Priorità | Area | Attività | Stato | Evidenza / criterio di chiusura |
|---|---:|---|---|---|---|
| FA-001 | P0 | Sicurezza | Proteggere `/metrics` dall’ingress pubblico con allowlist loopback | **DONE / PROD** | Commit `cb524d5` pushato; probe esterno 403, health 200, Prometheus interno `up=1`. |
| FA-002 | P1 | Backup | Portare la retention PostgreSQL da 7 a 30 giorni | **READY / LOCAL** | Commit `cae2986`; la produzione resta a 7 giorni finché non viene pushato e sincronizzato. |
| FA-003 | P1 | Backup | Migrare dal Barman integrato CNPG al Barman Cloud Plugin prima di CNPG 1.31 | **READY / LOCAL** | Manifest plugin/ObjectStore/Cluster/ScheduledBackup/runbook pronti e YAML validato; deploy reale ancora necessario. [Guida ufficiale](https://cloudnative-pg.io/plugin-barman-cloud/docs/migration/). |
| FA-004 | P1 | Osservabilità | Aggiornare gli alert ai metric name del plugin | **READY / LOCAL** | Regole aggiornate a `barman_cloud_cloudnative_pg_io_*`; verifica live dopo FA-003. |
| FA-005 | P2 | Kubernetes | Rimuovere `spec.monitoring.enablePodMonitor` deprecato | **READY / LOCAL** | Campo rimosso e PodMonitor esplicito aggiunto; verifica live dopo sync. |
| FA-006 | P2 | Performance | Analizzare i percorsi lenti sui percentili reali | **WAITING DATA** | Bucket/latenze già strumentati; attendere almeno 7 giorni e misurare p50/p95/p99 prima/dopo. |
| FA-007 | P2 | Frontend | Introdurre RUM per Web Vitals LCP/INP/CLS | **READY / LOCAL** | Reporter browser, endpoint autenticato e metriche Prometheus implementati; servono deploy e p75 reali. |
| FA-008 | P2 | Frontend | Ridurre e presidiare i finding ESLint React Hooks | **OPEN** | Baseline 60 finding: 45 errori, 15 warning. |
| FA-009 | P1 | UX | Correggere etichette valuta/prezzo nelle posizioni | **READY / LOCAL** | Prezzi e P&L usano la valuta nativa con fallback USD; build/test frontend passano. |
| FA-010 | P1 | UX | Rendere visibili e recuperabili gli errori delle mutazioni | **READY / LOCAL** | Hook posizioni con toast successo/errore e dettaglio API; form trade mantiene errore inline. |
| FA-011 | P1 | UX mobile | Focus trap, ESC, scroll lock e restore del drawer | **READY / LOCAL** | Comportamento dialog implementato; verifica browser reale dopo deploy. |
| FA-012 | P1 | UX/search | Stati errore e semantica combobox | **READY / LOCAL** | Stato errore con retry e ruoli `combobox`/`listbox`/`option` implementati. |
| FA-013 | P2 | UX/navigation | Preservare filtri/calendar/search nell’URL e migliorare il 404 | **READY / LOCAL** | Calendar state serializzato in URL e pagina 404 dedicata con link di recupero; build frontend passata. Verifica browser cross-session ancora da fare dopo deploy. |
| FA-014 | P2 | Sessioni | Revoca server-side e logout tra schede | **READY / LOCAL** | Token firmati revocabili fino a scadenza; logout revoca il cookie e invalida cache/propaga l’evento alle altre schede. Test backend mirati: 13 pass. Deploy multi-replica richiede store condiviso per la blacklist. |
| FA-015 | P3 | Logging/storage | Guardrail dimensione Loki e monitoraggio disco nodo | **READY / LOCAL** | Alert PVC >80% e filesystem root <15% aggiunti; retention Loki resta 30d. Stato osservato: ~152 MB su PVC 2 GiB, filesystem ~84%; verifica live dopo sync. |
| FA-016 | P2 | Prodotto | Decomporre le 72 proposte dell’audit UI/UX | **READY / LOCAL** | Roadmap numerata UX-001..UX-072 con sei tranche, risultati attesi e criteri comuni in [docs/frontend-ux-audit-2026-09-09.md](frontend-ux-audit-2026-09-09.md). |
| FA-017 | P2 | Sicurezza | Triage dei finding Bandit e hardening dei casi confermati | **READY / LOCAL** | Validazione URL HTTP(S) aggiunta; classificazione in [docs/security-bandit-triage.md](security-bandit-triage.md). Nessun high; audit npm/pip senza vulnerabilità note. |

| FA-018 | P2 | Accessibilita | Aggiungere descrizione accessibile al dialog degli alert prezzo | **READY / LOCAL** | `PriceAlertDialog` espone ora `DialogDescription` screen-reader-only; il warning Radix di descrizione mancante e stato corretto. |

## Ordine operativo

1. FA-002: push, sync Argo e verifica retention effettiva a 30 giorni.
2. FA-003: installare plugin, creare ObjectStore, migrare Cluster/ScheduledBackup, verificare backup e restore.
3. FA-004 e FA-005: chiudere alert e warning dopo la migrazione.
4. FA-006: attendere dati reali e intervenire solo sui percorsi con percentili significativi.
5. FA-007 e FA-008: RUM reale e pulizia lint.
6. FA-009–FA-013: tranche UX ad alto impatto.
7. FA-014–FA-018: sessioni, storage, triage sicurezza, accessibilita e roadmap prodotto.

## Vincoli e fatti da non confondere

- Il cluster usa ancora CNPG **1.30.0** e backup legacy `barmanObjectStore`; gli ultimi backup osservati sono completati.
- I commit locali non ancora sincronizzati su `origin/cloud` includono `cae2986`, `d5d32de`, `3697899`, `af4ec64`, `4ea9447`, `e2a3c88`, `79e30ff` e `c5d3e8b`; la produzione contiene solo il fix metrics `cb524d5`.
- I manifest plugin sono ora preparati nel repository locale, ma non applicati al cluster.
- Il Python globale non contiene le dipendenze backend: usare `uv run --project backend pytest`.
