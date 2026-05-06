"""Run all four index seeds against the configured DB."""
from pathlib import Path

from loguru import logger

from app.core.db import SessionLocal
from app.services.seed_service import seed_index_from_csv

SEEDS = [
    ("sp500.csv", "SP500", "S&P 500", "US"),
    ("nasdaq100.csv", "NDX", "Nasdaq-100", "US"),
    ("djia.csv", "DJI", "Dow Jones Industrial Average", "US"),
    ("ftsemib.csv", "FTSEMIB", "FTSE MIB", "IT"),
    ("eustx50.csv", "EUSTX50", "EuroStoxx 50", "EU"),
    ("sse50.csv", "SSE50", "SSE 50", "CN"),
    ("hsi30.csv", "HSI30", "Hang Seng top 30", "HK"),
    # Nikkei 225 — top ~40 most-traded constituents seeded; full 225
    # would require a scraped feed. Yahoo tickers use the .T suffix
    # (Tokyo) so the live quote service can fetch them directly.
    ("nikkei225.csv", "N225", "Nikkei 225 (top constituents)", "JP"),
]

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def run() -> None:
    db = SessionLocal()
    try:
        for filename, code, name, country in SEEDS:
            path = SEED_DIR / filename
            if not path.exists():
                logger.warning(f"Seed file missing: {path}")
                continue
            with path.open(encoding="utf-8") as f:
                result = seed_index_from_csv(
                    db, f, index_code=code, index_name=name, country=country
                )
            logger.info(f"{code}: added={result.added} updated={result.updated}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()
