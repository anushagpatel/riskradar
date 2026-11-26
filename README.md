# 📡 RiskRadar AI: Market & Credit Risk Intelligence

RiskRadar AI is a research dashboard that pulls public financial data, flags indicators that move outside their normal range, and uses an AI model to explain what the signals mean. It covers market volatility, credit spreads, interest rates, equities, AI-company financing, hedge fund leverage, farm lending, lending to non-bank financial institutions (NDFIs) and bank lending.

> **Research support only.** RiskRadar does not give investment advice and does not predict financial crises. Classifications are heuristic signals from configurable thresholds, not validated risk ratings.

![Overview](docs/screenshots/overview.png)

---

## Features

- **Live risk overview**: 20 indicators across 9 risk areas, each classified as Normal, Elevated or High from its own thresholds. There is no composite score.
- **Automatic data loading**: data refreshes on page open when it's more than 6 hours old, so the dashboard is ready without any clicks.
- **Threshold alerts**: every threshold crossing is recorded with the value, trigger rule, observation date and source link.
- **AI briefing**: a structured written assessment built only from the calculated metrics, alerts and Federal Reserve report excerpts.
- **Research assistant**: a chat window that answers questions about the current data and cites its evidence.
- **Stress testing**: deterministic what-if scenarios for hedge fund leverage, NDFI credit losses, AI-company debt service and farm loan delinquencies.
- **Hallucination guards**: the app warns when an AI answer cites evidence that doesn't exist or uses numbers that aren't in the supplied data.

---

## Screenshots

### Overview
![Overview](docs/screenshots/overview.png)

The home page. The summary card states how many indicators are above their normal range and counts them by status. The colored strip shows every indicator at a glance, grouped by risk area. Below it, each indicator has a card with its latest value, change vs the previous reading, observation date and a trend chart. Charts show a moving average and dashed Elevated/High threshold lines where they apply. You can filter to flagged indicators, narrow by risk area, or sort by severity.

### Alerts
![Alerts](docs/screenshots/alerts.png)

A log of every threshold crossing. Each row shows the risk area, indicator, current and previous values, the exact rule that triggered, the severity, the observation date and a link to the source data. You can filter by High or Elevated.

### Research assistant
![Research assistant](docs/screenshots/assistant.png)

Opens from the **Ask RiskRadar** button in the bottom-right corner, on any tab. Answers are grounded in the app's own data and cite evidence IDs:
- `[M#]` for metrics
- `[A#]` for alerts
- `[R#]` for Fed report excerpts
- `[S#]` for stress results

### AI briefing
![AI briefing](docs/screenshots/ai-briefing.png)

A one-click written assessment with an executive summary, emerging risk factors, supporting evidence and source references. The model only interprets numbers the app has already calculated. The exact evidence sent to the model can be inspected under **Evidence sent to the model**.

### Stress test
![Stress test](docs/screenshots/stress-test.png)

Choose a scenario, adjust the assumptions and see hypothetical results immediately. Inputs are prefilled from the latest data where available (here, the latest OFR hedge fund leverage reading). Every calculation is deterministic Python, and **Explain with AI** describes which transmission channels the scenario could activate.

### Data & method
![Data & method](docs/screenshots/data-method.png)

