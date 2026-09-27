#!/bin/sh
# Prima di un rilascio, aspetta che la scansione in corso finisca (FA-109).
#
# Gira come hook PreSync di ArgoCD: prima che il nuovo StatefulSet venga
# applicato, chiede all'app viva se sta scansionando. Un riavvio a meta'
# scansione la interrompe; l'app la rilancia da sola all'avvio, ma rifacendola
# da capo — ~10 minuti di lavoro e di ritardo. Misurato: 5 scansioni
# interrotte in 10 giorni, tutte da un rilascio.
#
# ⚠️ ESCE SEMPRE 0. Un hook PreSync che fallisce ferma la sincronizzazione, e
# senza un nuovo commit ArgoCD non riprova la stessa revisione: il rilascio
# resterebbe fermo IN SILENZIO — la sonda di parita' non se ne accorgerebbe,
# perche' l'immagine desiderata non cambia finche' il sync non passa. Una
# scansione rifatta costa dieci minuti; un rilascio fermo, un giorno. Quindi
# ogni caso dubbio — app giu', risposta di una versione vecchia, attesa oltre
# il tetto — lascia passare il rilascio, e lo dice nel log.
#
# La verifica e' in backend/tests/test_attesa_scansione.py, che esegue questo
# file contro un server finto.
set -u

URL="${URL:?serve URL, per esempio http://servizio:8000/api/health}"
ATTESA_MAX_S="${ATTESA_MAX_S:-900}"
PASSO_S="${PASSO_S:-20}"

inizio=$(date +%s)
while :; do
  if ! corpo=$(curl -fsS --max-time 5 "$URL" 2>/dev/null); then
    echo "app non raggiungibile ($URL): niente da proteggere, il rilascio procede"
    exit 0
  fi
  if ! printf '%s' "$corpo" | grep -Eq '"scan_running": *(true|false)'; then
    echo "la risposta non dice scan_running (app di una versione precedente): il rilascio procede"
    exit 0
  fi
  if printf '%s' "$corpo" | grep -Eq '"scan_running": *false'; then
    echo "nessuna scansione in corso: il rilascio procede"
    exit 0
  fi
  trascorsi=$(( $(date +%s) - inizio ))
  if [ "$trascorsi" -ge "$ATTESA_MAX_S" ]; then
    echo "scansione ancora in corso dopo ${trascorsi}s: il rilascio procede comunque"
    exit 0
  fi
  echo "scansione in corso (atteso ${trascorsi}s su ${ATTESA_MAX_S}s): riprovo fra ${PASSO_S}s"
  sleep "$PASSO_S"
done
