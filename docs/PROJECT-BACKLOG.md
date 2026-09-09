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
| FA-001 | P0 | Sicurezza | Proteggere `/metrics` dall’ingress pubblico con allowlist loopback | **DONE / PROD** | Commit `cb524d5` pushato su `origin/cloud`; probe esterno HTTP 403, `/api/health` HTTP 200, Prometheus interno `up=1`. |
| FA-002 | P1 | Backup | Portare la retention PostgreSQL da 7 a 30 giorni | **READY / LOCAL** | Commit locale `cae2986`; modifica a Cluster, ScheduledBackup e runbook. La produzione resta a 7 giorni finché il commit non viene pushato e sincronizzato. |
| FA-003 | P1 | Backup | Migrare dal Barman integrato CNPG al Barman Cloud Plugin prima di CNPG 1.31 | **BLOCKED** | Plugin/ObjectStore/Cluster/ScheduledBackup/runbook/alert devono essere migrati atomicamente. Dry-run server riuscito; installazione reale non eseguita. Chiusura: plugin Healthy, nuovo backup completato, restore point verificato. Riferimento: [guida ufficiale di migrazione](https://cloudnative-pg.io/plugin-barman-cloud/docs/migration/). |
| FA-004 | P1 | Osservabilità | Aggiornare gli alert dai metric name legacy CNPG ai metric name del plugin | **OPEN** | Dipende da FA-003. Chiusura: alert testati sui metric name `barman_cloud_cloudnative_pg_io_*` e assenza di regole legacy attive. |
| FA-005 | P2 | Kubernetes | Rimuovere la dipendenza da `spec.monitoring.enablePodMonitor` deprecato | **OPEN** | Definire e gestire il PodMonitor esplicitamente; dry-run senza warning di deprecazione. |
| FA-006 | P2 | Performance | Analizzare i percorsi lenti sui percentili reali | **WAITING DATA** | Bucket/latenze già strumentati. Chiusura dopo almeno 7 giorni di traffico: p50/p95/p99 per endpoint, top regressioni e fix misurato prima/dopo. |
| FA-007 | P2 | Frontend | Introdurre RUM per Web Vitals (LCP, INP, CLS), separato mobile/desktop | **OPEN** | Dashboard p75 per route e dispositivo, soglie e regressioni visibili. Il build pass non equivale a una misura reale. |
| FA-008 | P2 | Frontend | Ridurre e presidiare i finding ESLint React Hooks | **OPEN** | Baseline verificata: 60 finding (45 errori, 15 warning). Chiusura per tranche con lint a zero o eccezioni motivate e scadenziate. |
| FA-009 | P1 | UX | Correggere etichette valuta/prezzo nelle posizioni e nei flussi correlati | **OPEN** | Valuta mostrata con codice/simbolo coerente con il dato e test UI per almeno EUR/USD. |
| FA-010 | P1 | UX | Rendere visibili e recuperabili gli errori delle mutazioni (salvataggi, aggiornamenti, eliminazioni) | **OPEN** | Errore API esposto con messaggio, retry e stato non ambiguo; test di failure path. |
| FA-011 | P1 | UX mobile | Correggere drawer mobile: focus, ESC, scroll lock e ritorno del focus | **OPEN** | Test keyboard/mobile: focus intrappolato nel drawer, ESC chiude, body non scrolla, focus torna al trigger. |
| FA-012 | P1 | UX/search | Stati errore e semantica combobox nella ricerca | **OPEN** | Errore distinto da “nessun risultato”; ruoli ARIA, tastiera e annunci verificati. |
| FA-013 | P2 | UX/navigation | Preservare stato filtri/calendar/search nell’URL e migliorare il 404 | **OPEN** | Deep-link riproduce lo stato; 404 offre ritorno e destinazione utile; test browser. |
| FA-014 | P2 | Sessioni | Revoca server-side e sincronizzazione logout tra schede | **OPEN / P3** | Sessioni revocabili, evento logout propagato tra tab. Priorità bassa per il modello single-owner. |
| FA-015 | P3 | Logging/storage | Aggiungere guardrail di dimensione a Loki e monitoraggio disco nodo | **OPEN / monitoraggio** | Alert su PVC e filesystem; policy di retention/size esplicita. Stato attuale: Loki ~152 MB su PVC 2 GiB, retention 30 giorni, filesystem nodo ~84%. |
| FA-016 | P2 | Prodotto | Decomporre e pianificare le 72 proposte dell’audit UI/UX completo | **OPEN** | Selezionare tranche con priorità e criteri di accettazione nel presente backlog; report dettagliato: `frontend-ux-audit-2026-09-09/finance-alert-frontend-ui-ux-improvements.md`. |

## Ordine operativo

1. **FA-002**: push, sync Argo e verifica che la retention effettiva sia 30 giorni.
2. **FA-003**: installare il plugin, creare ObjectStore, migrare Cluster e ScheduledBackup con cambio atomico, poi verificare backup/restore.
3. **FA-004** e **FA-005**: chiudere warning e alert dopo la migrazione.
4. **FA-006**: attendere la finestra dati e intervenire solo sui percorsi con percentili significativi.
5. **FA-007** e **FA-008**: RUM reale e pulizia lint.
6. **FA-009**–**FA-013**: tranche UX ad alto impatto.
7. **FA-014**–**FA-016**: hardening e roadmap prodotto.

## Vincoli e fatti da non confondere

- Il cluster usa ancora CNPG **1.30.0** e backup legacy `barmanObjectStore`; gli ultimi backup osservati risultano completati.
- Il commit locale `cae2986` non è ancora in produzione.
- I file locali `infra/gitops/barman-cloud-plugin.yaml` e `infra/gitops/postgres/objectstore.yaml` sono bozze non tracciate e non applicate; non fanno parte dello stato produttivo.
- Il report UI/UX è analisi; le attività FA-009–FA-013 non sono ancora correzioni applicate.

