# Ciclo setup → segnale → esito: piano di implementazione

**Obiettivo:** far dire al sistema la verità sul proprio funzionamento: quando un
setup converte, in quale evento, con quale esito, e su quale popolazione.

**Misurato in produzione il 2026-09-16 (sola lettura) prima di scrivere il piano:**

| Fatto | Numero |
|---|---|
| Setup attivi con un segnale compatibile su una barra successiva all'apertura | 85 (+10 sulla stessa data) |
| ...di cui passati dal ramo che AGGIORNA l'alert (mai convertiti) | 95 su 95 |
| Convertiti il cui alert ha spostato `signal_date` dopo la conversione | 71 su 334 |
| Convertiti il cui alert e' stato rivisto almeno una volta | 316 su 334 |
| **Convertiti con verso OPPOSTO al setup** (bull→bear o bear→bull) | **68 su 334** |
| Chiusure senza ragione registrata | 322 |

Il quinto non era nella proposta: `convert_setups_for_alert` non guarda il tono.

## Fase A — conversione guidata dall'evento (punti 1 e 2), backend

1. **Modello** `stock_setups`, colonne nullable nuove:
   `first_seen_bar` (barra letta all'apertura), `converted_signal_date`,
   `converted_price`, `converted_tone`, `conversion_source`
   (`live` | `legacy` | `reconciled`), `bar_lead_days`, e l'esito proprio
   dell'evento: `outcome_signal_date`, `outcome_horizon_days`,
   `outcome_fwd_return`, `outcome_mkt_neutral_excess`,
   `outcome_mkt_neutral_hit`, `outcome_matured_at`.
2. **Regola di conversione** (`setup_service.convert_setups_for_event`), unica per
   i due rami della scansione (inserimento E aggiornamento dell'alert):
   episodio aperto per (titolo, detector); tono compatibile (uguale, o setup
   senza direzione); barra dell'evento STRETTAMENTE successiva alla barra di
   apertura (`first_seen_bar`, o la data di `first_seen_at` sugli episodi
   precedenti). L'evento (data, prezzo, tono) si scrive sul setup e non cambia
   piu', qualunque cosa faccia poi l'alert.
3. **Esito dell'evento**: `signal_outcome_service` estrae l'etichettatura in una
   funzione condivisa e matura anche gli eventi di conversione, dalla LORO data.
   Le conversioni storiche senza evento ricostruibile prendono l'esito del
   magazzino solo se misura una barra non successiva alla conversione.
4. **Migrazione dati**, con regole verificate e test sulla catena Alembic vera:
   - storico → `legacy`; data evento scritta solo se l'alert non e' mai stato
     rivisto (`amend_count == 0`), cioe' quando e' certa;
   - verso opposto → chiuso con ragione `mislinked`, fuori dal tasso, contato;
   - gli 85 attivi con evento su barra successiva → `reconciled`: convertiti,
     SENZA data evento, anticipo ed esito (la prima rilevazione non fu
     registrata e non si inventa). I 10 sulla stessa data restano attivi.
5. **`conversion_stats`** legge l'esito dal setup, non dall'alert; espone
   `closed_total`, `excluded_from_rate`, `mislinked`, `closed_without_reason`,
   `converted_outcome_unavailable`.

## Fase B — conteggi e linguaggio visivo (punti 3 e 4), frontend

- Tessera «Esiti»: tutti i chiusi (797), con quanti entrano nel tasso e perche'
  gli altri no; chiusure senza ragione visibili.
- «Convertiti: esito» ed «Efficacia» diventano UNA tessera: tasso, conteggi,
  intervallo, stato dell'evidenza. Nessun colore da maggioranza semplice; il
  colore solo se l'intervallo esclude il 50%. Stesso criterio per il rendimento.

## Fase C — maturazione (punto 5)

Prefiltro SQL dei candidati maturabili: si conta per ogni alert quante barre
esistono da `signal_date` in poi, e si carica la serie solo se sono > H. E'
esattamente la condizione che il ciclo verificava in Python, quindi gli esiti
sono identici per costruzione; test di equivalenza sugli esiti prodotti.
Misura del tempo in produzione prima e dopo.

## Fase D — provenienza (punto 7)

`app/core/provenance.py`: versioni di emissione, conversione e metodo d'esito +
`GIT_SHA`. Scritte nello snapshot dell'alert, sul setup alla conversione e
sulla riga d'esito. Lo storico resta `NULL`, dichiarato come tale.

## Fase E — cronologia nel dettaglio (punto 6)

Nel dialogo del setup: apertura → conversione (evento) → esito o attesa, usando
i campi della fase A. Nel dialogo dell'alert, l'origine mostra la data
dell'evento che ha convertito.

## Fuori perimetro

Qualunque affermazione predittiva («un setup anticipa segnali migliori»):
richiede un confronto fuori campione che 83 esiti in una finestra non reggono.

Ogni fase: test, `ruff`, suite, commit, push dopo CI verde della precedente.
