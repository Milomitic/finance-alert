"""Addestra ADESSO i modelli in ombra, senza aspettare la domenica.

    kubectl exec -n finance-alert finance-alert-finance-alert-0 -- \
        python -m app.scripts.addestra_modelli_ombra

Scrive due righe in `modelli_ombra`; lo scan le legge entro mezz'ora. Circa
un'ora e mezza sul nodo di produzione: non lanciarlo durante una scansione.
"""
from __future__ import annotations

import json


def main() -> None:
    from app.core.db import SessionLocal
    from app.ml.addestramento import addestra

    with SessionLocal() as db:
        print(json.dumps(addestra(db), indent=2, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
