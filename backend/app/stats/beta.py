"""Beta incompleta regolarizzata, e la continued fraction che la calcola.

Serve alla t di Student (`app/stats/media.py`) e al test a blocchi dello
studio condizionale. Niente scipy: non e' una dipendenza di questo progetto.

⚠️ Questo codice NON e' stato riscritto: e' stato spostato alla lettera da
`app/scripts/conditional_screen_grid.py`, dove viveva privato. Riscriverlo
avrebbe significato cambiare un'aritmetica gia' validata da uno studio, e
lasciarne una copia avrebbe significato due implementazioni della stessa
formula che divergono al primo ritocco — la forma che in questo repo ha gia'
prodotto un 500.
"""
from __future__ import annotations

import math


def betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Lentz's method)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-9:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * betacf(a, b, x) / a
    return 1.0 - front * betacf(b, a, 1.0 - x) / b
