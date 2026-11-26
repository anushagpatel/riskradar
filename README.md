# 📡 RiskRadar AI

A dashboard I built to keep an eye on market and credit risk using public financial data. It pulls numbers from FRED, SEC filings, the OFR and the Fed, checks each indicator against a set of thresholds, and flags anything that looks off. There's also an AI assistant on top that can explain what's going on, but it only works from the data the app has already pulled and calculated. It doesn't make up numbers.

Right now it tracks 20 indicators across 9 areas: market volatility, credit spreads, interest rates, equities, AI company financing, hedge fund leverage, farm lending, bank lending to non-bank lenders (NDFIs), and overall bank lending.

It's a research tool, not investment advice, and it doesn't try to predict crises.

## Where the data comes from

Everything is from free, official sources. Every indicator in the app links back to where it came from and shows the date of the latest reading.

| Source | Who publishes it | What I use from it |
|---|---|---|
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | Federal Reserve Bank of St. Louis | VIX (`VIXCLS`), S&P 500 (`SP500`), high yield spread (`BAMLH0A0HYM2`), fed funds rate (`FEDFUNDS`), 10y and 2y Treasury yields (`DGS10`, `DGS2`), bank loans (`TOTLL`), bank loans to NDFIs (`LNFACBM027SBOG`), farm loan delinquency rate (`DRFAPGACBS`) |
| [SEC EDGAR](https://www.sec.gov/edgar/sec-api-documentation) | U.S. Securities and Exchange Commission | Debt, operating cash flow and capex from the annual filings of Microsoft, Alphabet, Amazon, Meta and NVIDIA |
| [OFR Hedge Fund Monitor](https://www.financialresearch.gov/hedge-fund-monitor/) | Office of Financial Research (Treasury) | Hedge fund leverage, from Form PF data |
| [Financial Stability Report](https://www.federalreserve.gov/publications/financial-stability-report.htm) | Federal Reserve Board | Report text, only used as background for the AI |

FRED needs a free API key and the SEC asks for your name and email in the request header. The other two don't need anything. The AI parts run on the OpenAI API.

## How I tried to keep it trustworthy

The main rule I followed: the AI explains, Python calculates. All the math (changes, year-over-year growth, percentiles, drawdowns, ratios) is plain Python with unit tests. The model never computes anything itself.

Some other things I put in place:

- If a source fails, the card just says the data is unavailable. Nothing gets estimated or filled in.
- There's no overall "risk score". Each indicator is judged on its own thresholds, and all of them live in one file (`config/thresholds.toml`) that you can read and change.
- Every alert shows the exact rule that fired, so you can see why something got flagged.
- When the AI answers, it has to cite where each point came from. `[M3]` means metric 3, `[A2]` means alert 2, and so on.
- The app checks every answer afterwards. If the model cites something that doesn't exist, or uses a number that isn't in the data it was given, you get a warning.
- You can see exactly what was sent to the model for each briefing.
- Stress test results are always labelled as hypothetical so they don't get mixed up with real data.

On the privacy side, your API keys stay in your local `.env` file (which is gitignored), and they never show up in error messages. Everything is stored in a local SQLite file. The app caches data and only goes back to the APIs when it's more than 6 hours old, and SEC requests are throttled well under their 10 requests/second limit.

## What it looks like

### Overview
<img width="3420" height="1670" alt="Overview page" src="https://github.com/user-attachments/assets/e7540691-7cf7-4002-ac74-634004ea8fda" />

This is the home page. The top card tells you how many indicators are out of their normal range, and the colored strip shows all 20 at once, grouped by area (red = high, orange = elevated, green = normal). Below that, each indicator gets its own card with the latest value, the change since the last reading, and a chart with the moving average and threshold lines. You can filter to just the flagged ones, pick specific areas, or sort by severity.

### Alerts
<img width="3390" height="1014" alt="Alerts page" src="https://github.com/user-attachments/assets/65ea3c31-a95f-463b-8de4-6520562f1300" />

Every time an indicator crosses a threshold it shows up here, with the value, the previous value, which rule triggered it and a link to the source.

### AI assistant
<img width="930" height="1220" alt="AI assistant" src="https://github.com/user-attachments/assets/e9f2bfaf-8135-48af-b27f-3d52c4fc8fd7" />

Click "Ask RiskRadar" in the bottom right corner on any page to open the chat. You can ask things like "which indicators are showing stress right now?" and it answers from the current data, with citations.

### AI briefing
<img width="3198" height="1704" alt="AI briefing" src="https://github.com/user-attachments/assets/73f1877a-20e3-4ec8-99c4-221a6bb3ffb4" />

One click and you get a written summary of where things stand: a short overview, the main risks, the numbers behind them and the sources. You can expand "Evidence sent to the model" to see exactly what it was working from.

### Stress test
<img width="3198" height="1268" alt="Stress test" src="https://github.com/user-attachments/assets/927ffa31-991e-4867-839c-08d5b044099c" />

What-if scenarios. Pick one (hedge fund leverage shock, NDFI credit losses, AI company debt service, or farm loan stress), move the sliders and the results update straight away. Where possible the inputs start from real data. In this screenshot the leverage comes from the latest OFR reading. "Explain with AI" walks through what the result could mean.

### Data & method
<img width="3198" height="1704" alt="Data and method" src="https://github.com/user-attachments/assets/a12260c3-4508-4d30-8f88-db4c014cbde3" />

Shows whether each data source is connected, lets you force an update or pull the latest Fed reports, and explains how the classifications work and where the data has gaps.

## Tech stack

- Python 3.11+
- Streamlit (1.40+) for the UI, with a custom CSS theme
- Plotly for charts
- pandas and NumPy for the data work
- httpx for API calls
- SQLite for storage
- OpenAI API (`gpt-4o-mini` by default)
- pytest for tests

## Running it locally

Clone it and install the requirements:

```bash
git clone https://github.com/<your-username>/riskradar_ai.git
cd riskradar_ai
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Make your `.env` file from the example:

```bash
cp .env.example .env             # on Windows: copy .env.example .env
```

Then open it and add your keys:

```
OPENAI_API_KEY=sk-...
FRED_API_KEY=your32characterlowercasefredkey
SEC_USER_AGENT=Your Name your.email@example.com
```

You can get a FRED key for free at [fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys). It's 32 lowercase letters and numbers, so don't wrap it in quotes. For the SEC one, just put your real name and email. The OpenAI key comes from [platform.openai.com](https://platform.openai.com/api-keys).

Start the app:

```bash
streamlit run app.py
```

It opens at http://localhost:8501. The first load takes about a minute because it's pulling everything. After that it's quick. If something isn't loading, check the Data & method tab to see which source has a problem.

To run the tests:

```bash
pytest
```

A few optional settings you can add to `.env`:

| Variable | Default | What it does |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4o-mini` | Which model to use |
| `OPENAI_BASE_URL` | OpenAI | Point it at any OpenAI-compatible API |
| `RISKRADAR_REFRESH_HOURS` | `6` | How old the data can get before it reloads |
| `OFR_LEVERAGE_MNEMONIC` | auto | Pin a specific OFR leverage series |
| `RISKRADAR_DB` | `riskradar.db` | Where the database file goes |

## Project layout

```
riskradar_ai/
├── app.py                    # the Streamlit app
├── config/thresholds.toml    # indicators, series IDs and thresholds
├── riskradar/
│   ├── calc.py               # all the calculations
│   ├── engine.py             # applies thresholds, creates alerts
│   ├── stress.py             # stress test scenarios
│   ├── fred.py               # FRED client
│   ├── edgar.py              # SEC EDGAR client
│   ├── ofr.py                # OFR client
│   ├── fedreports.py         # pulls Fed report text
│   ├── llm.py                # OpenAI calls and the answer checks
│   ├── pipeline.py           # ties fetching and storage together
│   ├── db.py                 # SQLite
│   └── ui.py                 # styling and UI pieces
├── tests/
├── .streamlit/config.toml    # theme
├── requirements.txt
└── .env.example
```

## Known limitations

- The thresholds are my own starting points, not calibrated risk levels. Change them in `config/thresholds.toml` if you want.
- Since April 2026 FRED only gives about 3 years of high yield spread history and about 10 years of S&P 500 history, so some percentile and drawdown calculations work on shorter windows.
- A lot of these series are monthly or quarterly, so they lag. Always check the date on the card.
- Companies tag debt and capex differently in their filings, so the numbers aren't perfectly comparable across companies. The tags used are shown on each card.
- The Fed report fetcher reads the HTML pages. If the Fed changes their site layout it might break, in which case you can paste an excerpt manually in the Data & method tab.

## Disclaimer

This is a personal research project. Nothing in it is investment advice, a forecast or an official risk rating.
