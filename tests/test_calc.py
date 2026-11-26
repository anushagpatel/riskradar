import math

import pandas as pd

from riskradar import calc


def series(values, freq="D"):
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq=freq), dtype=float)


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_pct_change_basic_and_undefined():
    assert close(calc.pct_change(110, 100), 10.0)
    assert close(calc.pct_change(90, 100), -10.0)
    assert calc.pct_change(5, 0) is None
    assert calc.pct_change(None, 3) is None
    assert calc.pct_change(float("nan"), 3) is None


def test_yoy_growth_needs_enough_history():
    s = series(range(100, 113), freq="MS")  # 13 monthly points
    assert close(calc.yoy_growth(s, 12), 12.0)  # 112 vs 100
    assert calc.yoy_growth(s.iloc[:12], 12) is None


def test_historical_percentile():
    s = series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert close(calc.historical_percentile(s), 100.0)
    assert close(calc.historical_percentile(s, 5), 50.0)
    assert calc.historical_percentile(series([1.0])) is None


def test_moving_average():
    s = series([1, 2, 3, 4, 5])
    ma = calc.moving_average(s, 3)
    assert math.isnan(ma.iloc[1])
    assert close(ma.iloc[-1], 4.0)


def test_drawdown_running_peak():
    s = series([100, 120, 90, 110])
    dd = calc.drawdown_series(s)
    assert close(dd.iloc[2], (90 / 120 - 1) * 100)
    assert close(calc.max_drawdown(s), -25.0)
    assert close(calc.current_drawdown(s), (110 / 120 - 1) * 100)


def test_drawdown_trailing_window_forgets_old_peak():
    s = series([200, 100, 90, 95])
    assert close(calc.current_drawdown(s, window=3), (95 / 100 - 1) * 100)  # old 200 peak excluded


def test_spread_widening():
    s = series([3.0, 3.1, 3.2, 3.9])
    assert close(calc.spread_widening(s, 3), 0.9)
    assert calc.spread_widening(s, 10) is None


def test_debt_growth_annual():
    debt = series([40, 50], freq="YS")
    assert close(calc.debt_growth(debt), 25.0)


def test_capex_to_ocf_handles_nonpositive_ocf():
    assert close(calc.capex_to_ocf(60, 100), 0.6)
    assert calc.capex_to_ocf(60, 0) is None
    assert calc.capex_to_ocf(60, -5) is None
    assert calc.capex_to_ocf(None, 10) is None


def test_capex_to_ocf_series_aligns_dates_and_drops_bad_rows():
    idx = pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31"])
    capex = pd.Series([10.0, 20.0, 30.0], index=idx)
    ocf = pd.Series([100.0, -5.0], index=idx[:2])
    out = calc.capex_to_ocf_series(capex, ocf)
    assert list(out.index) == [idx[0]] and close(out.iloc[0], 0.1)


def test_leverage_change():
    s = series([5.0, 5.0, 5.0, 5.0, 6.0], freq="QS")
    assert close(calc.leverage_change(s, 4), 20.0)
    assert calc.leverage_change(s, 9) is None
