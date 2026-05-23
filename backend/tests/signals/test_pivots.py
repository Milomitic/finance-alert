import pandas as pd
from app.signals.pivots import find_pivots


def test_find_pivots_extrema_and_edges():
    s = pd.Series([5, 3, 1, 4, 2, 6, 0])
    assert find_pivots(s, 1, kind="low") == [2, 4]
    assert find_pivots(s, 1, kind="high") == [3, 5]
    edges = find_pivots(s, 1, kind="low") + find_pivots(s, 1, kind="high")
    assert 0 not in edges and 6 not in edges
