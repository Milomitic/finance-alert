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
        "tests/test_setup_service.py",
        "tests/test_setup_conversion_outcomes.py",
        "tests/test_setup_earnings_window.py",
        "tests/test_setup_expiry_ceiling.py",
        "tests/test_setup_return_stats.py",
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
        "tests/test_detector_performance.py",
        "tests/test_effective_sample.py",
        "tests/test_equity_curve_direction.py",
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
    ],
    # La de-correlazione per famiglia: N segnali correlati devono contare ~1.3,
    # non N. Se smette di funzionare la confluenza si gonfia in silenzio.
    "app/services/confluence_service.py": [
        "tests/test_confluence_service.py",
        "tests/test_confluence_strength_field.py",
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
    "app/services/image_provenance.py:47  7 -> 8":
        "STALE_AFTER_DAYS: il test sulla soglia asserisce un INTERVALLO "
        "ragionevole (3-14) e non il valore esatto, di proposito — il numero e' "
        "una taratura, non un contratto, e fissarlo renderebbe rosso ogni "
        "ripensamento legittimo. Otto giorni resta una soglia sensata.",
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
    "app/services/technical_score_service.py:52  Gt -> GtE":
        "`int(price > f)` e i suoi due gemelli. Il bordo si raggiunge solo dove "
        "il prezzo eguaglia ESATTAMENTE la EMA, cioe' su una serie "
        "perfettamente piatta — dove il punteggio di trend non significa "
        "niente in nessuna delle due forme. ⚠️ E separare «un punto su quattro» "
        "da «zero punti» richiederebbe di limitare la miscela 0,6+0,4·adx_w: "
        "si congelerebbe una taratura per fissare un caso degenere. Il test "
        "`test_una_serie_ferma_NON_legge_come_trend` tiene la guardia larga "
        "(sotto la neutralita') proprio per non farlo.",
    "app/services/technical_score_service.py:120  GtE -> Gt":
        "`if n >= 10` davanti a `vol.iloc[-10:].mean()`. Con ESATTAMENTE dieci "
        "barre le due strade calcolano la stessa media, perche' `vol[-10:]` E' "
        "`vol`. Identiche, non simili — e comunque `partial_for` sbarra sotto "
        "le trenta.",
    "app/services/technical_score_service.py:147  Gt -> GtE":
        "`num / wsum if wsum > 0 else None`. `wsum` somma i pesi delle parti "
        "non nulle e `_blended_return` e' chiamata solo da `partial_for`, che "
        "richiede almeno trenta barre: `_ret(close, min(63, n-1))` ha sempre un "
        "k valido, quindi wsum >= 0,4. Il ramo in cui le due forme divergono "
        "(wsum == 0) e' irraggiungibile.",
    "app/services/technical_score_service.py:239  GtE -> Gt":
        "`Alert.triggered_at >= cutoff` dove cutoff e' `now() - 14 giorni`, un "
        "istante al microsecondo. Un avviso marcato ESATTAMENTE su quel "
        "microsecondo non e' costruibile in modo deterministico: la differenza "
        "esiste e non e' osservabile.",
    "app/services/technical_score_service.py:347  1 -> 2":
        "`.limit(1)` su una `where(stock_id == ...)` dove `stock_id` e' la "
        "CHIAVE PRIMARIA di technical_scores: al massimo esiste una riga, e "
        "`.first()` prende comunque la prima. Il limite e' cintura oltre alle "
        "bretelle, non un filtro.",
    "app/services/technical_score_service.py:373  1 -> 2":
        "Il gemello alla rilettura finale, stessa ragione: chiave primaria, "
        "una riga al massimo.",
    # ── signal_outcome_service: dieci superstiti, tutti dichiarati ───────
    #
    # ⚠️ Il modulo e' passato da 20 a 47 uccisi su 57. Questi dieci non sono i
    # "difficili": sono quelli che NESSUN test onesto puo' uccidere, perche'
    # fissarli congelerebbe una taratura o proverebbe un caso irraggiungibile.
    "app/services/signal_outcome_service.py:31  200 -> 201":
        "`_REGIME_EMA`: la EMA lenta e' una TARATURA (CLAUDE.md la fissa a 200 "
        "insieme a 20 e 50) e l'etichetta che ne esce e' grossolana, bull o "
        "bear. Un periodo in piu' sposta il confine solo per le barre gia' "
        "appiccicate alla linea. ⚠️ Il rilievo vero qui non e' il mutante: e' "
        "che `timeframe_service.FIXED_EMA_SLOW` esiste come fonte unica "
        "dichiarata e questo modulo non la importa.",
    "app/services/signal_outcome_service.py:97  GtE -> Gt":
        "`OhlcvDaily.date >= since` dove `since` e' gia' il minimo trigger "
        "MENO dieci giorni di margine: un giorno in piu' o in meno resta "
        "dentro il margine, e il docstring dimostra che la finestra non cambia "
        "il riferimento al giorno del segnale.",
    "app/services/signal_outcome_service.py:121  900 -> 901":
        "SQLite tronca a 999 parametri legati, e 900 e' il margine sotto quel "
        "tetto. Il vincolo e' `< 999`, non `== 900`: 901 lo soddisfa "
        "identicamente. Un test che fissasse 900 impedirebbe di alzarlo a 950 "
        "senza guadagnare niente.",
    "app/services/signal_outcome_service.py:121  Gt -> GtE":
        "Stesso margine, dal lato dell'operatore: con esattamente 900 titoli "
        "entrambe le strade funzionano (900 < 999).",
    "app/services/signal_outcome_service.py:160  LtE -> Lt":
        "`if len(cs) <= horizon: continue`. Col bordo esatto — serie lunga "
        "quanto l'orizzonte — il ramo che passa produce `cs[:-horizon]` vuoto "
        "e `cs[horizon:]` vuoto, quindi zero osservazioni: le due forme fanno "
        "LA STESSA COSA, non due cose simili.",
    "app/services/signal_outcome_service.py:166  False -> True":
        "`zip(..., strict=False)`. I due lati sono filtrati dalla stessa "
        "maschera `ok`, quindi hanno lunghezza uguale per costruzione e "
        "`strict` non ha niente da rilevare. ⚠️ Nota: `strict=True` sarebbe "
        "codice MIGLIORE — trasformerebbe un troncamento silenzioso in un "
        "errore — ma nessun test puo' distinguerli finche' l'invariante "
        "regge, quindi resta un miglioramento, non una lacuna.",
    "app/services/signal_outcome_service.py:234  10 -> 11":
        "I dieci giorni di margine con cui la finestra dell'universo parte "
        "prima del primo trigger. E' un cuscinetto: allargarlo di un giorno "
        "carica una barra in piu' e non cambia nessun numero calcolato.",
    "app/services/signal_outcome_service.py:278  Lt -> LtE":
        "La guardia `ti < len(ema_arr)` e' IRRAGGIUNGIBILE nel ramo mutato: "
        "`ema_arr` ha la lunghezza di `cs` e `ti` viene da `_trigger_index`, "
        "che rende solo indici validi di `cs`. `ti == len` non accade.",
    "app/services/signal_outcome_service.py:278  Gt -> GtE":
        "`ema_arr[ti] >= 0`. La EMA all'indice `ti` include `cs[ti]` col peso "
        "alpha, e `entry > 0` e' gia' stato verificato venti righe sopra: "
        "quindi `ema_arr[ti] >= alpha * cs[ti] > 0` sempre. Il bordo zero non "
        "esiste.",
    "app/services/signal_outcome_service.py:278  And -> Or":
        "Col primo termine sempre vero (vedi sopra), `and` e `or` "
        "corto-circuitano allo stesso risultato. Il caso in cui divergono — "
        "`ema_arr` vuoto — richiede zero barre, che `_trigger_index` ha gia' "
        "escluso rendendo None.",
    "app/core/security.py:22  12 -> 13":
        "Il fattore di costo di bcrypt e' una TARATURA, non un contratto: 13 e' "
        "piu' forte di 12, e qualunque asserzione onesta e' un pavimento "
        "(`>= 12`), che per definizione non puo' bocciare un valore piu' alto. "
        "⚠️ Il mutante che conterebbe e' `12 -> 11` e questo operatore non lo "
        "genera: incrementa soltanto. Il pavimento e' fissato a mano in "
        "`test_il_costo_di_bcrypt_non_scende_sotto_12`.",
    "app/core/security.py:52  16 -> 17":
        "La lunghezza del nonce di sessione. Il jti e' OPACO — non viene mai "
        "letto, confrontato o misurato dal prodotto: serve solo a rendere ogni "
        "accesso revocabile per conto suo, quindi piu' entropia non e' un "
        "comportamento diverso. Stessa asimmetria del costo bcrypt: `16 -> 15` "
        "sarebbe un indebolimento vero e la sonda non lo produce; il pavimento "
        "sta in `test_il_nonce_di_sessione_ha_almeno_16_byte_di_entropia`.",
    "app/services/image_provenance.py:54  True -> False":
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


def genera(percorso: Path) -> list[Mutante]:
    originale = percorso.read_text(encoding="utf-8")
    out: list[Mutante] = []
    for i in range(_quanti(originale)):
        albero = ast.parse(originale)
        r = _Riscrittore(i)
        nuovo = r.visit(albero)
        if r.applicato is None:
            continue
        ast.fix_missing_locations(nuovo)
        riga, prima, dopo = r.applicato
        out.append(Mutante(riga, prima, dopo, ast.unparse(nuovo)))
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
    "--scrivi solo DOPO aver ucciso qualcosa, mai per far passare la CI."
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
                    sopravvissuti.append(f"{modulo}:{m.riga}  {m.prima} -> {m.dopo}")
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
            # ⚠️ Deduplicati: la chiave "file:riga  prima -> dopo" non e' unica
            # — due mutazioni identiche sulla stessa riga la condividono — e il
            # confronto usa un insieme. Senza `set` il conteggio scritto e
            # quello confrontato divergerebbero, come e' gia' successo con le
            # chiavi del rapporto sul codice morto.
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
            print(f"  {s}", file=sys.stderr)
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
