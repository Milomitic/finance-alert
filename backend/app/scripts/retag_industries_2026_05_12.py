"""One-shot re-tag of `stocks.industry` after the May 2026 taxonomy audit.

What changed in the taxonomy (see `industry_normalizer.py` docstring):

 - Capital Goods split into Aerospace & Defense / Machinery / Electrical
   Equipment / Industrial Conglomerates & Distribution.
 - Software & Services lost Payments & Fintech to its own bucket.
 - Four homonyms renamed (Energy/Materials/Real Estate/Utilities →
   Oil, Gas & Consumable Fuels / Chemicals & Mining / Equity REITs /
   Electric, Water & Gas Utilities).
 - ~40 new yfinance label variants added to the synonyms map so they
   stop landing in OTHER.

What this script does
---------------------
1. Re-walks every seed CSV (sp500.csv, ftsemib.csv, …) and builds a
   `ticker → raw_industry_label` lookup from the source-of-truth
   CSVs.
2. For each stock in DB, picks the raw label from the lookup and
   re-runs `canonical_industry()`. This achieves three things at once:
     - moves Capital Goods rows to their split children;
     - moves payments rows out of Software & Services;
     - rescues the ~165 rows that were stranded in OTHER because
       yfinance uses labels like "Software - Application" that the
       old synonyms map didn't know.
3. For stocks that are NOT in any seed CSV (the 154 NULLs — mostly
   UK FTSE 100 + Chinese SSE rows that were added by a different
   ingestion path), applies a hand-curated `_TICKER_OVERRIDES` map
   keyed by ticker.

Idempotent: running it twice is safe — the second run finds nothing
to change.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.retag_industries_2026_05_12
"""
from __future__ import annotations

import csv
import os
from collections import Counter

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services.industry_normalizer import (
    AEROSPACE_DEFENSE,
    AUTOMOBILES,
    BANKS,
    CANONICAL_INDUSTRIES,
    CAPITAL_GOODS_OTHER,
    CHEMICALS_MINING,
    COMMERCIAL_SERVICES,
    CONSUMER_DURABLES,
    CONSUMER_SERVICES,
    DIVERSIFIED_FINANCIALS,
    ELECTRICAL_EQUIPMENT,
    FOOD_BEVERAGE_TOBACCO,
    FOOD_STAPLES_RETAIL,
    HEALTH_CARE_EQUIPMENT,
    HOUSEHOLD_PRODUCTS,
    INSURANCE,
    MACHINERY,
    MEDIA,
    OIL_GAS_FUELS,
    PAYMENTS_FINTECH,
    PHARMACEUTICALS,
    REITS,
    RETAILING,
    SEMICONDUCTORS,
    SOFTWARE_SERVICES,
    TECH_HARDWARE,
    TELECOM,
    TRANSPORTATION,
    UTILITIES_REGULATED,
    canonical_industry,
)

# Path to the seed dir relative to this file's package
_HERE = os.path.dirname(os.path.abspath(__file__))
_SEED_DIR = os.path.normpath(os.path.join(_HERE, "..", "data", "seed"))

# Pre-computed set of canonical labels — used as the guard for the
# "rerun canonical_industry on existing label" tier (see `run()`).
_CANONICAL_SET = set(CANONICAL_INDUSTRIES)


