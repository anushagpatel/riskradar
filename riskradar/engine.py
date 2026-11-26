"""Risk detection engine: transparent, indicator-specific threshold rules.

No composite score is produced. Each indicator is classified Normal / Elevated / High /
Insufficient data from its own configured rules; the worst triggered rule wins.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import calc

CLASSES = ("Normal", "Elevated", "High", "Insufficient data")
_RANK = {"Normal": 0, "Elevated": 1, "High": 2}
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "thresholds.toml"


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG, "rb") as f:
        return tomllib.load(f)


@dataclass
class Signal:
    """Outcome of one rule on one series."""
    name: str
    rule_type: str
    value: float
    status: str  # Normal | Elevated | High
    condition: str  # human-readable trigger text (also shown for Normal as context)


@dataclass
class IndicatorResult:
    key: str
    label: str
    category: str
    unit: str
    source: str
    source_url: str
    series: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    latest: float | None = None
    previous: float | None = None
    change: float | None = None
    change_kind: str = "pct"  # "pct" or "abs"
    obs_date: str | None = None
    last_refresh: str | None = None
    classification: str = "Insufficient data"
    signals: list[Signal] = field(default_factory=list)
    rules_config: list[dict] = field(default_factory=list)
    note: str = ""
    status: str = "ok"  # ok | unavailable | demo
    error: str | None = None


def _grade(value: float, elevated: float, high: float, direction: str = "above") -> str:
    if direction == "below":
        if value <= high:
            return "High"
        if value <= elevated:
            return "Elevated"
        return "Normal"
    if value >= high:
        return "High"
    if value >= elevated:
        return "Elevated"
    return "Normal"


def evaluate_rule(rule: dict, s: pd.Series, periods_per_year: int = 1) -> Signal | None:
    """Evaluate one rule. Returns None if the series is too short (insufficient data)."""
    s = s.dropna()
    rtype = rule["type"]
    name = rule.get("name", rtype)
    direction = rule.get("direction", "above")
    if s.empty:
        return None

    if rtype == "level":
        value = float(s.iloc[-1])
    elif rtype == "change":
        value = calc.spread_widening(s, int(rule["lookback"]))
    elif rtype == "pct_change":
        value = calc.leverage_change(s, int(rule["lookback"]))
    elif rtype == "yoy":
        value = calc.yoy_growth(s, int(rule.get("periods_per_year", periods_per_year)))
    elif rtype == "drawdown":
        direction = "below"
        value = calc.current_drawdown(s, int(rule["window_obs"]) if "window_obs" in rule else None)
    elif rtype == "percentile":
        if len(s) < int(rule.get("min_obs", 30)):
            return None
        value = calc.historical_percentile(s)
    else:
        raise ValueError(f"Unknown rule type: {rtype}")

    if value is None:
        return None
    elevated, high = rule["elevated"], rule["high"]
    status = _grade(value, elevated, high, direction)
    op = "<=" if direction == "below" else ">="
    if status == "Normal":
        cond = f"{name} = {value:.2f}; below Elevated threshold ({op} {elevated})"
    else:
        thr = high if status == "High" else elevated
        cond = f"{name} = {value:.2f} {op} {thr} ({status} threshold)"
    return Signal(name=name, rule_type=rtype, value=float(value), status=status, condition=cond)


def evaluate_series(rules: list[dict], s: pd.Series, periods_per_year: int = 1) -> tuple[str, list[Signal]]:
    """Classify a series from its rules. Insufficient data only if *no* rule can be evaluated."""
    signals = [sig for r in rules if (sig := evaluate_rule(r, s, periods_per_year)) is not None]
    if not signals:
        return "Insufficient data", []
    worst = max(signals, key=lambda x: _RANK[x.status])
    return worst.status, signals


def summarize_series(s: pd.Series, change_kind: str = "pct") -> dict:
    """Latest value, previous comparable observation, change and observation date."""
    s = s.dropna()
    if s.empty:
        return {"latest": None, "previous": None, "change": None, "obs_date": None}
    latest = float(s.iloc[-1])
    previous = float(s.iloc[-2]) if len(s) > 1 else None
    change = calc.pct_change(latest, previous) if change_kind == "pct" else calc.abs_change(latest, previous)
    return {
        "latest": latest,
        "previous": previous,
        "change": change,
        "obs_date": pd.Timestamp(s.index[-1]).strftime("%Y-%m-%d"),
    }


def build_result(key: str, spec: dict, series: pd.Series, *, source_url: str, last_refresh: str | None,
                 status: str = "ok", error: str | None = None, note: str = "") -> IndicatorResult:
    kind = spec.get("change_kind", "pct")
    res = IndicatorResult(
        key=key, label=spec["label"], category=spec["category"], unit=spec.get("unit", ""),
        source=spec.get("source_label", spec.get("source", "")), source_url=source_url,
        series=series if series is not None else pd.Series(dtype=float),
        change_kind=kind, last_refresh=last_refresh, rules_config=spec.get("rules", []),
        note=note, status=status, error=error,
    )
    if series is None or series.dropna().empty:
        res.status = "unavailable" if status == "ok" else status
        return res
    res.__dict__.update(summarize_series(series, kind))
    res.classification, res.signals = evaluate_series(spec.get("rules", []), series, spec.get("periods_per_year", 1))
    return res


def alerts_from_results(results: list[IndicatorResult], now: datetime | None = None) -> list[dict]:
    """One alert per triggered (Elevated/High) rule. Demo-mode results never create alerts."""
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")
    alerts = []
    for r in results:
        if r.status != "ok":
            continue
        for sig in r.signals:
            if sig.status == "Normal":
                continue
            alerts.append({
                "created_at": ts,
                "category": r.category,
                "indicator": r.label,
                "current_value": r.latest,
                "previous_value": r.previous,
                "condition": sig.condition,
                "severity": sig.status,
                "obs_date": r.obs_date,
                "source_url": r.source_url,
            })
    return alerts
