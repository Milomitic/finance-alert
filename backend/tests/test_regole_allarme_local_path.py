"""Nessuna regola d'allarme legge i volumi del kubelet (FA-015).

Su `local-path` un PVC e' una directory sul disco del nodo, e il kubelet
riporta per ogni PVC le cifre di QUEL filesystem: misurato il 2026-09-15, tutti
i PVC del cluster dichiaravano 26,83 GB usati su 31,6 GB — identici a `df /` —
mentre Loki ne occupava 122 MB. Una regola su `kubelet_volume_stats_*` misura il
nodo con il nome di un volume, e il rimedio che suggerisce e' quello sbagliato.

La regola che c'era non ha mai potuto scattare comunque: regex ancorata
`loki.*` contro un PVC chiamato `storage-loki-0`. Caricata, sana, `inactive`.
"""

from pathlib import Path

REGOLE = Path(__file__).resolve().parents[2] / "infra" / "observability"


def _espressioni(testo: str) -> str:
    """Il file senza i commenti, che la regola rimossa la NOMINANO."""
    return "\n".join(r for r in testo.splitlines() if not r.lstrip().startswith("#"))


def test_nessuna_regola_legge_i_volumi_del_kubelet():
    file = sorted(REGOLE.glob("*.yaml"))
    # Il pavimento: senza file la lista vuota sotto sarebbe vera di niente.
    assert any(f.name == "app-alert-rules.yaml" for f in file), REGOLE

    offensori = [
        f.name for f in file
        if "kubelet_volume_stats" in _espressioni(f.read_text(encoding="utf-8"))
    ]

    assert offensori == [], (
        "su local-path i volume_stats del kubelet descrivono il DISCO DEL NODO, "
        f"non il volume: {offensori}"
    )


def test_il_disco_del_nodo_resta_sorvegliato():
    """Togliere la regola del PVC e' giusto solo perche' questa esiste."""
    testo = _espressioni((REGOLE / "app-alert-rules.yaml").read_text(encoding="utf-8"))
    assert "alert: FinanceAlertNodeRootFilling" in testo
    assert 'node_filesystem_avail_bytes{mountpoint="/"' in testo