# ─── Hand-curated overrides for tickers NOT in any seed CSV ───────────────
# Built from a manual audit of the 154 NULL-industry rows. Most are
# FTSE 100 (.L) and HKEX (.HK) tickers ingested by catalog_refresh
# without an industry column. Keys are tickers as they appear in DB.
_TICKER_OVERRIDES: dict[str, str] = {
    # ─── UK Communication Services (.L) ────────────────────────────────
    "AAF.L":   TELECOM,                  # Airtel Africa
    "AUTO.L":  MEDIA,                    # Autotrader Group (online classifieds)
    "BT-A.L":  TELECOM,                  # BT Group
    "INF.L":   MEDIA,                    # Informa (publishing & events)
    "PSON.L":  MEDIA,                    # Pearson (education publishing)
    "REL.L":   MEDIA,                    # RELX (info & analytics)
    "RMV.L":   MEDIA,                    # Rightmove (online classifieds)
    "VOD.L":   TELECOM,                  # Vodafone Group

    # ─── UK Consumer Discretionary (.L, .MI) ───────────────────────────
    "BC.MI":   CONSUMER_DURABLES,        # Brunello Cucinelli (luxury apparel)
    "ENT.L":   CONSUMER_SERVICES,        # Entain (gambling)
    "GAW.L":   CONSUMER_DURABLES,        # Games Workshop (leisure goods)
    "HWDN.L":  RETAILING,                # Howdens Joinery (specialty retail)
    "IAG.L":   TRANSPORTATION,           # International Airlines Group
    "IHG.L":   CONSUMER_SERVICES,        # IHG Hotels & Resorts
    "JD.L":    RETAILING,                # JD Sports
    "KGF.L":   RETAILING,                # Kingfisher (home improvement)
    "LTMC.MI": CONSUMER_SERVICES,        # Lottomatica (gambling)
    "NXT.L":   RETAILING,                # Next plc
    "ULVR.L":  HOUSEHOLD_PRODUCTS,       # Unilever (CPG)
    "WTB.L":   CONSUMER_SERVICES,        # Whitbread (hotels & restaurants)

    # ─── UK Consumer Staples (.L) ──────────────────────────────────────
    "ABF.L":   FOOD_BEVERAGE_TOBACCO,    # Associated British Foods
    "BATS.L":  FOOD_BEVERAGE_TOBACCO,    # British American Tobacco
    "BKG.L":   REITS,                    # Berkeley Group (homebuilding)
    "BTRW.L":  REITS,                    # Barratt Redrow (homebuilding)
    "CCEP.L":  FOOD_BEVERAGE_TOBACCO,    # Coca-Cola Europacific Partners
    "CCH.L":   FOOD_BEVERAGE_TOBACCO,    # Coca-Cola HBC
    "DGE.L":   FOOD_BEVERAGE_TOBACCO,    # Diageo
    "IMB.L":   FOOD_BEVERAGE_TOBACCO,    # Imperial Brands
    "MKS.L":   RETAILING,                # Marks & Spencer
    "PSN.L":   REITS,                    # Persimmon (homebuilding)
    "RKT.L":   HOUSEHOLD_PRODUCTS,       # Reckitt
    "SBRY.L":  FOOD_STAPLES_RETAIL,      # Sainsbury's
    "TSCO.L":  FOOD_STAPLES_RETAIL,      # Tesco

    # ─── Italian Energy (.MI) ──────────────────────────────────────────
    "SPM.MI":  OIL_GAS_FUELS,            # Saipem (oilfield services)
    "TEN.MI":  OIL_GAS_FUELS,            # Tenaris (steel pipes for O&G)

    # ─── Financials: banks, asset managers, insurance (.L, .MI, HK) ────
    "3968.HK": BANKS,                    # China Merchants Bank
    "ADM.L":   INSURANCE,                # Admiral Group
    "ALW.L":   DIVERSIFIED_FINANCIALS,   # Alliance Witan (investment trust)
    "AV.L":    INSURANCE,                # Aviva
    "BARC.L":  BANKS,                    # Barclays
    "BEZ.L":   INSURANCE,                # Beazley
    "BGEO.L":  BANKS,                    # Lion Finance Group (ex Bank of Georgia)
    "BMPS.MI": BANKS,                    # Monte dei Paschi
    "FBK.MI":  BANKS,                    # FinecoBank
    "FCIT.L":  DIVERSIFIED_FINANCIALS,   # F&C Investment Trust
    "HSBA.L":  BANKS,                    # HSBC
    "HSX.L":   INSURANCE,                # Hiscox
    "ICG.L":   DIVERSIFIED_FINANCIALS,   # ICG (private debt)
    "IGG.L":   DIVERSIFIED_FINANCIALS,   # IG Group (CFD broker)
    "III.L":   DIVERSIFIED_FINANCIALS,   # 3i Group
    "LGEN.L":  INSURANCE,                # Legal & General
    "LLOY.L":  BANKS,                    # Lloyds Banking Group
    "LSEG.L":  DIVERSIFIED_FINANCIALS,   # LSE Group (exchange)
    "MNG.L":   INSURANCE,                # M&G plc
    "NWG.L":   BANKS,                    # NatWest Group
    "PCT.L":   DIVERSIFIED_FINANCIALS,   # Polar Capital Tech Trust
    "PRU.L":   INSURANCE,                # Prudential plc
    "PSH.L":   DIVERSIFIED_FINANCIALS,   # Pershing Square Holdings
    "SDLF.L":  INSURANCE,                # Standard Life (life ins)
    "SDR.L":   DIVERSIFIED_FINANCIALS,   # Schroders (asset mgmt)
    "SMT.L":   DIVERSIFIED_FINANCIALS,   # Scottish Mortgage Trust
    "STAN.L":  BANKS,                    # Standard Chartered
    "STJ.L":   DIVERSIFIED_FINANCIALS,   # St. James's Place (wealth mgmt)

    # ─── UK Health Care (.L) ───────────────────────────────────────────
    "AZN.L":   PHARMACEUTICALS,          # AstraZeneca
    "CTEC.L":  HEALTH_CARE_EQUIPMENT,    # Convatec (medical devices)
    "GSK.L":   PHARMACEUTICALS,          # GSK plc
    "HLN.L":   HOUSEHOLD_PRODUCTS,       # Haleon (consumer health → CPG)
    "SN.L":    HEALTH_CARE_EQUIPMENT,    # Smith & Nephew

    # ─── Industrials (.HK, .L, .MI) ────────────────────────────────────
    "0175.HK": AUTOMOBILES,              # Geely Auto
    "0241.HK": PHARMACEUTICALS,          # Alibaba Health (e-pharmacy)
    "0267.HK": CAPITAL_GOODS_OTHER,      # CITIC Limited (conglomerate)
    "0285.HK": TECH_HARDWARE,            # BYD Electronics
    "0288.HK": FOOD_BEVERAGE_TOBACCO,    # WH Group (pork)
    "0291.HK": FOOD_BEVERAGE_TOBACCO,    # China Resources Beer
    "0300.HK": CONSUMER_DURABLES,        # Midea Group (appliances)
    "0316.HK": TRANSPORTATION,           # Orient Overseas (container shipping)
    "0322.HK": FOOD_BEVERAGE_TOBACCO,    # Tingyi (instant noodles)
    "0669.HK": CONSUMER_DURABLES,        # Techtronic Industries (power tools)
    "0762.HK": TELECOM,                  # China Unicom
    "0868.HK": CHEMICALS_MINING,         # Xinyi Glass
    "0881.HK": RETAILING,                # Zhongsheng (auto dealer)
    "0981.HK": SEMICONDUCTORS,           # SMIC
    "0992.HK": TECH_HARDWARE,            # Lenovo
    "AVIO.MI": AEROSPACE_DEFENSE,        # Avio
    "BAB.L":   AEROSPACE_DEFENSE,        # Babcock International
    "BNZL.L":  CAPITAL_GOODS_OTHER,      # Bunzl (distribution)
    "BZU.MI":  CHEMICALS_MINING,         # Buzzi (cement)
    "CPG.L":   CONSUMER_SERVICES,        # Compass Group (contract catering)
    "DCC.L":   CAPITAL_GOODS_OTHER,      # DCC plc (sales/marketing & distribution)
    "DPLM.L":  CAPITAL_GOODS_OTHER,      # Diploma (specialty distribution)
    "EXPN.L":  COMMERCIAL_SERVICES,      # Experian (credit data)
    "FCT.MI":  AEROSPACE_DEFENSE,        # Fincantieri (shipbuilding & defense)
    "IMI.L":   MACHINERY,                # IMI plc (engineering)
    "ITRK.L":  COMMERCIAL_SERVICES,      # Intertek (testing & cert)
    "IVG.MI":  MACHINERY,                # Iveco (trucks → industrial machinery)
    "MRO.L":   CAPITAL_GOODS_OTHER,      # Melrose Industries
    "RTO.L":   COMMERCIAL_SERVICES,      # Rentokil Initial (facilities)
    "SMIN.L":  CAPITAL_GOODS_OTHER,      # Smiths Group (diversified)
    "SPX.L":   MACHINERY,                # Spirax Group (industrial steam/fluids)
    "WEIR.L":  MACHINERY,                # Weir Group (mining equipment)

    # ─── Information Technology (.L, .MI) ──────────────────────────────
    "HLMA.L":  TECH_HARDWARE,            # Halma (safety sensors)
    "SGE.L":   SOFTWARE_SERVICES,        # Sage Group
    "STMMI.MI": SEMICONDUCTORS,          # STMicroelectronics

    # ─── Materials (.L) → Chemicals & Mining ───────────────────────────
    "AAL.L":   CHEMICALS_MINING,         # Anglo American
    "ANTO.L":  CHEMICALS_MINING,         # Antofagasta (copper)
    "CRDA.L":  CHEMICALS_MINING,         # Croda (specialty chemicals)
    "EDV.L":   CHEMICALS_MINING,         # Endeavour Mining (gold)
    "FRES.L":  CHEMICALS_MINING,         # Fresnillo (silver)
    "MNDI.L":  CHEMICALS_MINING,         # Mondi (packaging)
    "RIO.L":   CHEMICALS_MINING,         # Rio Tinto

    # ─── Real Estate (.HK, .L) → Equity REITs ──────────────────────────
    "0012.HK": REITS,                    # Henderson Land
    "0101.HK": REITS,                    # Hang Lung Properties
    "0823.HK": REITS,                    # Link REIT
    "0960.HK": REITS,                    # Longfor Properties
    "1109.HK": REITS,                    # China Resources Land
    "1209.HK": REITS,                    # CR Mixc Lifestyle
    "1997.HK": REITS,                    # Wharf REIC
    "BBOX.L":  REITS,                    # Tritax Big Box REIT
    "BLND.L":  REITS,                    # British Land
    "LAND.L":  REITS,                    # Land Securities
    "LMP.L":   REITS,                    # LondonMetric Property
    "SGRO.L":  REITS,                    # Segro

    # ─── Utilities (.HK, .L, .MI) → Electric, Water & Gas Utilities ────
    "0002.HK": UTILITIES_REGULATED,      # CLP Holdings
    "0003.HK": UTILITIES_REGULATED,      # Hong Kong & China Gas
    "0836.HK": UTILITIES_REGULATED,      # China Resources Power
    "1038.HK": UTILITIES_REGULATED,      # CKI Holdings
    "A2A.MI":  UTILITIES_REGULATED,      # A2A
    "CNA.L":   UTILITIES_REGULATED,      # Centrica
    "MTLN.L":  UTILITIES_REGULATED,      # Metlen Energy & Metals
    "NG.L":    UTILITIES_REGULATED,      # National Grid
    "SSE.L":   UTILITIES_REGULATED,      # SSE plc
    "SVT.L":   UTILITIES_REGULATED,      # Severn Trent
    "UU.L":    UTILITIES_REGULATED,      # United Utilities

    # ─── Chinese SSE (.SS) — no sector either, best-effort by name ────
    "600104.SS": AUTOMOBILES,             # SAIC Motor
    "600111.SS": CHEMICALS_MINING,            # China Northern Rare Earth
    "600150.SS": TRANSPORTATION,              # CSSC Holdings (shipbuilding)
    "600436.SS": PHARMACEUTICALS,             # Pien Tze Huang (TCM)
    "600809.SS": FOOD_BEVERAGE_TOBACCO,       # Xinghuacun Fen Wine
    "600893.SS": AEROSPACE_DEFENSE,           # AECC Aviation Power
    "601390.SS": CAPITAL_GOODS_OTHER,         # China Railway Group (constr)
    "601669.SS": CAPITAL_GOODS_OTHER,         # PowerChina (construction)
    "601899.SS": CHEMICALS_MINING,            # Zijin Mining
    "601919.SS": TRANSPORTATION,              # Cosco Shipping
    "688041.SS": SEMICONDUCTORS,              # Hygon Information Tech
    "688111.SS": SOFTWARE_SERVICES,           # Kingsoft Office
    "688599.SS": TECH_HARDWARE,               # Trina Solar (solar mfg)
    "688981.SS": SEMICONDUCTORS,              # SMIC (Shanghai listing)

    # ─── European misc (.PA, .BR, .DE) without industry in CSV ─────────
    "AI.PA":    CHEMICALS_MINING,        # Air Liquide (industrial gases)
    "ARGX.BR":  PHARMACEUTICALS,         # Argenx (biotech)
    "DBK.DE":   BANKS,                   # Deutsche Bank
    "DG.PA":    CAPITAL_GOODS_OTHER,     # Vinci (construction & concessions)
    "ENR.DE":   ELECTRICAL_EQUIPMENT,    # Siemens Energy
    "SGO.PA":   CHEMICALS_MINING,        # Saint-Gobain (building materials)
    "VOW.DE":   AUTOMOBILES,             # Volkswagen Group

    # ─── US S&P 500 currently in old "Capital Goods" — manual split ────
    # The seed CSV stub for S&P 500 only covers 25 names; the rest were
    # ingested via catalog_refresh and need a split decision here.
    "AXON": AEROSPACE_DEFENSE,           # Axon Enterprise (Tasers, body cams)
    "GD":   AEROSPACE_DEFENSE,           # General Dynamics
    "GE":   AEROSPACE_DEFENSE,           # GE Aerospace
    "HWM":  AEROSPACE_DEFENSE,           # Howmet Aerospace
    "LHX":  AEROSPACE_DEFENSE,           # L3Harris
    "LMT":  AEROSPACE_DEFENSE,           # Lockheed Martin
    "NOC":  AEROSPACE_DEFENSE,           # Northrop Grumman
    "RTX":  AEROSPACE_DEFENSE,           # RTX Corp (Raytheon)
    "TDG":  AEROSPACE_DEFENSE,           # TransDigm
    "TXT":  AEROSPACE_DEFENSE,           # Textron

    "CMI":  MACHINERY,                   # Cummins (engines)
    "DE":   MACHINERY,                   # Deere & Co (ag machinery)
    "DOV":  MACHINERY,                   # Dover Corp
    "IEX":  MACHINERY,                   # IDEX (fluid handling)
    "IR":   MACHINERY,                   # Ingersoll Rand (air compressors)
    "ITW":  MACHINERY,                   # Illinois Tool Works
    "NDSN": MACHINERY,                   # Nordson (precision dispensing)
    "PH":   MACHINERY,                   # Parker Hannifin (motion control)
    "POOL": MACHINERY,                   # Pool Corp (pool supplies)
    "SNA":  MACHINERY,                   # Snap-on (hand tools)
    "SWK":  MACHINERY,                   # Stanley Black & Decker
    "WAB":  MACHINERY,                   # Wabtec (rail equipment)

    "AME":  ELECTRICAL_EQUIPMENT,        # Ametek (electronic instruments)
    "AOS":  ELECTRICAL_EQUIPMENT,        # A.O. Smith (water heaters)
    "EMR":  ELECTRICAL_EQUIPMENT,        # Emerson Electric
    "ETN":  ELECTRICAL_EQUIPMENT,        # Eaton
    "GEV":  ELECTRICAL_EQUIPMENT,        # GE Vernova (power equipment)
    "GNRC": ELECTRICAL_EQUIPMENT,        # Generac generators
    "HUBB": ELECTRICAL_EQUIPMENT,        # Hubbell
    "ROK":  ELECTRICAL_EQUIPMENT,        # Rockwell Automation
    "VRT":  ELECTRICAL_EQUIPMENT,        # Vertiv (data center cooling/power)
    "XYL":  ELECTRICAL_EQUIPMENT,        # Xylem (water tech)

    # Remaining "industrials-misc" — building products, HVAC contractors,
    # MRO distribution, infrastructure services, conglomerates.
    "ALLE": CAPITAL_GOODS_OTHER,         # Allegion (door security)
    "BLDR": CAPITAL_GOODS_OTHER,         # Builders FirstSource (lumber distrib)
    "CARR": CAPITAL_GOODS_OTHER,         # Carrier (HVAC)
    "EME":  CAPITAL_GOODS_OTHER,         # Emcor (mechanical contractor)
    "FER":  CAPITAL_GOODS_OTHER,         # Ferrovial (infrastructure)
    "FIX":  CAPITAL_GOODS_OTHER,         # Comfort Systems USA (HVAC)
    "FTV":  CAPITAL_GOODS_OTHER,         # Fortive (diversified)
    "GPC":  CAPITAL_GOODS_OTHER,         # Genuine Parts (auto distrib)
    "GWW":  CAPITAL_GOODS_OTHER,         # W.W. Grainger (MRO distrib)
    "J":    CAPITAL_GOODS_OTHER,         # Jacobs Solutions (engineering)
    "JCI":  CAPITAL_GOODS_OTHER,         # Johnson Controls
    "LII":  CAPITAL_GOODS_OTHER,         # Lennox (HVAC)
    "MAS":  CAPITAL_GOODS_OTHER,         # Masco (building products)
    "OTIS": CAPITAL_GOODS_OTHER,         # Otis (elevators)
    "PNR":  CAPITAL_GOODS_OTHER,         # Pentair (water solutions)
    "PWR":  CAPITAL_GOODS_OTHER,         # Quanta Services (infra)
    "TT":   CAPITAL_GOODS_OTHER,         # Trane (HVAC)
    "URI":  CAPITAL_GOODS_OTHER,         # United Rentals (equipment rental)

    # Mis-classified — these aren't Capital Goods at all
    "ISRG": HEALTH_CARE_EQUIPMENT,       # Intuitive Surgical (medical devices)
    "ASML": SEMICONDUCTORS,              # ASML (semicon equipment)
    "LRCX": SEMICONDUCTORS,              # Lam Research (semicon equipment)

    # ─── US "Other" recovery (Financials, Health Care, Industrials) ────
    # The first version of this script had a rerun-tier bug that
    # punted ~141 stocks with valid-but-not-synonym-keyed canonical
    # labels into OTHER. These mappings recover them by ticker.
    #
    # Asset managers / IB / brokers → Diversified Financials
    "AMP": DIVERSIFIED_FINANCIALS, "APO": DIVERSIFIED_FINANCIALS,
    "ARES": DIVERSIFIED_FINANCIALS, "BEN": DIVERSIFIED_FINANCIALS,
    "BK": DIVERSIFIED_FINANCIALS, "BX": DIVERSIFIED_FINANCIALS,
    "COF": DIVERSIFIED_FINANCIALS, "FDS": DIVERSIFIED_FINANCIALS,
    "IBKR": DIVERSIFIED_FINANCIALS, "IVZ": DIVERSIFIED_FINANCIALS,
    "KKR": DIVERSIFIED_FINANCIALS, "MS": DIVERSIFIED_FINANCIALS,
    "NTRS": DIVERSIFIED_FINANCIALS, "RJF": DIVERSIFIED_FINANCIALS,
    "SCHW": DIVERSIFIED_FINANCIALS, "STT": DIVERSIFIED_FINANCIALS,
    "SYF": DIVERSIFIED_FINANCIALS, "TROW": DIVERSIFIED_FINANCIALS,
    # Exchanges + ratings + indices providers → Diversified Financials
    "CBOE": DIVERSIFIED_FINANCIALS, "CME": DIVERSIFIED_FINANCIALS,
    "ICE": DIVERSIFIED_FINANCIALS, "NDAQ": DIVERSIFIED_FINANCIALS,
    "MCO": DIVERSIFIED_FINANCIALS, "MSCI": DIVERSIFIED_FINANCIALS,
    "SPGI": DIVERSIFIED_FINANCIALS,
    # Payment processors / paytech → Payments & Fintech
    "CPAY": PAYMENTS_FINTECH, "FIS": PAYMENTS_FINTECH,
    "FISV": PAYMENTS_FINTECH, "GPN": PAYMENTS_FINTECH,
    "JKHY": PAYMENTS_FINTECH, "XYZ": PAYMENTS_FINTECH,  # Block (ex Square)

    # Health Care Equipment & Services
    "ABT": HEALTH_CARE_EQUIPMENT, "ALGN": HEALTH_CARE_EQUIPMENT,
    "BAX": HEALTH_CARE_EQUIPMENT, "BDX": HEALTH_CARE_EQUIPMENT,
    "BSX": HEALTH_CARE_EQUIPMENT, "CAH": HEALTH_CARE_EQUIPMENT,
    "CI":  HEALTH_CARE_EQUIPMENT, "CNC": HEALTH_CARE_EQUIPMENT,
    "COO": HEALTH_CARE_EQUIPMENT, "COR": HEALTH_CARE_EQUIPMENT,
    "CVS": HEALTH_CARE_EQUIPMENT, "DGX": HEALTH_CARE_EQUIPMENT,
    "DHR": HEALTH_CARE_EQUIPMENT, "DVA": HEALTH_CARE_EQUIPMENT,
    "DXCM": HEALTH_CARE_EQUIPMENT, "ELV": HEALTH_CARE_EQUIPMENT,
    "EW":  HEALTH_CARE_EQUIPMENT, "GEHC": HEALTH_CARE_EQUIPMENT,
    "HCA": HEALTH_CARE_EQUIPMENT, "HSIC": HEALTH_CARE_EQUIPMENT,
    "HUM": HEALTH_CARE_EQUIPMENT, "IDXX": HEALTH_CARE_EQUIPMENT,
    "IQV": HEALTH_CARE_EQUIPMENT, "LH":  HEALTH_CARE_EQUIPMENT,
    "MCK": HEALTH_CARE_EQUIPMENT, "MDT": HEALTH_CARE_EQUIPMENT,
    "MTD": HEALTH_CARE_EQUIPMENT, "PODD": HEALTH_CARE_EQUIPMENT,
    "RMD": HEALTH_CARE_EQUIPMENT, "RVTY": HEALTH_CARE_EQUIPMENT,
    "SOLV": HEALTH_CARE_EQUIPMENT, "STE": HEALTH_CARE_EQUIPMENT,
    "SYK": HEALTH_CARE_EQUIPMENT, "TECH": HEALTH_CARE_EQUIPMENT,
    "TMO": HEALTH_CARE_EQUIPMENT, "UHS": HEALTH_CARE_EQUIPMENT,
    "WAT": HEALTH_CARE_EQUIPMENT, "WST": HEALTH_CARE_EQUIPMENT,
    "ZBH": HEALTH_CARE_EQUIPMENT,
    # Pharmaceuticals, Biotech & Life Sciences
    "A":   PHARMACEUTICALS,  # Agilent (life sci tools)
    "ABBV": PHARMACEUTICALS, "ALNY": PHARMACEUTICALS,
    "BIIB": PHARMACEUTICALS, "BMY":  PHARMACEUTICALS,
    "CRL":  PHARMACEUTICALS, "INCY": PHARMACEUTICALS,
    "INSM": PHARMACEUTICALS, "LLY":  PHARMACEUTICALS,
    "MRNA": PHARMACEUTICALS, "PFE":  PHARMACEUTICALS,
    "VTRS": PHARMACEUTICALS, "ZTS":  PHARMACEUTICALS,
    # SaaS for healthcare → Software
    "VEEV": SOFTWARE_SERVICES,

    # Auto retailers + carmakers + parts
    "F":    AUTOMOBILES, "GM":   AUTOMOBILES,
    "PCAR": AUTOMOBILES, "APTV": AUTOMOBILES,
    "AZO":  AUTOMOBILES, "ORLY": AUTOMOBILES, "CVNA": AUTOMOBILES,
    # Hospitality / travel platforms
    "ABNB": CONSUMER_SERVICES,

    # Outsourcing / data / waste / cert services → Commercial Services
    "ADP":  COMMERCIAL_SERVICES, "PAYX": COMMERCIAL_SERVICES,
    "EFX":  COMMERCIAL_SERVICES, "VRSK": COMMERCIAL_SERVICES,
    "LDOS": COMMERCIAL_SERVICES, "ROL":  COMMERCIAL_SERVICES,
    "RSG":  COMMERCIAL_SERVICES, "WM":   COMMERCIAL_SERVICES,
    "VLTO": COMMERCIAL_SERVICES,
}


