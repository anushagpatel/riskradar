"""Synthetic data for an explicitly labeled DEMO MODE.

Demo series are random walks generated in memory. They are never written to the database and
never create alerts, so they cannot contaminate real history. The UI shows a banner whenever
demo mode is on.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

_FREQ = {252: "B", 52: "W-WED", 12: "MS", 4: "QS", 1: "YS"}


def synthetic_series(key: str, start_value: float, vol: float, periods_per_year: int,
                     years: int = 10, end: str | None = None) -> pd.Series:
    rng = np.random.default_rng(zlib.crc32(key.encode()))  # deterministic per key
    n = max(8, years * periods_per_year)
    idx = pd.date_range(end=end or pd.Timestamp.today().normalize(), periods=n, freq=_FREQ.get(periods_per_year, "B"))
    steps = rng.normal(0.0, vol, n)
    values = start_value * np.exp(np.cumsum(steps) - np.cumsum(steps)[-1] + 0.0)  # ends near start_value
    return pd.Series(values, index=idx, name=f"DEMO:{key}")
