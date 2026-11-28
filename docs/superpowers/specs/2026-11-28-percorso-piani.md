# Movimento favorevole e uscite discrezionali

Il percorso misura la distanza dall’ingresso a TP1 nel verso del piano. Un rialzo del 48% su un target del 50% copre il 96% della distanza. Il rendimento in R continua a descrivere l’uscita prevista dal piano. Una chiusura registrata nella sezione Posizioni misura il rendimento dell’operazione personale.

## Lettura nella scheda Esiti

La direzione a scadenza si misura su tutti i segnali live maturi del filtro, compresi quelli privi di piano. Il confronto con la mediana dell’universo usa i soli segnali con benchmark disponibile. L’orizzonte decorre dalla data usata dal magazzino dei segnali. Il piano decorre dalla prima emissione e può avere una durata diversa. I denominatori e le finestre indipendenti sono esposti per orizzonte.

La curva dei piani usa finestre complete con misure del percorso disponibili. Le soglie del 50%, 75%, 90% e 100% sono cumulative. «Quasi» conta una sola volta ciascun piano che ha toccato almeno il 90% e si è risolto senza TP1. Chi seleziona un esito sta condizionando anche le statistiche a quell’esito.

Sulle barre giornaliere il percorso confermato esclude la barra dello stop. Il massimo di un piano che raggiunge TP1 si ferma a TP1. Il dettaglio conserva anche l’estremo grezzo della seduta di stop quando supera il massimo già documentato. La migliore chiusura può includere la scadenza. Per la domanda «potevo decidere il giorno successivo?» si considera soltanto una chiusura al 90% con il piano ancora aperto dopo la seduta.

## Replay del 28 novembre 2026

Riproducibile da `backend` con `python -m scripts.studio_taratura.percorso_piani` e i dati locali dello studio. Lo script usa gli episodi con i filtri live del replay, ingresso e barre giornaliere d’archivio, geometria e durata del piano correnti, e il filtro storico su ATR e volume dello studio. Verifica su ogni piano la parità di esito, durata e R tra simulazione di controllo e motore ordinario. Gli ingressi a finestra completa vanno dal 10 maggio 2017 al 15 ottobre 2026.

| Orizzonte | Piani | Tocco ≥90% | Quasi | Delta medio in R della mezza uscita | Finestre | t per blocco |
|---|---:|---:|---:|---:|---:|---:|
| 21 sedute | 65.036 | 9.866 | 1.885 | −0,0011 | 114 | −1,80 |
| 63 sedute | 43.102 | 11.406 | 1.524 | −0,0015 | 38 | −0,69 |

Sui 450 titoli, 17.863 piani hanno completato TP1. Altri 3.409 sono arrivati almeno al 90% prima della risoluzione, con 2.907 scadenze, 500 stop e 2 esiti ambigui. Tra i 5.926 piani che hanno anche chiuso almeno al 90% lasciando una seduta per decidere, 5.006 hanno poi completato TP1, 819 sono scaduti, 100 hanno preso lo stop e uno ha avuto un esito ambiguo.

La variante in ombra ipotizza un ordine limite già attivo per metà al 90% di TP1. L’altra metà segue il piano originario. Ogni gamba applica la convenzione prudente di stop prioritario se i due livelli sono nella stessa barra. Su tutti i 108.138 piani la differenza media appaiata è −0,0013R. Applicando per sensibilità un attrito incrementale di 5 punti base sul nozionale della metà chiusa anticipatamente, scende a −0,0023R. È un’ipotesi sui costi differenziali. Esecuzioni personali, slippage e commissioni effettive richiedono dati di eseguito.

L’analisi è retrospettiva, con finestre sovrapposte e uno storico già impiegato in studi precedenti. I risultati sostengono la visualizzazione del movimento intermedio. Per l’adozione di una regola generale d’uscita resta necessaria una conferma prospettica. Un quasi-target descrive il percorso anche quando il rendimento finale è negativo.
