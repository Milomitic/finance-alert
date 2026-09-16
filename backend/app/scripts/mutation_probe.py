"""I test NOTEREBBERO un errore, o si limitano a eseguire la riga?

⚠️ E' la domanda che la copertura non fa. «Questa riga e' stata eseguita» e
«un suo errore verrebbe visto» sono cose diverse, e questo repo ha gia'
registrato quattro casi in cui coincidevano solo in apparenza: `toEqual` sui
nodi DOM (struttura al posto dell'identita'), il test sui giorni vero in UTC
cioe' in CI, la scheda filtri con tre aree chiuse, il `localStorage` di Node 25
che ingoiava ogni scrittura. In tutti e quattro il test passava, la riga era
coperta, e il difetto sarebbe passato.

Il modo sistematico di chiederlo e' rompere il codice apposta e guardare se
qualcuno protesta. Un mutante SOPRAVVISSUTO — codice alterato, suite ancora
verde — segnala una riga la cui correttezza nessuno sta verificando.

⚠️ PERCHE' UN MOTORE FATTO IN CASA E NON `mutmut`. mutmut e' lo strumento
standard ed e' stata la prima scelta: installato, configurato, e poi
`mutmut run` risponde «To run mutmut on Windows, please use the WSL». Avrei
potuto configurarlo solo per la CI, ma spedire un cancello che non ho MAI visto
girare e' esattamente il difetto che questo lavoro sta chiudendo — la stessa
forma dell'unit k3s e del livello apt. Questo motore ha meno operatori e in
cambio si esegue ovunque, si legge in una pagina, e non aggiunge dipendenze
(mutmut ne portava tre, fra cui una TUI).

⚠️ AMBITO RISTRETTO, e non per pigrizia. Mutare tutta `app/` significherebbe ore
per passata, e un cancello che nessuno aspetta viene spento. Si mutano i moduli
che questo repo ha deliberatamente consolidato in un PROPRIETARIO UNICO, cioe'
quelli dove un difetto si propaga a ogni schermata invece di restare locale.

    cd backend
    PYTHONPATH=. python -m app.scripts.mutation_probe            # tutti
    PYTHONPATH=. python -m app.scripts.mutation_probe --modulo fx_service
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]

#: modulo -> test che devono accorgersene.
#:
#: I test sono elencati esplicitamente e non dedotti: una passata che lancia
#: l'intera suite per ogni mutante costerebbe ore, e soprattutto non direbbe
#: QUALE test avrebbe dovuto proteggere quella riga.
#:
#: ⚠️ MA L'ELENCO DEVE ESSERE COMPLETO, e questo e' il rovescio della stessa
#: medaglia. Un elenco corto non produce un risultato prudente: produce
#: SOPRAVVISSUTI FALSI, cioe' lacune annunciate dove i test ci sono e
#: funzionano. Misurato il 2026-09-13: `detectors/base.py` elencava due file e
#: riportava 42 sopravvissuti su 58 — il modulo che calcola la Forza sembrava
#: non verificato. La verita' e' che i test stanno in `tests/signals/`, 45
#: file, e nessuno era elencato.
#:
#: Il difetto e' peggiore di una mancanza, perche' un numero alto qui si LEGGE
#: come rigore. Prima di aggiungere un modulo, cercare tutti i test che lo
#: nominano o lo importano — e rifarlo quando si aggiungono test.
#:
#: ⚠️ Vale anche all'indietro: i quattro moduli originali avevano elenchi
#: incompleti, quindi una parte della linea di base congelata a settembre era
#: fatta di sopravvissuti falsi.
BERSAGLI: dict[str, list[str]] = {
    # La provenienza dell'immagine: piccola, nuova, e il suo unico compito e'
    # distinguere tre stati (fresca / stantia / IGNOTA). Un fuori-di-uno sulla
    # soglia o un `None` collassato su `False` sono difetti silenziosi.
    "app/services/image_provenance.py": [
        "tests/test_image_provenance.py",
        "tests/test_api_platform_health.py",
    ],
    # L'etichetta della valuta: proprietario unico dopo che la logica dei
    # penny era quintuplicata in cinque servizi.
    "app/services/currency_units.py": [
        "tests/test_currency_label.py",
        "tests/test_alert_currency.py",
        "tests/test_ohlcv_currency_gate.py",
        "tests/test_ohlcv_minor_unit_scaling.py",
    ],
    # La conversione in dollari: un errore qui ha gia' fatto passare 75 titoli
    # per mega-cap che non lo erano (vedi risk.py in CLAUDE.md).
    "app/services/fx_service.py": [
        "tests/test_fx_honesty.py",
        "tests/test_position_fx.py",
        "tests/test_risk_market_cap_currency.py",
        "tests/test_fx_lacune_mutanti.py",
        "tests/test_screener_market_cap_usd.py",
    ],
    # Il tetto di 28 giorni sull'attesa di un setup: la scelta fra finestra
    # scorrevole e tetto e' stata misurata, e un fuori-di-uno la disfa.
    "app/services/setup_service.py": [
        # Versioni delle regole scritte e contate (2026-09-16).
        "tests/test_provenienza_regole.py",
        # Conversione per evento e suo esito (2026-09-16).
        "tests/test_setup_conversione_evento.py",
        "tests/test_setup_service.py",
        "tests/test_setup_conversion_outcomes.py",
        "tests/test_setup_earnings_window.py",
        "tests/test_setup_expiry_ceiling.py",
        "tests/test_setup_return_stats.py",
        # Scritto DOPO la passata che qui uccideva 49 su 90: la mediana
        # (che era duplicata e in una copia NON ordinava) e i confini del
        # sommario dei rendimenti.
        "tests/test_setup_service_mutanti.py",
        # ⚠️ Aggiunti il 2026-09-16, quando la notturna ha segnalato 9
        # sopravvissuti «nuovi» su codice di FA-061 (terzo tono, episodi,
        # perimetro) e FA-071 (serie ferma). I test di quelle correzioni
        # esistevano gia' ma non stavano in questo elenco: falsi
        # sopravvissuti, la forma che CLAUDE.md registra per `base.py`.
        "tests/test_setup_tone_terzo_valore.py",
        "tests/test_setup_episodi.py",
        "tests/test_setups_perimetro.py",
        "tests/test_serie_ferma_esce_dal_presente.py",
    ],
    # ─── Ampliamento 2026-09-13: da 4 a 12 moduli ─────────────────────────
    #
    # ⚠️ I quattro moduli iniziali erano quelli SCRITTI DA POCO, cioe' quelli
    # su cui il dubbio era piu' fresco. Sono anche i meno interessanti: il
    # codice nuovo e' quello che qualcuno ha appena guardato. Questi otto
    # reggono le conclusioni che l'app mostra a schermo, e alcuni non vengono
    # riletti da mesi.
    #
    # Il criterio non e' «i piu' grandi»: e' dove un errore sarebbe SILENZIOSO,
    # cioe' produrrebbe un numero plausibile invece di un'eccezione.

    # Il punteggio Forza. ⚠️ Qui un difetto e' gia' passato per tutta la vita
    # di un detector: gli ancoraggi di `chart_pattern` erano fuori scala e ogni
    # allarme prodotto era un triangolo a due soli valori di Forza, su 95
    # allarmi. I test dicevano «il pattern viene emesso» e quello era vero.
    "app/signals/detectors/base.py": [
        # ⚠️ L'INTERA cartella, non i due file col nome piu' somigliante: ogni
        # detector passa da `score_v2`, quindi ogni test di detector e' un
        # test di questo modulo. Elencarne due ne faceva sopravvivere 42 su 58
        # e faceva sembrare non verificato il calcolo della Forza.
        # Costo misurato: 3,3 s a mutante.
        "tests/signals/",
    ],
    # Probabilita', skill e la targa di onesta' (coinflip/negative/edge). Un
    # errore qui non rompe niente: cambia un'etichetta che l'utente legge come
    # un giudizio sul motore.
    "app/signals/calibration_map.py": [
        "tests/signals/",
        "tests/test_signal_drift_service.py",
    ],
    # Le finestre indipendenti e l'intervallo di Wilson: e' il codice che
    # impedisce di annunciare un'efficacia che il campione non regge. Un
    # fuori-di-uno qui STRINGE gli intervalli, cioe' sbaglia nella direzione
    # che fa sembrare il motore migliore di com'e'.
    "app/services/detector_performance_service.py": [
        # Versioni delle regole scritte e contate (2026-09-16).
        "tests/test_provenienza_regole.py",
        "tests/test_detector_performance.py",
        "tests/test_effective_sample.py",
        "tests/test_equity_curve_direction.py",
        # Scritto DOPO la passata che qui uccideva 19 su 50: il verdetto sul
        # bordo esatto del lancio di moneta, i filtri della curva di equity e
        # la pastiglia «campione scarso».
        "tests/test_detector_performance_mutanti.py",
    ],
    # ⚠️ Le sessioni. Un mutante che sopravvive qui e' un test che non
    # distingue un token valido da uno scaduto o manomesso.
    "app/core/security.py": [
        "tests/test_security.py",
        "tests/test_api_auth.py",
        "tests/test_session_revocation_persistence.py",
        # Scritto DOPO la prima passata, che su questo modulo uccideva 0 su 9:
        # copre i rami di RIFIUTO (hash malformato, username vuoto/lungo/non
        # stringa) che nessun test percorreva.
        "tests/test_security_mutanti.py",
        # ⚠️ `test_login_throttle.py` e' escluso di proposito: da solo porta la
        # sotto-suite da ~3 s a 13 s (contiene attese reali) e verifica la
        # limitazione dei tentativi, non la firma dei token. Un elenco completo
        # non vuol dire un elenco indiscriminato.
    ],
    # Il magazzino degli esiti: l'unica fonte di verita' su se un segnale ha
    # funzionato. Ha gia' avuto un difetto che ne misurava 19 righe su 4.880.
    "app/services/signal_outcome_service.py": [
        # Versioni delle regole scritte e contate (2026-09-16).
        "tests/test_provenienza_regole.py",
        # Prefiltro dei maturabili: equivalenza e confine (2026-09-16).
        "tests/test_maturazione_prefiltro.py",
        # Conversione per evento e suo esito (2026-09-16).
        "tests/test_setup_conversione_evento.py",
        "tests/test_signal_outcome_service.py",
        "tests/test_signal_drift_service.py",
        # Esercita `mature_outcomes` per verificare che gli ETF restino fuori
        # dal magazzino: mancava, ed e' un chiamante DIRETTO.
        "tests/test_etf_exclusions.py",
        # Scritto DOPO la passata che qui uccideva 20 su 57: i confini
        # (colpo a rendimento nullo, maturazione, segno market-neutral,
        # ricorrenza della EMA, prezzi sotto l'unita').
        "tests/test_signal_outcome_mutanti.py",
        # ⚠️ Questo NON importa il servizio: costruisce righe `SignalOutcome` a
        # mano e verifica il verso della curva dal lato del CONSUMATORE. Resta
        # in elenco perche' fissa lo stesso contratto (il tono al momento della
        # maturazione) e costa 0,4 s, ma non aspettarti che uccida mutanti di
        # questo modulo: non ne esegue una riga.
        "tests/test_equity_curve_direction.py",
    ],
    # La lente Tecnico: posture e punteggio continuo.
    "app/services/technical_score_service.py": [
        "tests/test_technical_score.py",
        "tests/test_technical_recompute_one.py",
        # Chiama `recompute_one` attraverso l'endpoint: mancava. ⚠️ Gli altri
        # sette file che nominano "technical_score" toccano il MODELLO
        # `TechnicalScore`, non il servizio — includerli allungherebbe ogni
        # mutante senza poter uccidere niente.
        "tests/test_api_scores.py",
        # Scritto DOPO la passata che qui uccideva 15 su 107: i CONTRATTI
        # (bande di postura, pavimento di storia, guardie sui denominatori
        # nulli, estremi della percentile, il titolo giusto), non le tarature.
        "tests/test_technical_score_mutanti.py",
        # `forget` (FA-071): i suoi test stanno col resto della correzione.
        "tests/test_serie_ferma_esce_dal_presente.py",
    ],
    # La de-correlazione per famiglia: N segnali correlati devono contare ~1.3,
    # non N. Se smette di funzionare la confluenza si gonfia in silenzio.
    "app/services/confluence_service.py": [
        "tests/test_confluence_service.py",
        "tests/test_confluence_strength_field.py",
        # Scritto DOPO la passata che qui uccideva 17 su 38: la
        # de-correlazione sul lato RIBASSISTA (il gemello rialzista era gia'
        # coperto), l'ordine dei gruppi e dei componenti, il filtro di
        # validita' e i bordi delle soglie.
        "tests/test_confluence_mutanti.py",
    ],
    # Gli arretrati a schermo. Ci e' appena stato trovato un denominatore
    # perso da una rinomina: esattamente la classe di errore che non solleva
    # eccezioni.
    "app/services/verification_posture.py": [
        "tests/test_verification_posture.py",
    ],
}


#: Sopravvissuti EQUIVALENTI: il codice mutato fa davvero la stessa cosa, o la
#: differenza e' deliberatamente tollerata. Vanno elencati CON LA RAGIONE, non
#: nascosti — un sopravvissuto senza spiegazione e' indistinguibile da una
#: lacuna, e dopo qualche mese nessuno sa piu' quale dei due fosse.
#:
#: ⚠️ Non e' il posto dove mettere i sopravvissuti scomodi. Al primo giro su
#: `image_provenance` ne sono emersi quattro: DUE erano lacune vere — il bordo
#: esclusivo della soglia (`>` contro `>=`, il fuori-di-uno piu' comune che
#: esista) e il taglio a dieci caratteri di una data con orario — e sono state
#: chiuse con un test. Solo le altre due stanno qui.
EQUIVALENTI: dict[str, str] = {
    "app/services/image_provenance.py::<modulo>#0  7 -> 8":
        "STALE_AFTER_DAYS: il test sulla soglia asserisce un INTERVALLO "
        "ragionevole (3-14) e non il valore esatto, di proposito — il numero e' "
        "una taratura, non un contratto, e fissarlo renderebbe rosso ogni "
        "ripensamento legittimo. Otto giorni resta una soglia sensata.",
    # ── cubo prestazioni e setup: due irraggiungibili e due tarature ────
    "app/services/detector_performance_service.py::_cell#0  21 -> 22":
        "`max((r.horizon_days for r in rows), default=21)`. Il ripiego e' "
        "IRRAGGIUNGIBILE: `_cell` calcola `n = len(rows)` e poi divide per n "
        "due righe sopra, quindi con `rows` vuoto sarebbe gia' esplosa. Il "
        "default non viene mai usato.",
    "app/services/detector_performance_service.py::compute_equity_curve#0  Gt -> GtE":
        "`if peak > 0`. Il picco parte da 1.0 ed e' aggiornato solo con "
        "`max(peak, eq)`, quindi non scende MAI sotto 1: `> 0` e' sempre vero e "
        "`>= 0` lo e' altrettanto. ⚠️ Il gemello numerico `peak > 1` invece NON "
        "e' equivalente — una curva che perde dalla prima operazione tiene il "
        "picco a 1.0 esatto e perderebbe il drawdown — ed e' ucciso da "
        "`test_una_curva_SEMPRE_in_perdita_ha_comunque_un_drawdown`.",
    "app/services/setup_service.py::<modulo>#0  10 -> 11":
        "`_EXPIRE_AFTER_DAYS`: per quanti giorni un setup resta in lista senza "
        "essere piu' visto. E' una TARATURA del prodotto — quanto a lungo "
        "guardare una formazione — e fissarla con un test renderebbe rossa ogni "
        "ritaratura legittima. Il COMPORTAMENTO del confine e' un'altra cosa e "
        "resta misurato in linea di base.",
    "app/services/setup_service.py::<modulo>#0  28 -> 29":
        "`_MAX_AGE_DAYS`, stessa natura: il tetto d'eta' oltre il quale una "
        "formazione non e' piu' interessante anche se ancora visibile.",
    # ── detectors/base: quindici superstiti, TUTTI equivalenti ──────────
    #
    # ⚠️ Lo scorer della Forza chiude a 43 su 58 e i quindici che restano non
    # sono un arretrato: sono cinque famiglie, e nessuna e' uccidibile da un
    # test onesto. Vale la pena riconoscerle a vista, perche' ricompaiono.
    #
    # (a) Il termine `x <= 0` di una guardia dove la formula rende comunque 0
    #     in x = 0. (b) I bordi di una curva CONTINUA: al nodo esatto il tratto
    #     successivo calcola lo stesso numero. (c) Guardie irraggiungibili
    #     perche' un ramo precedente ha gia' restituito. (d) Un `return`
    #     difensivo che nessun cammino raggiunge. (e) `frozen=True` senza un
    #     consumatore che eserciti l'immutabilita'.
    "app/signals/detectors/base.py::soft01#0  LtE -> Lt":
        "Il termine `x <= 0` della guardia. Col mutante `x < 0` uno zero passa, "
        "ma la formula rende `0 / (0 + 0.25*ref)` = 0.0 — lo STESSO valore del "
        "ramo di guardia. ⚠️ Il gemello sulla stessa riga, `ref <= 0`, NON e' "
        "equivalente (rende 1.0) ed e' ucciso da "
        "`test_soft01_respinge_un_riferimento_NULLO`: due termini della stessa "
        "condizione, esiti opposti.",
    "app/signals/detectors/base.py::log_saturate#0  LtE -> Lt":
        "Stessa forma: in x = 0 `log1p(0)` e' zero, quindi il risultato e' 0.0 "
        "con o senza guardia. Il termine `ceil <= 0` invece divide per zero ed "
        "e' ucciso.",
    "app/signals/detectors/base.py::concave#0  LtE -> Lt":
        "Idem per il termine `x <= 0`: il primo tratto rende `0.45 * (0/a45)` = "
        "0.0. Il termine `a45 <= 0` e' ucciso.",
    "app/signals/detectors/base.py::concave#2  LtE -> Lt":
        "CONTINUITA'. `x <= a45` -> `<`: nel bordo esatto il tratto successivo "
        "calcola `0.45 + 0.30*(a45-a45)/(a75-a45)` = 0.45, lo stesso valore. Non "
        "e' una lacuna: e' la prova che la curva non ha salti, e "
        "`test_concave_e_CONTINUA_sui_tre_nodi` fissa la proprieta' che lo rende "
        "vero.",
    "app/signals/detectors/base.py::concave#3  LtE -> Lt":
        "CONTINUITA' sul secondo nodo: al bordo il tratto successivo rende 0.75.",
    "app/signals/detectors/base.py::concave#4  LtE -> Lt":
        "CONTINUITA' sul terzo nodo — e qui il docstring del modulo lo dichiara "
        "esplicitamente: «The tail is continuous at (a88, 0.88)». La coda in "
        "a88 vale `_CONCAVE_CEIL - (0.99-0.88)*exp(0)` = 0.88.",
    "app/signals/detectors/base.py::score#0  Gt -> GtE":
        "CONTINUITA' del ginocchio. `raw > _CONF_KNEE` -> `>=`: esattamente al "
        "ginocchio la compressione rende `KNEE + (MAX-KNEE)*0/(1-KNEE)` = KNEE, "
        "cioe' il valore che il ramo non compresso avrebbe dato.",
    "app/signals/detectors/base.py::interp_adjustment#0  LtE -> Lt":
        "CONTINUITA' sul primo punto: col mutante si entra nel ciclo, che per "
        "`raw == x0` interpola a `y0 + (y1-y0)*0` = y0 — lo stesso "
        "`pts[0][1]`.",
    "app/signals/detectors/base.py::interp_adjustment#0  GtE -> Gt":
        "CONTINUITA' sull'ultimo punto: col mutante l'ultima iterazione del "
        "ciclo interpola a `y0 + (y1-y0)*1` = y1, cioe' `pts[-1][1]`.",
    "app/signals/detectors/base.py::interp_adjustment#1  LtE -> Lt":
        "CONTINUITA' sui nodi interni: al bordo esatto il segmento successivo "
        "parte da quel punto e rende lo stesso valore.",
    "app/signals/detectors/base.py::concave#0  Gt -> GtE":
        "⚠️ IRRAGGIUNGIBILE, e capirlo richiede di guardare il ramo PRECEDENTE. "
        "`if x <= a75 and a75 > a45`: se a75 == a45 allora per `x <= a45` il "
        "ramo prima ha gia' restituito, e per `x > a45` la condizione `x <= a75` "
        "e' falsa. Il secondo termine non decide mai niente. "
        "`test_concave_sopravvive_ad_ancoraggi_DEGENERI` verifica che non "
        "esploda — non poteva uccidere questo.",
    "app/signals/detectors/base.py::concave#1  Gt -> GtE":
        "Stessa irraggiungibilita' sul nodo successivo (`a88 > a75`). ⚠️ La "
        "terza della serie, `ceil > a88`, NON e' irraggiungibile — la coda ci "
        "arriva davvero — e infatti e' UCCISA.",
    "app/signals/detectors/base.py::interp_adjustment#6  1 -> 2":
        "`return pts[-1][1]` in coda alla funzione: irraggiungibile. Con raw "
        "strettamente fra il primo e l'ultimo punto il ciclo trova sempre un "
        "segmento e restituisce; fuori da quell'intervallo rispondono le due "
        "guardie sopra. E' un difensivo.",
    "app/signals/detectors/base.py::interp_adjustment#7  1 -> 2":
        "Il gemello sulla stessa riga (l'altro letterale), stessa ragione.",
    "app/signals/detectors/base.py::<modulo>#0  True -> False":
        "`@dataclass(frozen=True)` su `SignalMatch`: l'immutabilita' non ha un "
        "consumatore che la eserciti. E' igiene, non comportamento — stessa "
        "ragione gia' dichiarata per `image_provenance`.",
    # ── confluence_service: tre equivalenti, il resto e' arrotondamento ──
    "app/services/confluence_service.py::<modulo>#0  2 -> 3":
        "`_HORIZON_ORDER = {short: 0, medium: 1, long: 2}` -> long = 3. "
        "L'ordine e' PRESERVATO (0 < 1 < 3) e la funzione usa solo l'ordine, "
        "mai i valori: identica. ⚠️ I due gemelli che invece creano un PARI "
        "(short = medium, o medium = long) sono uccisi da "
        "`test_i_tre_orizzonti_hanno_un_ordine_STRETTO`, che asserisce la "
        "struttura e non i numeri — attraverso il comportamento sarebbero "
        "intermittenti, perche' l'ingresso di `sorted` e' un set.",
    "app/services/confluence_service.py::compute_confluence#2  1 -> 2":
        "Il valore di ripiego di `_HORIZON_ORDER.get(h, 1)`. E' "
        "IRRAGGIUNGIBILE: venti righe sopra `hz` viene normalizzato con "
        "`hz if hz in ('short','medium','long') else 'medium'`, quindi la "
        "chiave cercata esiste sempre e il default non viene mai usato.",
    "app/services/confluence_service.py::compute_confluence#0  10 -> 11":
        "`str(sdate)[:10]`, il taglio della data. ⚠️ Su `image_provenance` un "
        "taglio identico ERA una lacuna vera (li' il valore portava l'orario). "
        "Qui no: `Alert.signal_date` e' una colonna `Date`, quindi `str()` "
        "rende gia' dieci caratteri esatti e `[:11]` e' lo stesso taglio. La "
        "fetta resta come difesa, non come trasformazione.",
    # ── technical_score_service: solo le STRETTAMENTE equivalenti ───────
    #
    # ⚠️ Questo modulo chiude a 39 uccisi su 93 e il residuo NON e' un
    # arretrato: e' una superficie di TARATURA. Le finestre (50/200/252/63/126
    # /20/10), i periodi di ADX e RSI, il divisore 40, la miscela 0,6/0,4,
    # l'arrotondamento a un decimale, il tetto di 260 barre — fissarli con un
    # test significa rendere rossa ogni ritaratura legittima, cioe' il
    # contrario di cio' per cui questi presidi esistono. Restano in linea di
    # base, misurati e visibili. Qui sotto stanno SOLO quelli dove il codice
    # mutato fa davvero la stessa cosa.
    "app/services/technical_score_service.py::_trend#0  Gt -> GtE":
        "`int(price > f)` e i suoi due gemelli. Il bordo si raggiunge solo dove "
        "il prezzo eguaglia ESATTAMENTE la EMA, cioe' su una serie "
        "perfettamente piatta — dove il punteggio di trend non significa "
        "niente in nessuna delle due forme. ⚠️ E separare «un punto su quattro» "
        "da «zero punti» richiederebbe di limitare la miscela 0,6+0,4·adx_w: "
        "si congelerebbe una taratura per fissare un caso degenere. Il test "
        "`test_una_serie_ferma_NON_legge_come_trend` tiene la guardia larga "
        "(sotto la neutralita') proprio per non farlo.",
    "app/services/technical_score_service.py::_trend#1  Gt -> GtE":
        "Il secondo dei tre confronti di `pts`. Stessa ragione della "
        "voce `_trend#0` qui sopra: il bordo si raggiunge solo su una serie "
        "perfettamente piatta. ⚠️ La vecchia chiave `file:riga` li fondeva in "
        "una voce sola; l'ordinale li separa, ed e' la risoluzione che si "
        "guadagna.",
    "app/services/technical_score_service.py::_trend#2  Gt -> GtE":
        "Il terzo dei tre confronti di `pts`. Stessa ragione della "
        "voce `_trend#0` qui sopra: il bordo si raggiunge solo su una serie "
        "perfettamente piatta. ⚠️ La vecchia chiave `file:riga` li fondeva in "
        "una voce sola; l'ordinale li separa, ed e' la risoluzione che si "
        "guadagna.",
    "app/services/technical_score_service.py::_volume#0  GtE -> Gt":
        "`if n >= 10` davanti a `vol.iloc[-10:].mean()`. Con ESATTAMENTE dieci "
        "barre le due strade calcolano la stessa media, perche' `vol[-10:]` E' "
        "`vol`. Identiche, non simili — e comunque `partial_for` sbarra sotto "
        "le trenta.",
    "app/services/technical_score_service.py::_blended_return#0  Gt -> GtE":
        "`num / wsum if wsum > 0 else None`. `wsum` somma i pesi delle parti "
        "non nulle e `_blended_return` e' chiamata solo da `partial_for`, che "
        "richiede almeno trenta barre: `_ret(close, min(63, n-1))` ha sempre un "
        "k valido, quindi wsum >= 0,4. Il ramo in cui le due forme divergono "
        "(wsum == 0) e' irraggiungibile.",
    "app/services/technical_score_service.py::_recent_signal_facets#0  GtE -> Gt":
        "`Alert.triggered_at >= cutoff` dove cutoff e' `now() - 14 giorni`, un "
        "istante al microsecondo. Un avviso marcato ESATTAMENTE su quel "
        "microsecondo non e' costruibile in modo deterministico: la differenza "
        "esiste e non e' osservabile.",
    "app/services/technical_score_service.py::recompute_one#0  1 -> 2":
        "`.limit(1)` su una `where(stock_id == ...)` dove `stock_id` e' la "
        "CHIAVE PRIMARIA di technical_scores: al massimo esiste una riga, e "
        "`.first()` prende comunque la prima. Il limite e' cintura oltre alle "
        "bretelle, non un filtro.",
    "app/services/technical_score_service.py::recompute_one#1  1 -> 2":
        "Il gemello alla rilettura finale, stessa ragione: chiave primaria, "
        "una riga al massimo.",
    # ── signal_outcome_service: dieci superstiti, tutti dichiarati ───────
    #
    # ⚠️ Il modulo e' passato da 20 a 47 uccisi su 57. Questi dieci non sono i
    # "difficili": sono quelli che NESSUN test onesto puo' uccidere, perche'
    # fissarli congelerebbe una taratura o proverebbe un caso irraggiungibile.
    "app/services/signal_outcome_service.py::_load_universe_closes#0  GtE -> Gt":
        "`OhlcvDaily.date >= since` dove `since` e' gia' il minimo trigger "
        "MENO dieci giorni di margine: un giorno in piu' o in meno resta "
        "dentro il margine, e il docstring dimostra che la finestra non cambia "
        "il riferimento al giorno del segnale.",
    "app/services/signal_outcome_service.py::_load_stock_closes#0  900 -> 901":
        "SQLite tronca a 999 parametri legati, e 900 e' il margine sotto quel "
        "tetto. Il vincolo e' `< 999`, non `== 900`: 901 lo soddisfa "
        "identicamente. Un test che fissasse 900 impedirebbe di alzarlo a 950 "
        "senza guadagnare niente.",
    "app/services/signal_outcome_service.py::_load_stock_closes#0  Gt -> GtE":
        "Stesso margine, dal lato dell'operatore: con esattamente 900 titoli "
        "entrambe le strade funzionano (900 < 999).",
    "app/services/signal_outcome_service.py::_universe_fwd_medians#0  LtE -> Lt":
        "`if len(cs) <= horizon: continue`. Col bordo esatto — serie lunga "
        "quanto l'orizzonte — il ramo che passa produce `cs[:-horizon]` vuoto "
        "e `cs[horizon:]` vuoto, quindi zero osservazioni: le due forme fanno "
        "LA STESSA COSA, non due cose simili.",
    "app/services/signal_outcome_service.py::_universe_fwd_medians#0  True -> False":
        "`zip(..., strict=True)`. I due lati sono filtrati dalla STESSA maschera "
        "`ok`, quindi hanno lunghezza uguale per costruzione e `strict` non ha "
        "niente da rilevare: nessun test puo' distinguere le due forme finche' "
        "l'invariante regge. ⚠️ La voce diceva `False -> True` ed era descritta "
        "come «un miglioramento, non una lacuna»: il miglioramento e' stato "
        "fatto il 2026-09-14, quindi il mutante si e' invertito. Con `False` un "
        "disallineamento TRONCAVA in silenzio e il riferimento di mercato usciva "
        "da meno osservazioni di quante ce ne fossero; con `True` diventa un "
        "errore. Il mutante resta invisibile ai test, il difetto no.",
    "app/services/signal_outcome_service.py::_benchmark_medians#0  10 -> 11":
        "I dieci giorni di margine con cui la finestra dell'universo parte "
        "prima del primo trigger. E' un cuscinetto: allargarlo di un giorno "
        "carica una barra in piu' e non cambia nessun numero calcolato.",
    "app/services/signal_outcome_service.py::mature_outcomes#0  Lt -> LtE":
        "La guardia `ti < len(ema_arr)` e' IRRAGGIUNGIBILE nel ramo mutato: "
        "`ema_arr` ha la lunghezza di `cs` e `ti` viene da `_trigger_index`, "
        "che rende solo indici validi di `cs`. `ti == len` non accade.",
    "app/services/signal_outcome_service.py::mature_outcomes#0  Gt -> GtE":
        "`ema_arr[ti] >= 0`. La EMA all'indice `ti` include `cs[ti]` col peso "
        "alpha, e `entry > 0` e' gia' stato verificato in `_label`: "
        "quindi `ema_arr[ti] >= alpha * cs[ti] > 0` sempre. Il bordo zero non "
        "esiste.",
    "app/services/signal_outcome_service.py::mature_outcomes#0  And -> Or":
        "Col primo termine sempre vero (vedi sopra), `and` e `or` "
        "corto-circuitano allo stesso risultato. Il caso in cui divergono — "
        "`ema_arr` vuoto — richiede zero barre, che `_trigger_index` ha gia' "
        "escluso rendendo None.",
    "app/services/setup_service.py::convert_setups_for_event#0  And -> Or":
        "`first is not None and first.tzinfo is None`: `first_seen_at` e' NOT "
        "NULL, quindi il primo termine e' sempre vero e `or` rende vero anche "
        "su un datetime gia' consapevole — dove `replace(tzinfo=UTC)` su un "
        "valore gia' in UTC non cambia niente. Il database scrive sempre UTC.",
    "app/services/setup_service.py::<modulo>#0  True -> False":
        "`@dataclass(frozen=True)` su `EventOutcome`: nessun consumatore prova "
        "a scriverci, quindi l'immutabilita' non e' esercitata (famiglia 5).",
    "app/services/setup_service.py::_event_outcomes#0  And -> Or":
        "`outcome_matured_at` e `outcome_signal_date` sono scritte INSIEME "
        "da `mature_setup_outcomes`, in entrambi i rami: una riga con una "
        "sola delle due non esiste, e i due connettivi coincidono.",
    "app/services/setup_service.py::_per_detector#0  And -> Or":
        "`if judged and horizon`: `horizon` e' il massimo di "
        "`outcome_horizon_days` degli esiti giudicati, colonna scritta insieme "
        "all'esito, quindi e' None esattamente quando `judged` e' vuoto.",
    "app/services/signal_outcome_service.py::<modulo>#0  True -> False":
        "`@dataclass(frozen=True)` su `Label`: nessun consumatore prova a "
        "scriverci, quindi l'immutabilita' non e' esercitata (famiglia 5).",
    "app/core/security.py::hash_password#0  12 -> 13":
        "Il fattore di costo di bcrypt e' una TARATURA, non un contratto: 13 e' "
        "piu' forte di 12, e qualunque asserzione onesta e' un pavimento "
        "(`>= 12`), che per definizione non puo' bocciare un valore piu' alto. "
        "⚠️ Il mutante che conterebbe e' `12 -> 11` e questo operatore non lo "
        "genera: incrementa soltanto. Il pavimento e' fissato a mano in "
        "`test_il_costo_di_bcrypt_non_scende_sotto_12`.",
    "app/core/security.py::create_session_token#0  16 -> 17":
        "La lunghezza del nonce di sessione. Il jti e' OPACO — non viene mai "
        "letto, confrontato o misurato dal prodotto: serve solo a rendere ogni "
        "accesso revocabile per conto suo, quindi piu' entropia non e' un "
        "comportamento diverso. Stessa asimmetria del costo bcrypt: `16 -> 15` "
        "sarebbe un indebolimento vero e la sonda non lo produce; il pavimento "
        "sta in `test_il_nonce_di_sessione_ha_almeno_16_byte_di_entropia`.",
    "app/services/image_provenance.py::<modulo>#0  True -> False":
        "`@dataclass(frozen=True)`: l'immutabilita' non ha un consumatore che "
        "la eserciti. E' igiene, non comportamento; un test che prova a scrivere "
        "su un campo verificherebbe la libreria standard, non questo modulo.",
}


@dataclass(frozen=True)
class Mutante:
    riga: int
    prima: str
    dopo: str
    sorgente: str
    #: Nome qualificato della funzione (o classe) che contiene la mutazione,
    #: `<modulo>` per il codice a livello di file. Insieme a `ordine` forma la
    #: chiave di linea di base: vedi `chiave()` per il perche'.
    ambito: str = "<modulo>"
    #: Quante mutazioni IDENTICHE (stesso ambito, stesso prima -> dopo) sono
    #: gia' state generate prima di questa.
    ordine: int = 0


#: Scambi di confronto: il fuori-di-uno e' il difetto piu' comune e il piu'
#: facile da non notare, perche' il test tipico usa valori lontani dal bordo.
_CONFRONTI = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}


class _Riscrittore(ast.NodeTransformer):
    def __init__(self, bersaglio: int) -> None:
        self.bersaglio = bersaglio
        self.visti = 0
        self.applicato: tuple[int, str, str] | None = None

    def _prendi(self, nodo, prima: str, dopo: str) -> bool:
        self.visti += 1
        if self.visti - 1 != self.bersaglio:
            return False
        self.applicato = (getattr(nodo, "lineno", 0), prima, dopo)
        return True

    def visit_Compare(self, nodo: ast.Compare):
        self.generic_visit(nodo)
        if len(nodo.ops) == 1 and type(nodo.ops[0]) in _CONFRONTI:
            nuovo = _CONFRONTI[type(nodo.ops[0])]
            if self._prendi(nodo, type(nodo.ops[0]).__name__, nuovo.__name__):
                nodo.ops = [nuovo()]
        return nodo

    def visit_BoolOp(self, nodo: ast.BoolOp):
        self.generic_visit(nodo)
        nuovo = ast.Or if isinstance(nodo.op, ast.And) else ast.And
        if self._prendi(nodo, type(nodo.op).__name__, nuovo.__name__):
            nodo.op = nuovo()
        return nodo

    def visit_Constant(self, nodo: ast.Constant):
        # Solo interi e booleani: mutare una stringa produce quasi sempre un
        # mutante banale (un messaggio di log diverso) che nessun test deve
        # notare, e i banali sono il rumore che fa spegnere questi strumenti.
        if isinstance(nodo.value, bool):
            if self._prendi(nodo, str(nodo.value), str(not nodo.value)):
                return ast.Constant(value=not nodo.value)
        elif isinstance(nodo.value, int):
            if self._prendi(nodo, str(nodo.value), str(nodo.value + 1)):
                return ast.Constant(value=nodo.value + 1)
        return nodo


def _quanti(sorgente: str) -> int:
    r = _Riscrittore(-1)
    r.visit(ast.parse(sorgente))
    return r.visti


def _mappa_ambiti(albero: ast.Module) -> list[tuple[int, int, str]]:
    """(prima_riga, ultima_riga, nome_qualificato) per ogni funzione e classe."""
    fuori: list[tuple[int, int, str]] = []

    def scendi(nodo: ast.AST, prefisso: str) -> None:
        for figlio in ast.iter_child_nodes(nodo):
            if isinstance(figlio, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                nome = f"{prefisso}.{figlio.name}" if prefisso else figlio.name
                fine = figlio.end_lineno or figlio.lineno
                fuori.append((figlio.lineno, fine, nome))
                scendi(figlio, nome)
            else:
                scendi(figlio, prefisso)

    scendi(albero, "")
    return fuori


def _ambito_di(mappa: list[tuple[int, int, str]], riga: int) -> str:
    """L'ambito PIU' INTERNO che contiene la riga."""
    migliore, ampiezza = "<modulo>", None
    for inizio, fine, nome in mappa:
        if inizio <= riga <= fine:
            a = fine - inizio
            if ampiezza is None or a < ampiezza:
                ampiezza, migliore = a, nome
    return migliore


def chiave(modulo: str, m: Mutante) -> str:
    """L'identita' di un mutante nella linea di base.

    ⚠️ NON contiene il numero di riga, e la ragione e' che il numero di riga
    non e' una proprieta' del mutante: e' una proprieta' del file che lo
    contiene. Con la vecchia forma `file:riga  prima -> dopo`, aggiungere un
    COMMENTO spostava ogni voce sotto di esso e la sonda le riportava tutte
    come «sopravvissuti nuovi» — cioe' `nightly.yml`, che gira senza
    `continue-on-error`, diventava rosso su codice che nessuno aveva toccato.
    Misurato: nove righe di commento in `signal_outcome_service` hanno prodotto
    quattro falsi sopravvissuti, e un riassetto di `technical_score_service` ne
    avrebbe prodotti 85. Questo file registra tre volte che un cancello che
    arrossisce su codice intatto viene spento.

    `modulo::funzione#N  prima -> dopo` si sposta solo quando cambia la
    funzione che lo contiene, che e' esattamente quando ri-misurare e' giusto.
    L'ordinale `#N` conserva la risoluzione: due mutazioni identiche nella
    stessa funzione restano due voci, mentre la vecchia chiave le fondeva
    quando cadevano sulla stessa riga.

    Il numero di riga resta STAMPATO accanto ai sopravvissuti nuovi — serve a
    chi legge per arrivarci — ma non entra nell'identita'.
    """
    return f"{modulo}::{m.ambito}#{m.ordine}  {m.prima} -> {m.dopo}"


def genera(percorso: Path) -> list[Mutante]:
    originale = percorso.read_text(encoding="utf-8")
    ambiti = _mappa_ambiti(ast.parse(originale))
    visti: Counter[tuple[str, str, str]] = Counter()
    out: list[Mutante] = []
    for i in range(_quanti(originale)):
        albero = ast.parse(originale)
        r = _Riscrittore(i)
        nuovo = r.visit(albero)
        if r.applicato is None:
            continue
        ast.fix_missing_locations(nuovo)
        riga, prima, dopo = r.applicato
        ambito = _ambito_di(ambiti, riga)
        ordine = visti[(ambito, prima, dopo)]
        visti[(ambito, prima, dopo)] += 1
        out.append(Mutante(riga, prima, dopo, ast.unparse(nuovo), ambito, ordine))
    return out


def _suite_verde(test: list[str]) -> bool:
    esito = subprocess.run(
        [sys.executable, "-m", "pytest", *test, "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
        cwd=RADICE, capture_output=True, text=True,
    )
    return esito.returncode == 0


def _albero_pulito(percorsi: list[str]) -> bool:
    esito = subprocess.run(
        ["git", "status", "--porcelain", "--", *percorsi],
        cwd=RADICE, capture_output=True, text=True,
    )
    return esito.returncode == 0 and not esito.stdout.strip()


#: Arretrato MISURATO di sopravvissuti, come le altre linee di base del repo.
#:
#: ⚠️ Perche' una baseline e non uno zero: la prima passata completa ha dato
#: 130 mutanti, 43 uccisi, **87 sopravvissuti**. Pretendere lo zero
#: significherebbe scrivere decine di test in un colpo o — molto piu'
#: probabile — dichiarare equivalenti ottantacinque mutanti che non lo sono,
#: cioe' mentire in un file che esiste per dire la verita'. E un cancello che
#: nasce rosso viene spento, come `eslint.hooks.config.js` registra gia'.
#:
#: Il contratto e' quindi il CRICCHETTO, identico a quello di a11y e del codice
#: morto: il numero non puo' CRESCERE. Ogni test nuovo che uccide un mutante
#: stringe la linea.
LINEA_BASE = RADICE / "app" / "data" / "mutation_baseline.json"

_PERCHE_BASE = (
    "Sopravvissuti MISURATI, non tollerati per sempre: ogni riga qui e' una "
    "riga eseguita dai test la cui CORRETTEZZA nessuno verifica. Il cancello "
    "impedisce che il numero cresca; cala scrivendo test. Rigenerare con "
    "--scrivi solo DOPO aver ucciso qualcosa, mai per far passare la CI. "
    "CHIAVE: modulo::funzione#N  prima -> dopo. Senza numero di riga di "
    "proposito — con la vecchia forma un COMMENTO spostava ogni voce sotto "
    "di se' e la notturna arrossiva su codice intatto."
)


def _carica_conteggi() -> dict[str, dict[str, int]]:
    """I conteggi per modulo gia' noti, o vuoto.

    ⚠️ Il tipo si CONTROLLA, non si spera. Il valore letto finisce in
    `{**noti, **conteggi}` dentro `--scrivi`: un file in cui `per_modulo` non
    e' un oggetto — JSON valido, quindi nessuna eccezione — farebbe esplodere
    la scrittura a meta', dopo che i mutanti sono gia' stati eseguiti. Con un
    dizionario vuoto la passata si comporta come se non sapesse niente, che e'
    la verita'.
    """
    try:
        d = json.loads(LINEA_BASE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    per_modulo = d.get("per_modulo") if isinstance(d, dict) else None
    return per_modulo if isinstance(per_modulo, dict) else {}


def _carica_base() -> set[str]:
    try:
        return set(json.loads(LINEA_BASE.read_text(encoding="utf-8")).get("sopravvissuti", []))
    except (FileNotFoundError, ValueError):
        return set()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modulo", help="sottostringa per restringere i bersagli")
    ap.add_argument("--scrivi", action="store_true",
                    help="rigenera la linea di base invece di confrontarla")
    args = ap.parse_args()

    bersagli = {
        m: t for m, t in BERSAGLI.items()
        if not args.modulo or args.modulo in m
    }
    if not bersagli:
        print("nessun bersaglio", file=sys.stderr)
        return 2

    # ⚠️ Precondizione non negoziabile: questo strumento SCRIVE nei file
    # sorgente e li ripristina. Se l'albero e' gia' sporco, un'interruzione
    # renderebbe impossibile distinguere le modifiche di qualcuno da un
    # ripristino mancato — e si finirebbe per buttare lavoro vero, che e' il
    # modo in cui `git checkout --` ha gia' distrutto due volte codice in
    # questo repo.
    if not _albero_pulito(list(bersagli)):
        print("I file bersaglio hanno modifiche non committate. Committa o "
              "metti da parte prima: questo strumento li riscrive.", file=sys.stderr)
        return 2

    sopravvissuti: list[str] = []
    # La chiave non porta il numero di riga (vedi `chiave()`), ma chi legge
    # un sopravvissuto nuovo deve poterci arrivare: si tiene a parte.
    righe_di: dict[str, int] = {}
    totale = 0
    conteggi: dict[str, dict[str, int]] = {}
    for modulo, test in bersagli.items():
        percorso = RADICE / modulo
        # ⚠️ BYTE, non testo. `read_text`/`write_text` traducono i fine riga:
        # su Windows un file CRLF tornava LF dopo il ripristino, `git status`
        # lo segnalava come modificato, e il controllo «albero pulito» in fondo
        # dichiarava un ripristino mancato che non era mai avvenuto. Effetto:
        # la linea di base NON veniva mai scritta, e il messaggio finiva su
        # stderr dove una pipeline con `tail` lo nascondeva.
        #
        # Ripristinare i byte esatti e' anche l'unica definizione onesta di
        # «ripristinato»: un file che differisce di un carattere non e' quello
        # di prima.
        originale_byte = percorso.read_bytes()
        mutanti = genera(percorso)
        print(f"\n{modulo}: {len(mutanti)} mutanti, test {' '.join(test)}")

        # Controllo negativo obbligatorio: se la suite bersaglio e' gia' rossa,
        # OGNI mutante risulterebbe "ucciso" e il rapporto sarebbe un verde
        # che non significa niente.
        if not _suite_verde(test):
            print("  la suite bersaglio e' gia' rossa: salto", file=sys.stderr)
            continue

        try:
            for n, m in enumerate(mutanti, 1):
                percorso.write_text(m.sorgente, encoding="utf-8")
                vivo = _suite_verde(test)
                stato = "SOPRAVVISSUTO" if vivo else "ucciso"
                totale += 1
                if vivo:
                    k = chiave(modulo, m)
                    sopravvissuti.append(k)
                    righe_di[k] = m.riga
                print(f"  [{n}/{len(mutanti)}] riga {m.riga}: {m.prima} -> {m.dopo}  {stato}")
        finally:
            # Sempre, anche su eccezione o interruzione, e byte per byte.
            percorso.write_bytes(originale_byte)
        vivi_qui = sum(1 for s in sopravvissuti if s.startswith(modulo))
        conteggi[modulo] = {"mutanti": len(mutanti), "uccisi": len(mutanti) - vivi_qui}

    print(f"\n{'=' * 60}")
    uccisi = totale - len(sopravvissuti)
    # ⚠️ Il confronto va RISTRETTO ai moduli effettivamente mutati.
    #
    # Con `--modulo fx_service` la linea di base contiene anche i 59
    # sopravvissuti di `setup_service`, che questa passata non ha nemmeno
    # guardato: confrontarli tutti faceva riportare «76 mutanti ora uccisi»
    # dove i veri erano venti. Un numero che si congratula da solo e' la forma
    # esatta di difetto che questo strumento esiste per trovare — e ce l'aveva
    # dentro.
    prefissi = tuple(bersagli)
    base = {b for b in _carica_base() if b.startswith(prefissi)}
    nuovi = [s for s in sopravvissuti if s not in EQUIVALENTI and s not in base]
    uccisi_da_poco = sorted(base - set(sopravvissuti))
    print(
        f"mutanti: {totale}, uccisi {uccisi}, sopravvissuti {len(set(sopravvissuti))} "
        f"unici ({len(EQUIVALENTI)} equivalenti dichiarati, {len(base)} in linea di base)"
    )

    if not _albero_pulito(list(bersagli)):
        print("\nATTENZIONE: un file non e' stato ripristinato. Controlla `git diff`.",
              file=sys.stderr)
        return 2

    if args.scrivi:
        LINEA_BASE.parent.mkdir(parents=True, exist_ok=True)
        LINEA_BASE.write_text(json.dumps({
            "_perche": _PERCHE_BASE,
            # ⚠️ I totali sono PER MODULO, non globali.
            #
            # Scriverli come numeri unici faceva sovrascrivere il totale
            # dell'intera passata con quello di una mirata: dopo un
            # `--modulo fx_service` il file diceva «27 mutanti» invece di 130,
            # e il test che pretende una passata vera diventava rosso. Tenendo
            # il conto per modulo, una passata mirata aggiorna solo la propria
            # voce e il totale resta la somma di cio' che si sa.
            "per_modulo": {
                **{k: v for k, v in _carica_conteggi().items() if k not in bersagli},
                **conteggi,
            },
            # ⚠️ L'insieme resta anche se la chiave e' ora UNICA (l'ordinale
            # `#N` distingue due mutazioni identiche nello stesso ambito, che
            # la vecchia chiave `file:riga` fondeva): il confronto a valle usa
            # un insieme, e scrivere una lista con doppioni farebbe divergere
            # il conteggio scritto da quello confrontato — e' gia' successo
            # con le chiavi del rapporto sul codice morto.
            # ⚠️ Si conservano i sopravvissuti dei moduli NON eseguiti in
            # questa passata: con `--modulo` la riscrittura li cancellerebbe,
            # e la prossima passata completa li riporterebbe come NUOVI. Una
            # linea di base che dimentica non e' un cricchetto.
            "sopravvissuti": sorted(
                {s for s in sopravvissuti if s not in EQUIVALENTI}
                | {b for b in _carica_base() if not b.startswith(prefissi)}
            ),
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"linea di base scritta: {len(sopravvissuti)} sopravvissuti")
        return 0

    if uccisi_da_poco:
        print(f"\n{len(uccisi_da_poco)} mutanti ORA UCCISI: stringi la linea di base "
              "con --scrivi")
        for s in uccisi_da_poco[:8]:
            print(f"  {s}")

    if nuovi:
        print("\nSOPRAVVISSUTI NUOVI - righe la cui correttezza nessun test verifica:",
              file=sys.stderr)
        for s in nuovi:
            dove = f"   (riga {righe_di[s]})" if s in righe_di else ""
            print(f"  {s}{dove}", file=sys.stderr)
        print(
            "\nOgnuno e' una lacuna o un equivalente, e la differenza va DECISA, "
            "non rimandata: se e' una lacuna si scrive il test, se e' equivalente "
            "si mette in EQUIVALENTI con la ragione. Un sopravvissuto senza "
            "spiegazione e' indistinguibile da un difetto.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
