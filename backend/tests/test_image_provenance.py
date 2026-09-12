"""La provenienza dell'immagine: cosa il pod puo' DIMOSTRARE di se'.

Il 12 settembre il livello Docker che scarica le patch di sicurezza Debian e'
risultato inerte da 24 giorni: `cache-from: type=gha` lo riusava perche' il suo
comando non nominava niente di variabile. Nessuno se ne e' accorto finche' trivy
non ha rotto la pipeline con tre CVE CRITICAL gia' corrette a monte.

Il file `/etc/image-provenance.json` e' l'asserzione POSITIVA che mancava:
scritto dentro lo stesso RUN delle patch, se il livello non gira la data resta
vecchia e chiunque la legga se ne accorge — la CI, questi test, e il cruscotto.
"""

import json
from datetime import date

import pytest

from app.services import image_provenance as ip


def _scrivi(tmp_path, payload: str):
    p = tmp_path / "image-provenance.json"
    p.write_text(payload, encoding="utf-8")
    return p


class TestLettura:
    def test_legge_le_due_date(self, tmp_path):
        p = _scrivi(tmp_path, json.dumps({
            "apt_security_date": "2026-09-12",
            "built_at": "2026-09-12T14:39:33Z",
        }))
        prov = ip.read_provenance(p)
        assert prov is not None
        assert prov.apt_security_date == date(2026, 9, 12)
        assert prov.built_at is not None

    def test_file_assente_non_esplode_e_non_inventa(self, tmp_path):
        """In sviluppo il file non c'e'. Deve dire NON SO, non una data finta:
        una data inventata qui e' peggio dell'assenza, perche' verrebbe letta
        come prova di freschezza."""
        assert ip.read_provenance(tmp_path / "manca.json") is None

    def test_unknown_non_e_una_data(self, tmp_path):
        """`ARG APT_SECURITY_DATE=unknown` e' il default del Dockerfile: e' il
        valore che compare quando qualcuno costruisce a mano SENZA passare il
        build-arg, cioe' esattamente il caso in cui non si sa nulla."""
        p = _scrivi(tmp_path, json.dumps({
            "apt_security_date": "unknown", "built_at": "unknown",
        }))
        prov = ip.read_provenance(p)
        assert prov is not None
        assert prov.apt_security_date is None
        assert prov.built_at is None

    def test_json_corrotto_degrada_a_none(self, tmp_path):
        assert ip.read_provenance(_scrivi(tmp_path, "{non json")) is None


class TestEta:
    def test_eta_in_giorni(self):
        assert ip.apt_age_days(date(2026, 9, 12), oggi=date(2026, 9, 19)) == 7

    def test_senza_data_l_eta_e_ignota(self):
        assert ip.apt_age_days(None, oggi=date(2026, 9, 19)) is None

    def test_una_data_fresca_NON_e_stantia(self):
        """Il controllo negativo dell'asserzione sotto: senza questo, una
        funzione che restituisce sempre `True` passerebbe il test successivo."""
        assert ip.is_stale(date(2026, 9, 19), oggi=date(2026, 9, 19)) is False
        assert ip.is_stale(date(2026, 9, 13), oggi=date(2026, 9, 19)) is False

    def test_oltre_la_soglia_e_stantia(self):
        oltre = ip.STALE_AFTER_DAYS + 1
        vecchia = date(2026, 9, 19).toordinal() - oltre
        assert ip.is_stale(date.fromordinal(vecchia), oggi=date(2026, 9, 19)) is True

    def test_data_ignota_non_e_stantia_ma_nemmeno_fresca(self):
        """Assente non e' zero: `None` non deve diventare «va tutto bene».
        Chi legge deve poter distinguere «costruita ieri» da «non lo so»."""
        assert ip.is_stale(None, oggi=date(2026, 9, 19)) is None


class TestSoglia:
    def test_la_soglia_e_dichiarata_e_ragionevole(self):
        """Non un numero magico: l'immagine si ricostruisce a ogni push, quindi
        una soglia sotto i pochi giorni suonerebbe per un weekend tranquillo."""
        assert 3 <= ip.STALE_AFTER_DAYS <= 14


@pytest.mark.parametrize("payload", ['{"built_at": "2026-09-12T00:00:00Z"}', "{}"])
def test_campi_mancanti_non_esplodono(tmp_path, payload):
    prov = ip.read_provenance(_scrivi(tmp_path, payload))
    assert prov is not None
    assert prov.apt_security_date is None
