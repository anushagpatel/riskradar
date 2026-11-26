"""Glue between data sources, SQLite and the risk engine."""
from __future__ import annotations

from . import calc, db, demo, edgar, engine, fred, ofr

SOURCE_LABELS = {"fred": "FRED", "ofr": "OFR Hedge Fund Monitor", "edgar": "SEC EDGAR"}
OFR_KEY = "ofr:hf_leverage"


def _series_key(spec: dict) -> str:
    return OFR_KEY if spec["source"] == "ofr" else f"fred:{spec['series_id']}"


def refresh_all(conn, cfg: dict, *, fred_key: str, sec_user_agent: str, ofr_override: str = "") -> list[dict]:
    """Refresh every source independently; one failure never blocks the others."""
    import httpx

    status: list[dict] = []
    default_start = cfg.get("defaults", {}).get("history_start", "2000-01-01")

    # ---- FRED
    with httpx.Client() as client:
        for name, spec in cfg["indicators"].items():
            if spec["source"] != "fred":
                continue
            key = _series_key(spec)
            url = f"https://fred.stlouisfed.org/series/{spec['series_id']}"
            try:
                s, meta = fred.fetch_series(spec["series_id"], fred_key, spec.get("history_start", default_start), client)
                if s.empty:
                    raise fred.FredError(f"FRED returned no observations for {spec['series_id']}")
                db.save_series(conn, key, s, title=meta["title"], units=meta["units"], frequency=meta["frequency"],
                               source="FRED", source_url=meta["source_url"])
                status.append({"source": "FRED", "item": spec["series_id"], "ok": True, "message": f"{len(s)} observations"})
            except Exception as exc:  # noqa: BLE001
                db.record_failure(conn, key, str(exc), source="FRED", source_url=url)
                status.append({"source": "FRED", "item": spec["series_id"], "ok": False, "message": str(exc)})

    # ---- OFR
    for name, spec in cfg["indicators"].items():
        if spec["source"] != "ofr":
            continue
        try:
            s, meta = ofr.fetch_leverage(cfg.get("ofr", {}), ofr_override)
            if s.empty:
                raise ofr.OfrError("OFR returned no observations")
            db.save_series(conn, OFR_KEY, s, title=meta["title"], units="ratio", frequency="Quarterly",
                           source="OFR Hedge Fund Monitor", source_url=meta["source_url"], extra={"mnemonic": meta["mnemonic"]})
            status.append({"source": "OFR", "item": meta["mnemonic"], "ok": True, "message": f"{len(s)} observations"})
        except Exception as exc:  # noqa: BLE001
            db.record_failure(conn, OFR_KEY, str(exc), source="OFR Hedge Fund Monitor", source_url=ofr.PAGE_URL)
            status.append({"source": "OFR", "item": "hedge fund leverage", "ok": False, "message": str(exc)})

    # ---- SEC EDGAR
    with httpx.Client() as client:
        for ticker in cfg["ai_financing"]["tickers"]:
            try:
                company = edgar.fetch_company(ticker, client, sec_user_agent)
                got = 0
                for metric, payload in company["metrics"].items():
                    key = f"edgar:{ticker}:{metric}"
                    if payload["series"].empty:
                        db.record_failure(conn, key, f"No usable XBRL tag found for {metric}", source="SEC EDGAR",
                                          source_url=company["source_url"])
                        continue
                    db.save_series(conn, key, payload["series"], title=f"{company['name']} - {metric}", units="$bn",
                                   frequency="Annual (fiscal year)", source="SEC EDGAR", source_url=company["source_url"],
                                   extra={"tags": payload["tags"], "company": company["name"]})
                    got += 1
                status.append({"source": "SEC EDGAR", "item": ticker, "ok": got > 0,
                               "message": f"{got}/{len(company['metrics'])} metrics available"})
            except Exception as exc:  # noqa: BLE001
                db.record_failure(conn, f"edgar:{ticker}:status", str(exc), source="SEC EDGAR")
                status.append({"source": "SEC EDGAR", "item": ticker, "ok": False, "message": str(exc)})
    return status


