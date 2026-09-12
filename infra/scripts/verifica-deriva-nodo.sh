#!/usr/bin/env bash
# Il nodo ESEGUE quello che cloud-init DICHIARA?
#
# ⚠️ Nasce da un caso reale e silenzioso. Il 2026-09-09 l'unit k3s portava i
# flag corretti (`--write-kubeconfig-mode 640 --write-kubeconfig-group k3s`)
# dall'8 settembre, mentre il processo in esecuzione era su dal 17 LUGLIO con
# un argv nudo: `k3s server`. I flag erano sul disco, la configurazione era
# giusta, e non era mai stata eseguita. I permessi corretti che si vedevano
# venivano da un `chmod` fatto a mano — quindi il primo riavvio li avrebbe
# ripristinati per caso, o rotti, senza che nessuno sapesse quale dei due.
#
# Una unit predisposta e MAI ESERCITATA, sull'unico nodo che regge tutto, non
# e' una correzione: e' un rischio al prossimo riavvio.
#
# ⚠️ E non si legge l'argv. k3s riscrive il proprio proctitle, quindi
# `/proc/<pid>/cmdline` mostra `k3s server` anche quando i flag sono attivi.
# Si legge il RISULTATO: il file che k3s ha prodotto. Modo 640 e gruppo k3s su
# k3s.yaml non sono i default (600 root:root), quindi solo i flag possono
# produrli.
#
# ⚠️ NON fa `chmod 600` su k3s.yaml e non lo propone. kubectl sul nodo e' un
# symlink a k3s, k3s ignora ~/.kube/config e legge /etc/rancher/k3s/k3s.yaml:
# stringerlo a 600 lascia l'utente `opc` senza credenziali leggibili e chiude
# fuori dal cluster chi opera via SSH. CLAUDE.md lo registra come lockout gia'
# avvenuto, e un audit esterno continuera' a proporlo.
#
# Sola lettura. Uscita 0 se allineato, 1 se derivato, 2 se non verificabile.
#
#   ssh -i ~/.ssh/oci_finance_alert opc@<IP> 'bash -s' < verifica-deriva-nodo.sh
set -uo pipefail

ATTESO_MODO="640"
ATTESO_GRUPPO="k3s"
KUBECONFIG_NODO="/etc/rancher/k3s/k3s.yaml"

deriva=0
nota() { printf '  %s\n' "$1"; }

echo "== Deriva fra dichiarato ed eseguito =="

# ── 1. Il file che k3s produce ──────────────────────────────────────────────
if [ ! -e "$KUBECONFIG_NODO" ]; then
  echo "NON VERIFICABILE: $KUBECONFIG_NODO non esiste."
  exit 2
fi
modo=$(stat -c '%a' "$KUBECONFIG_NODO")
gruppo=$(stat -c '%G' "$KUBECONFIG_NODO")
echo "kubeconfig: modo $modo, gruppo $gruppo (atteso $ATTESO_MODO / $ATTESO_GRUPPO)"
if [ "$modo" != "$ATTESO_MODO" ] || [ "$gruppo" != "$ATTESO_GRUPPO" ]; then
  deriva=1
  nota "DERIVA: i flag --write-kubeconfig-* non sono attivi sul k3s in esecuzione."
  nota "Il default di k3s e' 600 root:root; 640 root:k3s puo' venire SOLO dai flag."
  nota "Riavviare k3s applicherebbe l'unit: 'sudo systemctl restart k3s'."
  nota "NON risolvere con chmod a mano: nasconderebbe la deriva lasciandola viva."
fi

# ── 2. L'unit sul disco dichiara i flag? ────────────────────────────────────
unit=$(systemctl cat k3s 2>/dev/null || true)
if [ -z "$unit" ]; then
  nota "unit k3s non leggibile: salto il confronto con il dichiarato."
else
  if printf '%s' "$unit" | grep -q -- "--write-kubeconfig-mode"; then
    echo "unit: i flag kubeconfig sono DICHIARATI"
  else
    deriva=1
    echo "unit: i flag kubeconfig NON sono dichiarati"
    nota "Qui il disco e il processo concordano, ma entrambi divergono da"
    nota "cloud-init/k3s.yaml. Va riallineata l'unit, non il file."
  fi
fi

# ── 3. Da quanto gira, contro da quando l'unit e' stata scritta ─────────────
# ⚠️ E' questo il confronto che avrebbe scoperto il caso di settembre: un
# processo piu' VECCHIO della propria configurazione non l'ha mai letta.
avvio=$(systemctl show k3s -p ActiveEnterTimestampMonotonic --value 2>/dev/null || echo 0)
unit_path=$(systemctl show k3s -p FragmentPath --value 2>/dev/null || true)
if [ -n "$unit_path" ] && [ -e "$unit_path" ]; then
  mtime_unit=$(stat -c '%Y' "$unit_path")
  avvio_epoch=$(date -d "$(systemctl show k3s -p ActiveEnterTimestamp --value)" +%s 2>/dev/null || echo 0)
  echo "unit modificata: $(date -d @"$mtime_unit" '+%Y-%m-%d %H:%M')"
  echo "k3s attivo dal:  $(date -d @"$avvio_epoch" '+%Y-%m-%d %H:%M')"
  if [ "$avvio_epoch" -gt 0 ] && [ "$mtime_unit" -gt "$avvio_epoch" ]; then
    deriva=1
    nota "DERIVA: l'unit e' piu' RECENTE del processo in esecuzione."
    nota "Cioe' la configurazione attuale non e' mai stata eseguita."
  fi
fi
: "${avvio:=0}"

# ── 4. Il gruppo esiste e opc ne fa parte ──────────────────────────────────
if getent group "$ATTESO_GRUPPO" >/dev/null 2>&1; then
  membri=$(getent group "$ATTESO_GRUPPO" | cut -d: -f4)
  echo "gruppo $ATTESO_GRUPPO: membri [$membri]"
  case ",$membri," in
    *,opc,*) : ;;
    *) deriva=1; nota "DERIVA: opc non e' nel gruppo $ATTESO_GRUPPO; kubectl via SSH fallira'." ;;
  esac
else
  deriva=1
  nota "DERIVA: il gruppo $ATTESO_GRUPPO non esiste (cloud-init lo crea con groupadd -f)."
fi

echo
if [ "$deriva" -eq 0 ]; then
  echo "ALLINEATO: cio' che gira corrisponde a cio' che e' dichiarato."
else
  echo "DERIVA RILEVATA. Vedi le note sopra."
fi
exit "$deriva"
