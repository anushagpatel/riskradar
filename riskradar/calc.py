"""Deterministic financial calculations. No LLM is ever used here.

All functions return None (or NaN inside a Series) when there is not enough data,
so callers can display "Insufficient data" instead of a misleading number.
"""
from __future__ import annotations

import math

import pandas as pd


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and not pd.isna(x)


def pct_change(current, previous) -> float | None:
    """Percent change from previous to current. None if undefined."""
    if not _ok(current) or not _ok(previous) or previous == 0:
        return None
    return float((current - previous) / abs(previous) * 100.0)


def abs_change(current, previous) -> float | None:
    if not _ok(current) or not _ok(previous):
        return None
    return float(current - previous)


def lookback_value(s: pd.Series, lookback: int):
    """Value `lookback` observations before the latest, or None."""
    s = s.dropna()
    if lookback < 1 or len(s) <= lookback:
        return None
    return float(s.iloc[-1 - lookback])


def yoy_growth(s: pd.Series, periods_per_year: int) -> float | None:
    """Latest year-over-year percent growth (latest vs. one year of observations earlier)."""
    s = s.dropna()
    if len(s) <= periods_per_year:
        return None
    return pct_change(s.iloc[-1], s.iloc[-1 - periods_per_year])


def yoy_growth_series(s: pd.Series, periods_per_year: int) -> pd.Series:
    return s.dropna().pct_change(periods_per_year) * 100.0


def historical_percentile(s: pd.Series, value: float | None = None) -> float | None:
    """Percent of historical observations <= value (default: the latest observation)."""
    s = s.dropna()
    if len(s) < 2:
        return None
    v = s.iloc[-1] if value is None else value
    return float((s <= v).mean() * 100.0)


def moving_average(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window=window, min_periods=window).mean()


def drawdown_series(s: pd.Series, window: int | None = None) -> pd.Series:
    """Percent decline from the running (or trailing-`window`) peak. Values are <= 0."""
    s = s.dropna()
    peak = s.rolling(window, min_periods=1).max() if window else s.cummax()
    return (s / peak - 1.0) * 100.0


def current_drawdown(s: pd.Series, window: int | None = None) -> float | None:
    d = drawdown_series(s, window)
    return float(d.iloc[-1]) if len(d) else None


def max_drawdown(s: pd.Series) -> float | None:
    d = drawdown_series(s)
    return float(d.min()) if len(d) else None


def spread_widening(s: pd.Series, lookback: int) -> float | None:
    """Absolute change in a spread over `lookback` observations (same units as the series)."""
    prev = lookback_value(s, lookback)
    if prev is None:
        return None
    return abs_change(float(s.dropna().iloc[-1]), prev)


def debt_growth(debt: pd.Series) -> float | None:
    """Year-over-year debt growth for an annual series (latest vs. prior fiscal year)."""
    return yoy_growth(debt, 1)


def capex_to_ocf(capex, ocf) -> float | None:
    """Capex divided by operating cash flow. None when OCF is missing or not positive."""
    if not _ok(capex) or not _ok(ocf) or ocf <= 0:
        return None
    return float(capex / ocf)


def capex_to_ocf_series(capex: pd.Series, ocf: pd.Series) -> pd.Series:
    """Ratio aligned on shared period-end dates; NaN where OCF <= 0 or either is missing."""
    df = pd.concat({"capex": capex, "ocf": ocf}, axis=1).dropna()
    df = df[df["ocf"] > 0]
    return (df["capex"] / df["ocf"]).rename("capex_to_ocf")


def leverage_change(s: pd.Series, lookback: int) -> float | None:
    """Percent change in a leverage measure over `lookback` observations."""
    prev = lookback_value(s, lookback)
    if prev is None:
        return None
    return pct_change(float(s.dropna().iloc[-1]), prev)