def _ai_specs(cfg: dict, ticker: str) -> dict[str, dict]:
    ai = cfg["ai_financing"]
    c, d = ai["capex_to_ocf"], ai["debt_growth"]
    return {
        f"ai_{ticker}_capex_ocf": {
            "label": f"{ticker} capex / operating cash flow", "category": ai["category"], "source": "edgar",
            "unit": "x", "periods_per_year": 1, "change_kind": "abs",
            "rules": [{"type": "level", "name": c["name"], "elevated": c["elevated"], "high": c["high"]}]},
        f"ai_{ticker}_debt": {
            "label": f"{ticker} total debt", "category": ai["category"], "source": "edgar",
            "unit": "$bn", "periods_per_year": 1, "change_kind": "pct",
            "rules": [{"type": "yoy", "name": d["name"], "elevated": d["elevated"], "high": d["high"]}]},
    }


def build_results(conn, cfg: dict, demo_mode: bool = False) -> list[engine.IndicatorResult]:
    results: list[engine.IndicatorResult] = []

    # ---- FRED + OFR indicators
    for name, spec in cfg["indicators"].items():
        spec = {**spec, "source_label": SOURCE_LABELS[spec["source"]]}
        key = _series_key(spec)
        if demo_mode:
            s = demo.synthetic_series(name, spec["demo_start"], spec["demo_vol"], spec["periods_per_year"])
            results.append(engine.build_result(name, spec, s, source_url="(synthetic demo data)", last_refresh=None,
                                               status="demo", note="SYNTHETIC DEMO DATA - not real"))
            continue
        meta = db.get_meta(conn, key) or {}
        s = db.load_series(conn, key)
        default_url = (f"https://fred.stlouisfed.org/series/{spec['series_id']}" if spec["source"] == "fred"
                       else ofr.PAGE_URL)
        note = ""
        if spec["source"] == "ofr" and meta.get("extra", {}).get("mnemonic"):
            note = f"OFR series {meta['extra']['mnemonic']}: {meta.get('title', '')}"
        results.append(engine.build_result(name, spec, s, source_url=meta.get("source_url") or default_url,
                                           last_refresh=meta.get("last_success"), error=meta.get("last_error"), note=note))

    # ---- AI financing (SEC EDGAR)
    for ticker in cfg["ai_financing"]["tickers"]:
        specs = _ai_specs(cfg, ticker)
        spec_ratio, spec_debt = (specs[f"ai_{ticker}_capex_ocf"], specs[f"ai_{ticker}_debt"])
        for k, sp in ((f"ai_{ticker}_capex_ocf", spec_ratio), (f"ai_{ticker}_debt", spec_debt)):
            sp["source_label"] = SOURCE_LABELS["edgar"]
        if demo_mode:
            ratio = demo.synthetic_series(f"{ticker}_ratio", 0.6, 0.12, 1, years=8)
            debt = demo.synthetic_series(f"{ticker}_debt", 40.0, 0.2, 1, years=8)
            for k, sp, s in ((f"ai_{ticker}_capex_ocf", spec_ratio, ratio), (f"ai_{ticker}_debt", spec_debt, debt)):
                results.append(engine.build_result(k, sp, s, source_url="(synthetic demo data)", last_refresh=None,
                                                   status="demo", note="SYNTHETIC DEMO DATA - not real"))
            continue
        capex_s, ocf_s = db.load_series(conn, f"edgar:{ticker}:capex"), db.load_series(conn, f"edgar:{ticker}:operating_cash_flow")
        debt_s = db.load_series(conn, f"edgar:{ticker}:total_debt")
        m_capex, m_debt = db.get_meta(conn, f"edgar:{ticker}:capex") or {}, db.get_meta(conn, f"edgar:{ticker}:total_debt") or {}
        err = (db.get_meta(conn, f"edgar:{ticker}:status") or {}).get("last_error") or m_debt.get("last_error")
        ratio = calc.capex_to_ocf_series(capex_s, ocf_s) if len(capex_s) and len(ocf_s) else capex_s.iloc[0:0]
        url = m_capex.get("source_url") or m_debt.get("source_url") or "https://www.sec.gov/edgar"
        tags_r = f"capex tags: {', '.join(m_capex.get('extra', {}).get('tags', [])) or 'n/a'}"
        tags_d = f"debt tag: {', '.join(m_debt.get('extra', {}).get('tags', [])) or 'n/a'} (definitions vary by company)"
        results.append(engine.build_result(f"ai_{ticker}_capex_ocf", spec_ratio, ratio, source_url=url,
                                           last_refresh=m_capex.get("last_success"), error=err, note=tags_r))
        results.append(engine.build_result(f"ai_{ticker}_debt", spec_debt, debt_s, source_url=url,
                                           last_refresh=m_debt.get("last_success"), error=err, note=tags_d))
    return results
