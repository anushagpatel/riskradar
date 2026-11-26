"""SEC EDGAR XBRL "company facts" client.

Follows SEC fair-access guidance: descriptive User-Agent (set SEC_USER_AGENT in .env) and
well under 10 requests/second. Annual (10-K, fiscal-year) values only, so reporting periods
are consistent across companies. All values are converted from USD to $ billions.

Tag handling is deliberately tolerant: companies change XBRL tags over time.
- Flow items (revenue, capex, operating cash flow): values are merged across candidate tags in
  priority order, per fiscal-year end date.
- Debt: ONE tag is chosen (no merging) because different debt tags have different definitions
  and mixing them would create artificial jumps. The tag used is reported.
"""
from __future__ import annotations

import time

import pandas as pd

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type=10-K"

TAGS = {
    "revenue": (["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"], "flow", "merge"),
    "operating_cash_flow": (["NetCashProvidedByUsedInOperatingActivities"], "flow", "merge"),
    "capex": (["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
               "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"], "flow", "merge"),
    "total_debt": (["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount",
                    "LongTermDebtNoncurrent"], "instant", "single"),
}


class EdgarError(Exception):
    pass


def _headers(user_agent: str) -> dict:
    if not user_agent or "@" not in user_agent:
        raise EdgarError("Set SEC_USER_AGENT in .env to something like 'Your Name your.email@example.com' "
                         "(required by SEC fair-access rules)")
    return {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}


def _get_json(client, url: str, headers: dict) -> dict:
    time.sleep(0.15)  # stay far below the SEC's 10 requests/second limit
    try:
        r = client.get(url, headers=headers, timeout=45)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise EdgarError(f"SEC request failed ({'HTTP ' + str(status) if status else type(exc).__name__}): {url}") from None


def resolve_cik(ticker: str, client, user_agent: str) -> tuple[int, str]:
    """Look up CIK and company name from the SEC's official ticker file (not hard-coded)."""
    data = _get_json(client, TICKERS_URL, _headers(user_agent))
    for row in data.values():
        if row.get("ticker", "").upper() == ticker.upper():
            return int(row["cik_str"]), row.get("title", ticker)
    raise EdgarError(f"Ticker {ticker} not found in SEC ticker file")


def _annual_entries(facts: dict, tag: str, kind: str) -> pd.Series:
    units = (facts.get("facts", {}).get("us-gaap", {}).get(tag, {}) or {}).get("units", {}).get("USD", [])
    best: dict[str, tuple[str, float]] = {}  # end -> (filed, value)
    for e in units:
        if e.get("fp") != "FY" or not str(e.get("form", "")).startswith("10-K"):
            continue
        end, val = e.get("end"), e.get("val")
        if end is None or val is None:
            continue
        if kind == "flow":
            start = e.get("start")
            if not start:
                continue
            days = (pd.Timestamp(end) - pd.Timestamp(start)).days
            if not 350 <= days <= 380:
                continue
        elif e.get("start"):  # instant items have no start
            continue
        filed = e.get("filed", "")
        if end not in best or filed >= best[end][0]:  # keep latest-filed (restated) value
            best[end] = (filed, float(val))
    if not best:
        return pd.Series(dtype=float)
    s = pd.Series({pd.Timestamp(k): v[1] for k, v in best.items()}).sort_index()
    return s / 1e9  # USD -> $ billions


def extract_metric(facts: dict, metric: str) -> tuple[pd.Series, list[str]]:
    """Return (annual series in $bn, tags used). Empty series if no tag is available."""
    tags, kind, mode = TAGS[metric]
    per_tag = {t: _annual_entries(facts, t, kind) for t in tags}
    per_tag = {t: s for t, s in per_tag.items() if not s.empty}
    if not per_tag:
        return pd.Series(dtype=float), []
    if mode == "merge":
        merged, used = pd.Series(dtype=float), []
        for t in tags:  # priority order
            if t not in per_tag:
                continue
            new = per_tag[t][~per_tag[t].index.isin(merged.index)]
            if not new.empty:
                merged = pd.concat([merged, new])
                used.append(t)
        return merged.sort_index(), used
    # single: latest observation first, then most observations, then priority order
    best = max(per_tag, key=lambda t: (per_tag[t].index[-1], len(per_tag[t]), -tags.index(t)))
    return per_tag[best], [best]


def fetch_company(ticker: str, client, user_agent: str) -> dict:
    """Fetch and extract all metrics for one ticker."""
    headers = _headers(user_agent)
    cik, name = resolve_cik(ticker, client, user_agent)
    facts = _get_json(client, FACTS_URL.format(cik=cik), headers)
    out = {"ticker": ticker, "name": name, "cik": cik, "source_url": BROWSE_URL.format(cik=cik), "metrics": {}}
    for metric in TAGS:
        series, used = extract_metric(facts, metric)
        out["metrics"][metric] = {"series": series, "tags": used}
    return out