The status of each data connection, controls to update data or fetch Federal Reserve reports, and plain-language notes on how classifications work and known data limitations. Expanders at the bottom list every threshold rule and the stored series.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| UI | Streamlit (1.40+), custom CSS theme |
| Charts | Plotly |
| Data processing | pandas, NumPy |
| HTTP client | httpx |
| Storage | SQLite (Python's built-in `sqlite3`) |
| AI model | OpenAI Chat Completions API (default `gpt-4o-mini`) |
| Config | TOML thresholds file, `.env` via python-dotenv |
| Tests | pytest |

---

## APIs and data sources

| Source | What it provides | Key needed |
|---|---|---|
| [FRED API](https://fred.stlouisfed.org/docs/api/fred/) (St. Louis Fed) | VIX (`VIXCLS`), S&P 500 (`SP500`), high-yield spread (`BAMLH0A0HYM2`), fed funds (`FEDFUNDS`), 10-year and 2-year Treasury yields (`DGS10`, `DGS2`), bank loans (`TOTLL`), bank loans to NDFIs (`LNFACBM027SBOG`), farm loan delinquencies (`DRFAPGACBS`) | Free API key |
| [SEC EDGAR XBRL API](https://www.sec.gov/edgar/sec-api-documentation) | Debt, operating cash flow and capex from company filings for MSFT, GOOGL, AMZN, META and NVDA | No key, but a contact user agent (name + email) is required |
| [OFR Hedge Fund Monitor](https://www.financialresearch.gov/hedge-fund-monitor/) | Hedge fund leverage from Form PF data | None |
| [Federal Reserve Financial Stability Report](https://www.federalreserve.gov/publications/financial-stability-report.htm) | Report text used as context for the AI briefing and assistant | None |
| [OpenAI API](https://platform.openai.com/docs/api-reference/chat) | AI briefing, research assistant and stress test explanations | API key |

---

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/riskradar_ai.git
cd riskradar_ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add your keys

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

Open `.env` and fill in:

```
OPENAI_API_KEY=sk-...
FRED_API_KEY=your32characterlowercasefredkey
SEC_USER_AGENT=Your Name your.email@example.com
```

- **FRED key**: free at [fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys). It's 32 lowercase letters and digits. Use no quotes or spaces.
- **SEC user agent**: your real name and email. The SEC requires it for fair access.
- **OpenAI key**: from [platform.openai.com](https://platform.openai.com/api-keys).

Optional settings:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for AI features |
| `OPENAI_BASE_URL` | OpenAI | Any OpenAI-compatible endpoint |
| `RISKRADAR_REFRESH_HOURS` | `6` | Reload data on page open when older than this |
| `OFR_LEVERAGE_MNEMONIC` | auto | Pin a specific OFR leverage series |
| `RISKRADAR_DB` | `riskradar.db` | SQLite database path |

### 3. Run

```bash
streamlit run app.py
```

The app opens at http://localhost:8501. The first load takes about a minute while it pulls data; after that it opens instantly. Check **Data & method → Connections** to confirm every source shows green.

### 4. Run the tests

```bash
pytest
```

---

## Project structure

```
riskradar_ai/
├── app.py                    # Streamlit UI
├── config/thresholds.toml    # Indicators, FRED series IDs and all thresholds
├── riskradar/
│   ├── calc.py               # Deterministic calculations (changes, YoY, percentiles, drawdowns, ratios)
│   ├── engine.py             # Rule evaluation, classification and alerts
│   ├── stress.py             # Hypothetical stress test scenarios
│   ├── fred.py               # FRED client
│   ├── edgar.py              # SEC EDGAR client
│   ├── ofr.py                # OFR Hedge Fund Monitor client
│   ├── fedreports.py         # Fed Financial Stability Report fetching and excerpt selection
│   ├── llm.py                # OpenAI client, evidence builder, citation and number guards
│   ├── pipeline.py           # Refresh and build glue
│   ├── db.py                 # SQLite persistence
│   └── ui.py                 # Theme, styling and visual components
├── tests/                    # Unit tests
├── .streamlit/config.toml    # Streamlit theme
├── requirements.txt
└── .env.example
```

---

## How it works

1. **Collect**: each source refreshes independently, so one failure never blocks the others. Results are stored in SQLite.
2. **Calculate**: all metrics (changes, year-over-year growth, percentiles, drawdowns, capex-to-cash-flow ratios) are computed in Python.
3. **Classify**: each indicator is graded Normal, Elevated or High against its own thresholds in `config/thresholds.toml`. The worst triggered rule wins.
4. **Explain**: the AI receives only the calculated metrics, alerts and report excerpts, each tagged with an ID it must cite. The app then checks the answer for unknown citations and unsupported numbers.

## Design principles

- **No fabricated data**: missing data is shown as unavailable and never filled in.
- **No composite score**: each indicator stands on its own, configurable thresholds.
- **The AI interprets; it never calculates.**
- **Fair access**: SEC requests carry your user agent and are throttled well under 10 requests per second.

## Known limitations

- Thresholds are illustrative defaults, not calibrated risk levels. Edit `config/thresholds.toml` to suit your research.
- Since April 2026, FRED provides only about 3 years of high-yield spread history and about 10 years of S&P 500 history, so percentile and drawdown windows are shorter.
- Several series are monthly or quarterly and lag; always check the observation date.
- XBRL debt and capex definitions vary by company; the tags used are shown on each indicator.
- Fed report fetching parses HTML pages. If the layout changes, paste an excerpt under **Data & method**.

## Disclaimer

RiskRadar AI is a research tool. Nothing in it is investment advice, a forecast or a validated financial risk rating.
