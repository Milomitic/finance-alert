# Modelli in prova silenziosa — cosa girano, dove si leggono, quando si promuovono

Fase 3 dello studio del 2026-09-23
([findings](2026-09-23-studio-taratura-e-ml-findings.md), §6-§7 e §9 C). Due
modelli calcolati e salvati accanto ai valori che il motore usa, **senza essere
usati da niente**. Prendono il posto degli attuali solo se gli esiti reali
confermano lo studio.

## I due modelli

| | Accanto a | Bersaglio | Nello studio |
|---|---|---|---|
| **volatilità** | ATR(14) | log(escursione media delle 10 sedute successive / ATR di oggi) | R² +0,17 contro l'ATR, positivo in 7 anni su 7 |
| **selezione** | Forza | il match batte lo stesso piano giocato su un titolo a caso lo stesso giorno | skill del 30% più alto −0,009 → +0,009 R, replicato su gruppi di titoli disgiunti |

Stesso gradient boosting a istogrammi dello studio (`app/ml/gbm.py`, numpy),
stesse variabili note alla chiusura del giorno di emissione (contesto del
titolo sulla finestra di 260 barre dello scan, detector, Forza, fattori,
geometria del piano), niente variabili di mercato.

## Dove girano

- **Addestramento**: job `addestra_modelli_ombra`, domenica 05:00 (Roma).
  Addestra solo se un modello manca o ha più di 27 giorni, quindi una volta al
  mese e la prima domenica dopo il rilascio. Campione: 300 titoli per la
  volatilità (una data ogni 10 sedute), 80 titoli rigiocati coi detector per
  la selezione, ultimi 9 anni. Misurato in locale: ~35 s a titolo per il
  replay, ~1-1,5 h in totale sul nodo. A mano:
  `python -m app.scripts.addestra_modelli_ombra`.
- **Punteggio**: lo scan, per ogni alert nuovo (`snapshot.first_ombra`, fissato
  come le altre variabili dell'ingresso e conservato a ogni revisione) e per
  ogni match scartato (`signal_candidates.ombra`, con il contesto in
  `signal_candidates.contesto`). Un guasto rende `{}` e basta: lo scan non può
  fallire per un modello in prova.
- **Modelli**: tabella `modelli_ombra`, una riga per addestramento con le
  metriche dell'ultimo anno tenuto da parte (embargo 100 giorni). Ogni
  punteggio porta la `versione` del modello che l'ha prodotto.

## Come si legge

    kubectl exec -n finance-alert finance-alert-finance-alert-0 -- \
        python -m app.scripts.rapporto_modelli_ombra

Restituisce le metriche d'addestramento (`modelli.*.addestramento`) e il
confronto dal vivo:

- `volatilita.R2_contro_ATR` sugli alert con 10 sedute dopo l'emissione;
- `selezione.top30` / `selezione.resto`: tasso market-neutral con le
  **finestre indipendenti** accanto alle righe, e R medio del piano a
  finestre chiuse.

⚠️ La prima cosa da guardare dopo il primo addestramento sono le metriche
d'addestramento, non il confronto dal vivo: dicono se **questo** campione ha
riprodotto lo studio. `R2_contro_ATR` sotto zero, o `t_mensile` della
selezione sotto ~2,6 (la banda del caso misurata coi controlli permutati),
vogliono dire che il modello in servizio non è quello dello studio, e che il
confronto dal vivo misurerebbe un'altra cosa.

## Criterio di promozione (scritto prima di vedere un dato)

Nessuna delle due sostituzioni si fa prima di **sei mesi** di emissioni con
punteggio. Poi:

- **volatilità → al posto dell'ATR nel pavimento dello stop e nel
  dimensionamento**: `R2_contro_ATR` > 0 nella prima e nella seconda metà del
  periodo prese separatamente, e ≥ 0,05 sull'insieme, su almeno 1.000 alert.
  È l'unico dei due con una probabilità concreta di passare: l'effetto dello
  studio è grande rispetto al rumore.
- **selezione → al posto della soglia di Forza**: il 30% più alto batte il
  resto sul tasso market-neutral in entrambe le metà, e la differenza sta
  fuori dagli intervalli dimensionati sulle finestre indipendenti. ⚠️ Con
  l'effetto dello studio (~0,02 R) la potenza stimata chiede **16 mesi** sui
  segnali a 5 giorni e anni sugli altri. Un risultato a sei mesi che «sembra
  buono» non è un criterio soddisfatto: è il t isolato che lo studio insegna a
  non credere.

Cambiare le variabili, l'etichetta o il campione dopo aver visto gli esiti
dal vivo azzera l'orologio: il confronto torna in campione.

## Cosa non fare

- Usare `first_ombra` in un ordinamento, un filtro o un dimensionamento prima
  del criterio: è la stessa forma della rampa di rischio sulla Forza, tolta
  perché non aveva basi.
- Addestrare sugli esiti dal vivo, o su un campione scelto guardandoli. Il
  riaddestramento mensile usa solo barre anteriori alle emissioni che il
  modello poi valuta, quindi ogni punteggio resta fuori campione e le versioni
  si possono sommare; un addestramento che legge `signal_outcomes` o
  `plan_outcomes` renderebbe il confronto in campione.
