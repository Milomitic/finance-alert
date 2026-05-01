"""Rule Protocol shared by all alert rules."""
from typing import Any, Protocol

import pandas as pd


class Rule(Protocol):
    """A rule that can be evaluated on a stock's OHLCV history."""

    kind: str
    default_params: dict[str, Any]

    def evaluate(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> bool:
        """Return True iff the rule's condition is currently satisfied.

        ohlcv: DataFrame indexed by date with at least a 'close' column,
               sorted ascending by date. Most recent bar is the last row.
        params: dict of named parameters (validated by caller per kind).
        """
        ...

    def snapshot(self, ohlcv: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
        """Return JSON-serializable snapshot of indicator values at the last bar.

        Used to populate Alert.snapshot for UI/debug. Should NOT include the
        raw OHLCV — only the computed indicator values + the params used.
        """
        ...
