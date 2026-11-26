import pandas as pd

from riskradar import db, engine


def series(values, freq="D"):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq=freq), dtype=float)


def test_config_loads_and_every_rule_has_thresholds():
    cfg = engine.load_config()
    assert cfg["indicators"] and cfg["ai_financing"]["tickers"]
    for name, spec in cfg["indicators"].items():
        assert spec["label"] and spec["category"] and spec["source"] in ("fred", "ofr"), name
        if spec["source"] == "fred":
            assert spec["series_id"], name
        for rule in spec["rules"]:
            assert "elevated" in rule and "high" in rule, (name, rule)


def test_level_rule_grades():
    rule = {"type": "level", "name": "VIX", "elevated": 20, "high": 30}
    assert engine.evaluate_rule(rule, series([15.0])).status == "Normal"
    assert engine.evaluate_rule(rule, series([25.0])).status == "Elevated"
    sig = engine.evaluate_rule(rule, series([35.0]))
    assert sig.status == "High" and ">= 30" in sig.condition


def test_drawdown_rule_uses_negative_thresholds():
    rule = {"type": "drawdown", "name": "DD", "window_obs": 10, "elevated": -10, "high": -20}
    assert engine.evaluate_rule(rule, series([100, 95])).status == "Normal"
    assert engine.evaluate_rule(rule, series([100, 88])).status == "Elevated"
    assert engine.evaluate_rule(rule, series([100, 75])).status == "High"


def test_change_and_pct_change_rules():
    s = series([3.0, 3.0, 3.0, 4.2])
    assert engine.evaluate_rule({"type": "change", "lookback": 3, "elevated": 0.75, "high": 1.5}, s).status == "Elevated"
    s2 = series([5, 5, 5, 5, 6.5], freq="QS")
    assert engine.evaluate_rule({"type": "pct_change", "lookback": 4, "elevated": 10, "high": 20}, s2).status == "High"


def test_yoy_rule():
    s = series(list(range(100, 113)), freq="MS")
    sig = engine.evaluate_rule({"type": "yoy", "elevated": 10, "high": 20}, s, periods_per_year=12)
    assert sig.status == "Elevated"


def test_insufficient_data_is_reported_not_guessed():
    rule = {"type": "change", "lookback": 20, "elevated": 1, "high": 2}
    assert engine.evaluate_rule(rule, series([1.0, 2.0])) is None
    cls, sigs = engine.evaluate_series([rule], series([1.0, 2.0]))
    assert cls == "Insufficient data" and sigs == []
    assert engine.evaluate_series([rule], pd.Series(dtype=float))[0] == "Insufficient data"


def test_percentile_rule_respects_min_obs():
    rule = {"type": "percentile", "elevated": 80, "high": 95, "min_obs": 10}
    assert engine.evaluate_rule(rule, series(range(5))) is None
    assert engine.evaluate_rule(rule, series(range(20))).status == "High"


def test_worst_rule_wins():
    rules = [{"type": "level", "elevated": 5, "high": 10}, {"type": "change", "lookback": 1, "elevated": 0.1, "high": 99}]
    cls, sigs = engine.evaluate_series(rules, series([4.0, 6.0]))
    assert cls == "Elevated" and len(sigs) == 2


def test_build_result_and_alert_fields():
    spec = {"label": "Test", "category": "Cat", "source": "fred", "unit": "%", "change_kind": "abs",
            "rules": [{"type": "level", "name": "Lvl", "elevated": 5, "high": 10}], "periods_per_year": 252}
    res = engine.build_result("t", spec, series([4.0, 6.0]), source_url="http://x", last_refresh="now")
    assert res.latest == 6.0 and res.previous == 4.0 and res.change == 2.0 and res.classification == "Elevated"
    alerts = engine.alerts_from_results([res])
    assert len(alerts) == 1
    a = alerts[0]
    for field in ("category", "indicator", "current_value", "previous_value", "condition", "severity", "created_at", "source_url"):
        assert a[field] not in (None, ""), field


def test_demo_results_never_create_alerts():
    spec = {"label": "Demo", "category": "Cat", "source": "fred", "rules": [{"type": "level", "elevated": 1, "high": 2}]}
    res = engine.build_result("d", spec, series([5.0, 9.0]), source_url="demo", last_refresh=None, status="demo")
    assert res.classification == "High" and engine.alerts_from_results([res]) == []


def test_unavailable_series_is_flagged():
    spec = {"label": "X", "category": "Cat", "source": "fred", "rules": []}
    res = engine.build_result("x", spec, pd.Series(dtype=float), source_url="u", last_refresh=None, error="boom")
    assert res.status == "unavailable" and res.classification == "Insufficient data" and res.latest is None


def test_db_roundtrip_and_alert_dedup(tmp_path=None):
    conn = db.connect(":memory:")
    s = series([1.0, 2.0, 3.0])
    db.save_series(conn, "fred:T", s, title="T", source="FRED", source_url="http://t")
    assert list(db.load_series(conn, "fred:T").values) == [1.0, 2.0, 3.0]
    assert db.get_meta(conn, "fred:T")["last_success"]
    db.record_failure(conn, "fred:BAD", "nope")
    assert db.get_meta(conn, "fred:BAD")["last_error"] == "nope"
    alert = {"created_at": "t", "category": "c", "indicator": "i", "current_value": 1.0, "previous_value": 0.5,
             "condition": "cond", "severity": "High", "obs_date": "2024-01-01", "source_url": "u"}
    assert db.insert_alerts(conn, [alert]) == 1
    assert db.insert_alerts(conn, [alert]) == 0  # same alert for same observation is not duplicated
    assert len(db.recent_alerts(conn)) == 1
