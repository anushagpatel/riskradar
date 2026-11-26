"""FRED API client (https://fred.stlouisfed.org/docs/api/fred/).

Series IDs are not hard-coded here; they live in config/thresholds.toml.
The series metadata call doubles as a runtime existence check: a bad ID fails loudly.
"""
from __future__ import annotations

import pandas as pd

BASE = "https://api.stlouisfed.org/fred"


class FredError(Exception):
    pass


def _get(client, path: str, params: dict) -> dict:
    # Never let the API key leak into error messages (httpx errors include the URL).
    try:
        r = client.get(f"{BASE}/{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", None)
        detail = ""
        try:  # FRED explains 4xx errors in JSON; it never echoes the key back
            detail = (resp.json().get("error_message") or "").strip() if resp is not None else ""
        except Exception:  # noqa: BLE001
            pass
        if status == 400 and "api_key" in detail:
            raise FredError("FRED rejected the API key. Check FRED_API_KEY in .env: it should be the 32-character "
                            "lowercase key from fredaccount.stlouisfed.org, with no quotes or spaces.") from None
        msg = f"FRED request to /{path} failed" + (f" (HTTP {status})" if status else f": {type(exc).__name__}")
        raise FredError(msg + (f": {detail}" if detail else "")) from None


def fetch_series(series_id: str, api_key: str, start: str = "2000-01-01", client=None) -> tuple[pd.Series, dict]:
    """Return (observations, metadata). Missing values ('.') are dropped."""
    api_key = (api_key or "").strip().strip('"').strip("'")
    if not api_key:
        raise FredError("FRED_API_KEY is not set")
    import httpx  # lazy import keeps pure-calculation modules importable without httpx

    own = client is None
    client = client or httpx.Client()
    try:
        meta_json = _get(client, "series", {"series_id": series_id, "api_key": api_key, "file_type": "json"})
        seriess = meta_json.get("seriess") or []
        if not seriess:
            raise FredError(f"FRED series '{series_id}' not found")
        m = seriess[0]
        obs_json = _get(client, "series/observations", {
            "series_id": series_id, "api_key": api_key, "file_type": "json", "observation_start": start})
    finally:
        if own:
            client.close()

    rows = [(o["date"], o["value"]) for o in obs_json.get("observations", []) if o.get("value") not in (".", "", None)]
    s = pd.Series(
        [float(v) for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), name=series_id, dtype=float
    )
    meta = {
        "title": m.get("title", series_id),
        "units": m.get("units", ""),
        "frequency": m.get("frequency", ""),
        "last_updated": m.get("last_updated", ""),
        "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
    }
    return s, meta
