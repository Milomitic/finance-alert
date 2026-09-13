"""I periodi degli indicatori hanno UN proprietario, e si verifica alla sorgente.

⚠️ CLAUDE.md dichiarava `FIXED_*` fonte unica dei periodi da mesi. Non lo erano:
un censimento ha trovato QUATTORDICI chiamate con il periodo scritto a mano, su
cinque file — EMA 20/50/200 e RSI 14 riscritti ovunque.

E la causa non era disattenzione, era la COLLOCAZIONE. Le costanti vivevano in
`app/services/timeframe_service.py`, cioe' dentro un servizio che importa
SQLAlchemy, i modelli e loguru. `app/signals/context.py` e' calcolo puro
(numpy, pandas, `app.indicators`): per leggere il numero 200 avrebbe dovuto
tirarsi dentro mezzo stack. La costante NON ERA IMPORTABILE da chi ne aveva
bisogno, quindi nessuno la importava, quindi ognuno la riscriveva.

Ora stanno in `app/indicators/periods.py`, un modulo foglia senza dipendenze.

⚠️ Questo test guarda la SORGENTE e non il comportamento, ed e' l'unico modo:
un consumatore scrive `from ... import FIXED_EMA_SLOW`, che lega il VALORE al
momento dell'import — sostituire la costante a runtime non cambierebbe niente
in chi l'ha gia' importata, quindi nessun test di comportamento puo' distinguere
`ema(close, FIXED_EMA_SLOW)` da `ema(close, 200)`. Stessa forma del censimento
delle classi mobile in `mobileLayout.test.ts`, e per la stessa ragione.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.indicators import periods

#: Chiamate a un indicatore il cui periodo e' un LETTERALE.
#: ⚠️ `adx` non c'e' di proposito: il suo periodo non e' fra i `FIXED_*`, e
#: aggiungerlo significherebbe inventare una politica che nessuno ha deciso.
_CHIAMATA = re.compile(
    r"\b(ema|ema_indicator|rsi|rsi_indicator|bollinger|macd)\s*\(\s*[^,()]+,\s*(\d+)"
)

_RADICE = Path(__file__).resolve().parents[1] / "app"


def _sorgenti() -> list[Path]:
    return [f for f in sorted(_RADICE.rglob("*.py")) if f.name != "periods.py"]


def test_nessun_periodo_di_indicatore_e_scritto_a_mano() -> None:
    """Il censimento, e il difetto che chiude.

    ⚠️ Un periodo cablato non rompe niente OGGI — il numero e' lo stesso. Rompe
    il giorno in cui qualcuno ritara: la EMA lenta cambia in un posto e
    l'etichetta di regime del magazzino esiti resta a 200, cosi' il grafico e la
    misura d'efficacia parlano di due tendenze diverse senza che niente lo dica.
    """
    colpevoli: list[str] = []
    for f in _sorgenti():
        for i, riga in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if riga.lstrip().startswith("#"):
                continue
            for m in _CHIAMATA.finditer(riga):
                colpevoli.append(f"{f.relative_to(_RADICE.parent)}:{i}  {m.group(0)}")
    assert not colpevoli, (
        "periodi di indicatore scritti a mano invece di importati da "
        "`app.indicators.periods`:\n  " + "\n  ".join(colpevoli)
    )


def test_le_costanti_sono_DAVVERO_usate() -> None:
    """⚠️ Il pavimento, senza il quale il test sopra e' vero di niente.

    Se un giorno qualcuno smettesse di chiamare gli indicatori con un periodo
    esplicito — o se il riconoscitore smettesse di funzionare — il censimento
    passerebbe su zero righe e sembrerebbe un successo. Si pretende quindi che
    i nomi compaiano davvero nei consumatori, e da almeno due file distinti.
    """
    usi: dict[str, set[str]] = {}
    for f in _sorgenti():
        testo = f.read_text(encoding="utf-8")
        for nome in ("FIXED_EMA_SLOW", "FIXED_EMA_MID", "FIXED_RSI_PERIOD"):
            if re.search(rf"\b{nome}\b", testo):
                usi.setdefault(nome, set()).add(f.name)
    for nome in ("FIXED_EMA_SLOW", "FIXED_EMA_MID", "FIXED_RSI_PERIOD"):
        assert len(usi.get(nome, ())) >= 2, f"{nome} usata in {usi.get(nome)}"


def test_il_modulo_dei_periodi_non_ha_dipendenze() -> None:
    """⚠️ E' la proprieta' da cui dipende tutto il resto: solo un modulo FOGLIA
    e' importabile da ogni livello, compreso il calcolo puro dei segnali. Se
    qualcuno gli aggiunge un import di `app.services` o di SQLAlchemy, la
    costante torna non-importabile e il difetto si riapre da solo — con il
    censimento ancora verde, perche' i consumatori attuali continuerebbero a
    funzionare.

    ⚠️ Si legge l'AST e non le righe. La prima versione cercava le righe che
    iniziano con `import`, e ha trovato un falso positivo dentro la propria
    docstring: una frase andata a capo la cui continuazione cominciava con
    «import». Un test che protegge una proprieta' STRUTTURALE deve leggere la
    struttura, non il testo che le somiglia.
    """
    albero = ast.parse((_RADICE / "indicators" / "periods.py").read_text(encoding="utf-8"))
    moduli = sorted(
        {a.name.split(".")[0] for n in ast.walk(albero)
         if isinstance(n, ast.Import) for a in n.names}
        | {(n.module or "").split(".")[0] for n in ast.walk(albero)
           if isinstance(n, ast.ImportFrom)}
    )
    assert moduli in ([], ["__future__"]), f"periods.py ha acquisito dipendenze: {moduli}"


def test_i_valori_canonici_restano_quelli_dichiarati() -> None:
    """⚠️ NON e' un congelamento della taratura: ritarare resta una decisione
    legittima, e allora questo test si aggiorna insieme. Fissa che i tre valori
    che CLAUDE.md nomina esplicitamente (20/50/200) siano ORDINATI e distinti —
    veloce < media < lenta — perche' scambiarli produrrebbe numeri plausibili e
    un trend letto al contrario.
    """
    assert periods.FIXED_EMA_FAST < periods.FIXED_EMA_MID < periods.FIXED_EMA_SLOW
