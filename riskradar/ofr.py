"""Office of Financial Research Hedge Fund Monitor API client.

Docs: https://www.financialresearch.gov/hedge-fund-monitor/api-specs/
Base URL: https://data.financialresearch.gov/hf/v1 (no key required).

The leverage mnemonic is NOT hard-coded. It is resolved at runtime from the OFR metadata search
(or taken from OFR_LEVERAGE_MNEMONIC if you set it), and the resolved mnemonic + series name are
shown in the app so the choice can be audited. If nothing resolves, the indicator shows
"Insufficient data" - nothing is fabricated.
"""
from __future__ import annotations

import pandas as pd

BASE = "https://data.financialresearch.gov/hf/v1"
PAGE_URL = "https://www.financialresearch.gov/hedge-fund-monitor/"


class OfrError(Exception):
    pass


def _get(client, path: str, params: dict | None = None):
    try:
        r = client.get(f"{BASE}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        status = getattr(getattr(exc, "response", None), "status_code", None)
        raise OfrError(f"OFR request to /{path} failed" + (f" (HTTP {status})" if status else f": {type(exc).__name__}")) from None


def pick_leverage_candidate(results: list[dict], must_contain: list[str], prefix: str) -> dict | None:
    """Choose a series from /metadata/search results.

    Keeps rows whose mnemonic starts with `prefix` and whose descriptive name contains every
    string in `must_contain`; returns the first in a stable (sorted-by-mnemonic) order.
    """
    cands = []
    for row in results:
        mnemonic = str(row.get("mnemonic", ""))
        value = str(row.get("value", ""))
        if row.get("field") != "description/name" or not mnemonic.upper().startswith(prefix.upper()):
            continue
        if all(t.lower() in value.lower() for t in must_contain):
            cands.append({"mnemonic": mnemonic, "name": value})
    return sorted(cands, key=lambda c: c["mnemonic"])[0] if cands else None


def resolve_mnemonic(client, cfg_ofr: dict, override: str = "") -> dict:
    if override:
        return {"mnemonic": override, "name": "(set via OFR_LEVERAGE_MNEMONIC)"}
    results = _get(client, "metadata/search", {"query": cfg_ofr.get("search_query", "*leverage*")})
    pick = pick_leverage_candidate(results, cfg_ofr.get("name_must_contain", ["leverage"]),
                                   cfg_ofr.get("mnemonic_prefix", "FPF-ALLQHF"))
    if not pick:
        raise OfrError("No OFR leverage series matched the configured search; set OFR_LEVERAGE_MNEMONIC")
    return pick


def fetch_timeseries(mnemonic: str, client=None) -> pd.Series:
    import httpx  # lazy import

    own = client is None
    client = client or httpx.Client()
    try:
        data = _get(client, "series/timeseries", {"mnemonic": mnemonic})
    finally:
        if own:
            client.close()
    pairs = [(d, v) for d, v in data if v is not None]
    return pd.Series([float(v) for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]),
                     name=mnemonic, dtype=float)


def fetch_leverage(cfg_ofr: dict, override: str = "") -> tuple[pd.Series, dict]:
    import httpx

    with httpx.Client() as client:
        pick = resolve_mnemonic(client, cfg_ofr, override)
        series = fetch_timeseries(pick["mnemonic"], client)
    return series, {"mnemonic": pick["mnemonic"], "title": pick["name"],
                    "source_url": f"{BASE}/series/timeseries?mnemonic={pick['mnemonic']}"}
