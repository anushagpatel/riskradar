# RiskRadar AI — Market & Credit Risk Intelligence (MVP)

A lightweight Streamlit research tool that consolidates public financial data, flags threshold
crossings, explains them with an LLM, and supports hypothetical stress tests.
**Research support only: no personalized investment advice, no crisis predictions.**

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install -r requirements.txt
cp .env.example .env                                   # then fill in the keys
streamlit run app.py
```
1. Add `FRED_API_KEY` (free), `SEC_USER_AGENT` (your name + email, required by the SEC) and `OPENAI_API_KEY` to `.env`.
2. Open the app. On first load it pulls fresh data from FRED, OFR and SEC EDGAR plus the latest Fed Financial Stability Report automatically, then reuses it until it is older than `RISKRADAR_REFRESH_HOURS` (default 6). **Data & method → Update now** forces a refresh.

Run the tests: `pytest`

## Layout
| Path | Purpose |
|---|---|
| `app.py` | Streamlit UI (Overview, with the assistant behind the **Ask RiskRadar** button in the bottom-right corner, Alerts, AI briefing, Stress test, Data & method) |
| `riskradar/ui.py`, `.streamlit/config.toml` | Theme, styling and presentational components |
| `config/thresholds.toml` | Indicators, FRED series IDs and all thresholds (edit freely) |
| `riskradar/calc.py` | Deterministic calculations (pct change, YoY, percentiles, drawdown, spreads, capex/OCF…) |
| `riskradar/engine.py` | Rule evaluation, classification (Normal/Elevated/High/Insufficient data), alerts |
| `riskradar/stress.py` | Deterministic hypothetical stress tests |
| `riskradar/fred.py`, `edgar.py`, `ofr.py`, `fedreports.py` | Data sources |
| `riskradar/llm.py` | OpenAI client, evidence builder, citation/number guards |
| `riskradar/db.py`, `pipeline.py` | SQLite persistence and refresh/build glue |

## Data sources and verified series
FRED series used (confirmed against FRED pages): `VIXCLS`, `SP500`, `BAMLH0A0HYM2`, `FEDFUNDS`, `DGS10`, `DGS2`,
`TOTLL` (bank loans, weekly), `LNFACBM027SBOG` (bank loans to nondepository financial institutions, monthly, SA),
`DRFAPGACBS` (delinquency rate, loans to finance agricultural production, quarterly, SA). The FRED metadata call
also validates every ID at refresh time; a bad ID shows as "data unavailable".
SEC EDGAR XBRL company facts (MSFT, GOOGL, AMZN, META, NVDA; CIKs resolved from the SEC's ticker file),
OFR Hedge Fund Monitor API, and the Fed Financial Stability Report page.

## Design guarantees
- **No fabricated data.** Failures show as unavailable.
- **No composite score.** Each indicator uses its own configurable thresholds; classifications are heuristics.
- **LLM only interprets.** It receives calculated metrics, alerts and report excerpts with IDs ([M#], [A#], [R#], [S#]),
  must cite them, and the app warns about unknown citation IDs and numbers not found in the evidence.
- **Fair access.** SEC requests carry your User-Agent and are throttled well under 10 req/s.

## Known limitations (please read)
- Built and unit-tested offline. The live API calls (FRED, SEC, OFR, Fed site, OpenAI) and the Streamlit UI were **not**
  exercised end-to-end in the build environment — expect to fix small integration issues on first run.
- **OFR leverage mnemonic** is auto-resolved from OFR's metadata search (name contains "leverage", `FPF-ALLQHF*`). Check the
  chosen series on the Methodology tab, or pin one with `OFR_LEVERAGE_MNEMONIC`.
- **Fed report fetching** parses HTML report pages only; if the layout changes or only PDFs are found, paste an excerpt under **Data & method**.
- FRED limits some history (HY spread ≈ 3 years since April 2026; S&P 500 ≈ 10 years), so percentile/drawdown windows are shorter.
- XBRL debt/capex definitions vary by company; tags used are displayed per indicator.
- Thresholds are illustrative defaults, not calibrated. `OPENAI_MODEL` defaults to `gpt-4o-mini`; change it in `.env`.
- Specification note: the project brief was cut off mid-sentence in Feature 4, so anything after it (extra features,
  deliverables) was not built. Stress testing was included because the problem statement asks for it.
