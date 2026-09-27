"""L'estrattore delle azioni degli analisti, su titoli VERI (FA-107).

I titoli vengono dalla cache delle notizie in produzione del 2026-09-28, e il
risultato atteso di ciascuno e' stato letto a mano dal testo, non preso da cio'
che l'estrattore rendeva. Il modulo non era mai stato eseguito da un test; la
prima esecuzione sul corpus vero ha trovato tre difetti sistematici:

1. la forma PASSIVA — «Price Target Hiked to $760», «price target raised by
   UBS», «Upped Its Price Target» — finiva in «Maintains»: sei titoli su
   venticinque, cioe' un rialzo mostrato come una conferma;
2. i tagli di rating nella forma «cuts Rollins to Neutral», «cuts Twilio to
   Reduce» non venivano riconosciuti affatto;
3. nei riepiloghi di mercato — «Humana Jumps on Barclays Upgrade…;
   UnitedHealth Nudges Higher» — l'azione su un titolo veniva attribuita a un
   ALTRO, perche' il suo nome compare nel titolo, ma in un'altra frase.
"""
import pytest

from app.services import news_analyst_extractor as x

DATA = "2026-09-20T12:00:00Z"


def _estrai(titolo: str, ticker: str, societa: str):
    return x.extract_from_news_item(
        titolo, published_at_iso=DATA, ticker=ticker, company_name=societa,
    )


# (titolo, ticker, societa', (firma, azione, target))
CORRETTI = [
    ("Carnival hit by rising oil costs as BofA cuts price target",
     "CCL", "Carnival Corp", ("Bank of America", "target_down", None)),
    ("Nike Stock In Focus As Barclays Cuts Price Target To $48 Ahead Of Q1 Earnings",
     "NKE", "Nike Inc.", ("Barclays", "target_down", 48.0)),
    ("Bank of America Just Cut Its Price Target on UPS",
     "UPS", "United Parcel Service Inc.", ("Bank of America", "target_down", None)),
    ("Ciena Stock Jumps Following Evercore ISI Upgrade to Outperform",
     "CIEN", "Ciena Corp", ("Evercore ISI", "up", None)),
    ("Bank of America Securities Maintains Buy on Altria Group (MO)",
     "MO", "Altria Group Inc.", ("Bank of America", "main", None)),
    ("Meta Spikes 7% as Wells Fargo Lifts Price Target to $796 Ahead of Connect; "
     "Alphabet Nudges Higher, Microsoft Holds Flat",
     "META", "Meta Platforms Inc.", ("Wells Fargo", "target_up", 796.0)),
    ("Humana Jumps 7% on Barclays Upgrade and $515 Target; UnitedHealth Nudges Higher",
     "HUM", "Humana Inc.", ("Barclays", "up", 515.0)),
]

# La forma passiva: il target viene PRIMA del verbo.
PASSIVI = [
    ("Teledyne Technologies (TDY) Price Target Hiked to $760 as Needham Bets on "
     "Defense and Short-Cycle Recovery",
     "TDY", "Teledyne Technologies Inc", ("Needham", "target_up", 760.0)),
    ("Newmont price target raised by UBS on capital returns outlook",
     "NEM", "Newmont Corp", ("UBS", "target_up", None)),
    ("Amgen price target raised by Jefferies to $410 after positive Sjogren's data",
     "AMGN", "Amgen Inc.", ("Jefferies", "target_up", 410.0)),
    ("Okta price target lifted to $220 as BofA sees stronger AI agent positioning",
     "OKTA", "Okta Inc.", ("Bank of America", "target_up", 220.0)),
    ("Bank of America Just Upped Its Price Target on AMD Stock",
     "AMD", "Advanced Micro Devices Inc.", ("Bank of America", "target_up", None)),
    ("Nebius Stock Soars 8% as BNP Paribas Delivers Massive Price Target Hike",
     "NBIS", "Nebius Group N.V.", ("BNP Paribas", "target_up", None)),
]

# Tagli di rating nella forma «taglia X a <giudizio>».
TAGLI = [
    ("Piper Sandler cuts Rollins to Neutral, citing AI search disruption",
     "ROL", "Rollins Inc.", ("Piper Sandler", "down", None)),
    ("HSBC cuts Twilio to Reduce, says Muse rally has gone too far",
     "TWLO", "Twilio Inc.", ("HSBC", "down", None)),
    ("Comcast Slips as KeyBanc Cuts to Underweight on Broadband Share Losses; "
     "AT&T and Verizon Hold Steady",
     "CMCSA", "Comcast Corp", ("KeyBanc", "down", None)),
]