def _build_csv_lookup() -> dict[str, str]:
    """Walk every seed CSV and build {ticker: raw_industry_label}. If a
    ticker appears in multiple CSVs, the LAST one wins — order of files
    below puts the more authoritative source last (catalog_extras
    overrides the broad indexes).
    """
    seed_files = [
        "sp500.csv", "djia.csv", "nasdaq100.csv",
        "eustx50.csv", "ftsemib.csv",
        "hsi30.csv", "nikkei225.csv", "kospi20.csv", "sse50.csv",
        "direxion_etfs.csv",
        # catalog_extras last → it wins ties (the file is the most
        # recent manual curation).
        "catalog_extras.csv",
    ]
    lookup: dict[str, str] = {}
    for fname in seed_files:
        path = os.path.join(_SEED_DIR, fname)
        if not os.path.exists(path):
            logger.warning(f"Seed file not found, skipping: {path}")
            continue
        with open(path, encoding="utf-8") as fp:
            for row in csv.DictReader(fp):
                ticker = (row.get("ticker") or "").strip()
                raw = (row.get("industry") or "").strip()
                if ticker and raw:
                    lookup[ticker] = raw
    return lookup


def run() -> None:
    db = SessionLocal()
    try:
        csv_lookup = _build_csv_lookup()
        logger.info(
            f"CSV lookup built: {len(csv_lookup)} tickers with a raw industry"
        )
        logger.info(
            f"Override map: {len(_TICKER_OVERRIDES)} hand-curated tickers"
        )

        before_counts: Counter[str | None] = Counter()
        after_counts: Counter[str | None] = Counter()
        from_csv = from_override = from_rerun = unchanged = still_null = 0

        rows = db.execute(select(Stock)).scalars().all()
        for stock in rows:
            old = stock.industry
            before_counts[old] += 1

            raw = csv_lookup.get(stock.ticker)
            if raw:
                new = canonical_industry(raw)
                src = "csv"
            elif stock.ticker in _TICKER_OVERRIDES:
                new = _TICKER_OVERRIDES[stock.ticker]
                src = "override"
            elif old is not None and old not in _CANONICAL_SET:
                # Third tier: re-run canonical_industry on a NON-canonical
                # existing label. Catches the May 2026 renames (Energy →
                # Oil/Gas/Fuels, Materials → Chemicals & Mining, Real Estate
                # → Equity REITs, Utilities → Electric/Water/Gas, Capital
                # Goods → Industrial Conglomerates & Distribution) since the
                # synonyms map knows the old strings.
                #
                # Guard: only rerun if `old` is NOT already a canonical
                # bucket — otherwise labels like "Diversified Financials"
                # (which is canonical but not present as a key in the
                # synonyms map) would get punted to OTHER.
                new = canonical_industry(old)
                src = "rerun"
            else:
                new = old  # genuinely nothing to do
                src = "kept"

            after_counts[new] += 1
            if new == old:
                unchanged += 1
                if new is None:
                    still_null += 1
            else:
                stock.industry = new
                if src == "csv":
                    from_csv += 1
                elif src == "override":
                    from_override += 1
                elif src == "rerun":
                    from_rerun += 1

        db.commit()

        logger.info("─" * 70)
        logger.info(
            f"Re-tag complete: {from_csv} from CSV, "
            f"{from_override} from override, "
            f"{from_rerun} from canonical rerun, "
            f"{unchanged} unchanged ({still_null} still NULL), "
            f"{len(rows)} total"
        )
        logger.info(
            f"Distinct industries: "
            f"{len(before_counts)} -> {len(after_counts)}"
        )
        logger.info("Distribution after re-tag:")
        for industry in CANONICAL_INDUSTRIES:
            count = after_counts.get(industry, 0)
            logger.info(f"  {industry:<48} {count}")
        if None in after_counts:
            logger.info(f"  {'(no industry)':<48} {after_counts[None]}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
