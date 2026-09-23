"""Studio di taratura del motore e fattibilita' ML (2026-09-23).

Esito e numeri: docs/superpowers/specs/2026-09-23-studio-taratura-e-ml-findings.md

DOVE STANNO I DATI
══════════════════
Fuori da git (`backend/data/studio_taratura/`, o `$STUDIO_DATI`): sono
esportazioni di PRODUZIONE e un replay di ~1 GB.

COME SI RIGENERANO, in ordine
═════════════════════════════
1. Dalla produzione, in sola lettura. ⚠️ Le serie complete NON passano dal
   container dell'app: una SELECT di 2,5 milioni di righe dentro il suo limite
   di 3 GiB e' finita in OOM (exit 137; l'app e' sopravvissuta, ma per caso).
   Si leggono dal pod di Postgres con `\\copy`, che fa streaming:

     ssh ... 'kubectl exec -n finance-alert pg-1 -c postgres -- psql -U postgres \\
        -d finance_alert -c "\\copy (select stock_id, date, open, high, low, close, volume
        from ohlcv_daily order by stock_id, date) to stdout with csv header" | gzip -6' \\
        > ohlcv_full.csv.gz

   Alert ed esiti (poche migliaia di righe) con `export_prod.py` via stdin al
   pod dell'app: TABELLA=alerts|plan_outcomes|signal_outcomes|stocks|ohlcv.
   Le serie macro (VIX, curva, credito) esistono solo nel DB locale:
   `macro.csv` da `backend/data/app.db`.
2. `python mercato.py`       variabili di mercato e benchmark (mediana!) per data
3. `python replay_ml.py 450 22`  il replay: ~2 ore su 22 processi
4. `python dataset.py`       unione, controllo casuale, esclusione barre non negoziate
5. `python coerenza.py`      il replay racconta la stessa storia del motore vivo?
6. `python tuning.py`        le leve, walk-forward
7. `python verifiche.py`     l'ipotesi PRE-REGISTRATA sul piano breve (sui soli
                              titoli fuori dalla pre-analisi) e la skill per detector
8. `python ml_study.py`      meta-labeling, walk-forward, con controlli permutati
9. `python ml_robustezza.py` / `ml_robustezza2.py <mn|sk> <tutti|pre|nuovi>`
                              la replica su gruppi di titoli disgiunti, e la scelta
                              DENTRO ciascun detector
10. `python ml_vol.py`       la controprova: la volatilita' si prevede

⚠️ `verifiche.py` e i `ml_robustezza*` leggono `preregistrazione.json`, scritto
PRIMA di vedere i titoli restanti: e' l'elenco dei 176 titoli della
pre-analisi, e rigenerarlo DOPO averli visti toglierebbe alla prova il suo
valore. Se si rifa' lo studio da zero, si rifa' anche la pre-registrazione.

Si lanciano da `backend/` con PYTHONPATH=. (il replay importa `app.signals`).
"""
import os

DATI = os.environ.get("STUDIO_DATI") or os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "studio_taratura"))