# Non sono azioni di un analista su QUESTO titolo: devono restare None.
MAI = [
    # nessuna banca d'affari: guidance, raccolte, obiettivi dell'azienda stessa
    ("Cintas Raises Full-Year Outlook Following Fiscal First-Quarter Beat", "CTAS", "Cintas Corp"),
    ("Kinross Gold Updates Production Outlook, Raises Capital Return Target", "KGC", "Kinross Gold Corp"),
    ("ADARx Pharmaceuticals raises $446 million in upsized IPO", "ABBV", "AbbVie Inc."),
    ("Goldman Sachs Cuts Global Smartphone Shipment Forecasts for 2026-28",
     "GS", "Goldman Sachs Group Inc."),
    # riepiloghi di mercato: l'azione e' su un ALTRO titolo
    ("Nebius Surges 6%, CoreWeave Treads Water as JPMorgan Upgrade Flags Rising "
     "Compute Pricing; IREN Slides 4%", "IREN", "IREN Ltd"),
    ("Humana Jumps 7% on Barclays Upgrade and $515 Target; UnitedHealth Nudges Higher",
     "UNH", "UnitedHealth Group Inc."),
    ("Meta Spikes 7% as Wells Fargo Lifts Price Target to $796 Ahead of Connect; "
     "Alphabet Nudges Higher, Microsoft Holds Flat", "MSFT", "Microsoft Corp"),
    ("Comcast Slips as KeyBanc Cuts to Underweight on Broadband Share Losses; "
     "AT&T and Verizon Hold Steady", "VZ", "Verizon Communications Inc."),
    # un titolo che parla di un'altra societa' e basta
    ("Newmont price target raised by UBS on capital returns outlook", "B", "Barrick Mining Corp"),
    # la banca che firma la nota NON e' il soggetto: il suo nome e' nel titolo
    # perche' e' lei ad aver alzato il target di Nebius
    ("Nebius Stock Soars 8% as BNP Paribas Delivers Massive Price Target Hike",
     "BNP.PA", "BNP Paribas SA"),
]


@pytest.mark.parametrize(("titolo", "ticker", "societa", "atteso"), CORRETTI + PASSIVI + TAGLI)
def test_azione_estratta(titolo, ticker, societa, atteso) -> None:
    m = _estrai(titolo, ticker, societa)
    assert m is not None, f"nessuna azione estratta da: {titolo}"
    assert (m.firm, m.action, m.current_price_target) == atteso
    assert m.date == "2026-09-20"


@pytest.mark.parametrize(("titolo", "ticker", "societa"), MAI)
def test_nessuna_azione(titolo, ticker, societa) -> None:
    assert _estrai(titolo, ticker, societa) is None


def test_la_forma_passiva_non_e_una_conferma() -> None:
    """Il difetto (1) visto dal lato di chi legge: un rialzo non deve MAI
    comparire come «Maintains»."""
    for titolo, ticker, societa, _ in PASSIVI:
        assert _estrai(titolo, ticker, societa).price_target_action == "Raises", titolo


def test_il_giudizio_del_taglio_si_legge() -> None:
    m = _estrai(*TAGLI[2][:3])
    assert m.to_grade == "Underperform"


def test_il_corpus_esercita_ogni_caso() -> None:
    """Il pavimento: un elenco svuotato renderebbe i test parametrici veri di
    niente."""
    assert len(CORRETTI) >= 7 and len(PASSIVI) >= 6 and len(TAGLI) >= 3 and len(MAI) >= 9


# ── doppioni rispetto alle azioni strutturate ─────────────────────────────


class _Azione:
    def __init__(self, firm: str, date: str) -> None:
        self.firm, self.date = firm, date


def test_stessa_firma_entro_tre_giorni_e_un_doppione() -> None:
    m = _estrai(*CORRETTI[0][:3])
    assert x.is_duplicate_of_existing(m, [_Azione("Bank of America Securities", "2026-09-18")])
    assert not x.is_duplicate_of_existing(m, [_Azione("Bank of America", "2026-09-14")])
    assert not x.is_duplicate_of_existing(m, [_Azione("Barclays", "2026-09-20")])
    assert not x.is_duplicate_of_existing(m, [])
