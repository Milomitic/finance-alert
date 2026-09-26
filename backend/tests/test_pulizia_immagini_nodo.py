"""La pulizia delle immagini del nodo scatta PRIMA dell'allarme sul disco (FA-101).

Con i valori predefiniti di kubelet (85/80%) le immagini inutilizzate si
cancellavano solo oltre l'85% di disco, che e' esattamente la soglia di
`FinanceAlertNodeRootFilling` (critico, meno del 15% libero). Misurato il
2026-09-26: 69 immagini dell'app in cache, 37 GB di containerd, disco dal 31%
al 66% in undici giorni — ogni push scarica un'immagine nuova. L'allarme
sarebbe suonato proprio mentre kubelet liberava spazio.

La configurazione vive in due posti: scritta a mano sul nodo vivo e verificata
con `configz`, e in cloud-init per un nodo ricostruito. Questo test sorveglia
la seconda, che e' quella che un domani si modifica senza pensarci.

I file si leggono come testo, non con PyYAML: nel backend e' solo una
dipendenza indiretta, e un test che la importa smetterebbe di girare il giorno
in cui chi la porta la lascia.
"""

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
CLOUD_INIT = RADICE / "infra" / "terraform" / "cloud-init" / "k3s.yaml"
REGOLE = RADICE / "infra" / "observability" / "app-alert-rules.yaml"


def _blocco_drop_in() -> str:
    testo = CLOUD_INIT.read_text(encoding="utf-8")
    m = re.search(
        r"path: /var/lib/rancher/k3s/agent/etc/kubelet\.conf\.d/50-image-gc\.conf"
        r"(?P<corpo>.*?)(?:\n  - path:|\nruncmd:)",
        testo,
        re.S,
    )
    assert m, "cloud-init non scrive piu' il drop-in di kubelet per la pulizia delle immagini"
    return m.group("corpo")


def _soglia_allarme_percento() -> float:
    """Occupazione oltre la quale suona FinanceAlertNodeRootFilling."""
    testo = REGOLE.read_text(encoding="utf-8")
    i = testo.index("alert: FinanceAlertNodeRootFilling")
    m = re.search(r"\)\s*<\s*(0\.\d+)", testo[i:i + 600])
    assert m, "espressione dell'allarme sul disco non riconosciuta"
    return 100 * (1 - float(m.group(1)))


def test_il_drop_in_e_una_configurazione_di_kubelet():
    corpo = _blocco_drop_in()
    assert "kind: KubeletConfiguration" in corpo
    assert "apiVersion: kubelet.config.k8s.io/v1beta1" in corpo


def test_le_immagini_inutilizzate_scadono_per_eta():
    """Le soglie da sole lasciano accumulare fino a loro: l'eta' pulisce anche
    quando il disco e' sereno."""
    m = re.search(r"imageMaximumGCAge:\s*(\d+)h", _blocco_drop_in())
    assert m, "manca imageMaximumGCAge"
    assert 0 < int(m.group(1)) <= 7 * 24


def test_la_pulizia_scatta_sotto_la_soglia_dell_allarme_critico():
    corpo = _blocco_drop_in()
    alta = int(re.search(r"imageGCHighThresholdPercent:\s*(\d+)", corpo).group(1))
    bassa = int(re.search(r"imageGCLowThresholdPercent:\s*(\d+)", corpo).group(1))
    allarme = _soglia_allarme_percento()
    assert allarme == 85.0          # il pavimento: il test legge la regola vera
    assert bassa < alta
    # Almeno dieci punti di margine: la pulizia deve aver finito ben prima che
    # l'allarme possa suonare, non partire nello stesso istante.
    assert alta <= allarme - 10, (
        f"kubelet pulisce oltre il {alta}% e l'allarme critico suona oltre il "
        f"{allarme:.0f}%: suonerebbe mentre il nodo libera spazio"
    )


def test_i_valori_predefiniti_di_kubelet_violerebbero_la_regola():
    """Controllo negativo: con 85/80 — cio' che kubelet fa senza il drop-in —
    il margine e' zero. Senza questo, il test sopra potrebbe essere vero per un
    confronto scritto male."""
    allarme = _soglia_allarme_percento()
    assert allarme - 10 < 85
