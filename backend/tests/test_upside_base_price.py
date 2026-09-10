"""Un upside senza la propria base non e un numero, e un'ambiguita.

Sulla pagina di DG lo stesso target analisti rendeva **+11.5%** in una scheda e
**+4.3%** in un'altra, e l'aritmetica lo conferma da sola: 138,93/124,57 contro
138,93/133,21. Le due schede partivano da prezzi diversi e nessuna delle due
diceva quale, quindi la contraddizione non era leggibile a schermo — sembravano
due misure diverse invece che la stessa misura su due basi.

Le basi in circolo sulla stessa pagina erano quattro: il prezzo live
dell'intestazione, `pt.current` di yfinance vecchio quanto la cache dei
fondamentali, l'ultima `OhlcvDaily.close` letta qui, e una quarta in
`pillars.py`.

⚠️ La correzione NON e imporre una base sola. Obbligherebbe ogni consumatore a
dipendere dal prezzo live, che ha un breaker e puo essere `STALE`. La
correzione e che ogni confronto **dichiari la propria**, che e la stessa regola
gia applicata ai tassi: un numero senza il proprio denominatore non si
pubblica.
"""
from types import SimpleNamespace

from app.services.score_service.quality_extras import quality_extras


def _fundamentals(target: float | None = 138.93):
    return SimpleNamespace(
        micro=SimpleNamespace(
            recommendation_mean=2.5,
            number_of_analyst_opinions=29,
            audit_risk=None, board_risk=None,
            compensation_risk=None, overall_risk=None,
        ),
        price_target=SimpleNamespace(mean=target, current=133.21),
    )


class TestLUpsideViaggiaConLaSuaBase:
    def test_la_base_e_pubblicata_insieme_alla_percentuale(self):
        out = quality_extras(_fundamentals(), 124.57, "2026-09-09")

        an = out["analyst"]
        assert an["target_upside_pct"] == 11.5
        assert an["upside_base_price"] == 124.57
        assert an["upside_base_as_of"] == "2026-09-09"

    def test_non_esiste_una_percentuale_senza_base(self):
        # E il punto dell'intero test: la coppia non si separa mai. Se un
        # giorno l'upside comparisse senza `upside_base_price`, il difetto
        # sarebbe tornato per intero.
        out = quality_extras(_fundamentals(), 124.57, "2026-09-09")

        an = out["analyst"]
        assert ("target_upside_pct" in an) == ("upside_base_price" in an)

    def test_senza_prezzo_non_si_pubblica_nessun_upside(self):
        out = quality_extras(_fundamentals(), None, None)

        an = out["analyst"]
        assert "target_upside_pct" not in an
        assert "upside_base_price" not in an
        # Il target resta: e un dato della fonte e non dipende da un prezzo.
        assert an["price_target"] == 138.93

    def test_un_prezzo_a_zero_non_diventa_una_divisione(self):
        out = quality_extras(_fundamentals(), 0.0, "2026-09-09")

        assert "target_upside_pct" not in out["analyst"]


class TestLaBaseCambiaLaPercentuale:
    def test_due_basi_diverse_danno_due_numeri_diversi(self):
        """La riproduzione esatta di cio che si vedeva a schermo.

        Lo stesso target, due prezzi base, due percentuali. Entrambe corrette,
        ed e proprio per questo che senza la base non si puo dire quale delle
        due schede stia sbagliando: nessuna delle due sbaglia.
        """
        header_base = quality_extras(_fundamentals(), 124.57, "2026-09-09")
        analyst_base = quality_extras(_fundamentals(), 133.21, "2026-09-05")

        assert header_base["analyst"]["target_upside_pct"] == 11.5
        assert analyst_base["analyst"]["target_upside_pct"] == 4.3
        # E ognuna porta la propria, quindi la differenza e spiegabile.
        assert (
            header_base["analyst"]["upside_base_price"]
            != analyst_base["analyst"]["upside_base_price"]
        )

    def test_la_data_e_facoltativa_ma_il_prezzo_no(self):
        # Una base senza data e comunque una base: dice su COSA e calcolata,
        # anche se non dice di quando. Meglio di niente, peggio di entrambe.
        out = quality_extras(_fundamentals(), 124.57, None)

        an = out["analyst"]
        assert an["upside_base_price"] == 124.57
        assert "upside_base_as_of" not in an
