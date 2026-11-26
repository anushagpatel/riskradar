"""RiskRadar AI - Market & Credit Risk Intelligence Platform (Streamlit MVP).

Research tool only: no personalized investment advice, no crisis predictions.
Run with:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from riskradar import calc, db, engine, fedreports, llm, pipeline, stress, ui

# .env next to app.py always wins over stale variables already set in the terminal
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
st.set_page_config(page_title="RiskRadar AI", page_icon="📡", layout="wide", initial_sidebar_state="collapsed")
st.markdown(ui.CSS, unsafe_allow_html=True)

CFG = engine.load_config()
DISCLAIMER = CFG["meta"]["disclaimer"]
CATEGORY_ORDER = ["Market volatility", "Corporate credit spreads", "Interest rates", "Equity market drawdown",
                  "AI financing", "Hedge fund leverage", "Agricultural lending stress", "NDFI lending growth",
                  "Bank lending"]
MA_WINDOW = {252: 50, 52: 13, 12: 6, 4: 4}
EXAMPLE_QUESTIONS = [
    "Why is AI financing considered a potential financial stability risk?",
    "What happens when highly leveraged hedge funds experience asset price corrections?",
    "Which financial indicators are currently showing elevated stress?",
    "How could increasing NDFI lending affect traditional banks?",
    "Are agricultural lending conditions deteriorating?",
    "Summarize the latest available Federal Reserve financial stability findings.",
    "What changed compared with the previous reporting period?",
]
SCENARIOS = ["Hedge fund leverage shock", "NDFI lending credit-loss", "AI financing debt-service",
             "Agricultural lending stress"]


@st.cache_resource
def get_conn():
    return db.connect(os.getenv("RISKRADAR_DB", "riskradar.db"))


conn = get_conn()


# ------------------------------------------------------------------ helpers

def fmt(x, unit="", nd=2) -> str:
    if x is None:
        return "n/a"
    return f"{x:,.{nd}f}{'' if unit in ('', 'index', 'index pts') else ' ' + unit}"


def fmt_num(x, nd=2) -> str:
    return "n/a" if x is None else f"{x:,.{nd}f}"


def fmt_change(r: engine.IndicatorResult) -> str | None:
    if r.change is None:
        return None
    return f"{r.change:+.2f}%" if r.change_kind == "pct" else f"{r.change:+.2f} {r.unit}"


def make_chart(r: engine.IndicatorResult) -> go.Figure:
    s = r.series.dropna()
    ppy = CFG["indicators"].get(r.key, {}).get("periods_per_year", 1)
    if ppy == 252:
        s = s.iloc[-1260:]  # ~5 years of daily data keeps charts responsive
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines+markers" if len(s) < 40 else "lines", name="Value",
                             line=dict(color=ui.ACCENT, width=1.7), marker=dict(size=5)))
    w = MA_WINDOW.get(ppy)
    if w and len(s) > w:
        fig.add_trace(go.Scatter(x=s.index, y=calc.moving_average(s, w), mode="lines", name=f"{w}-period average",
                                 line=dict(color="#98A2B3", width=1.3, dash="dot")))
    for rule in r.rules_config:
        if rule["type"] == "level":
            for lvl, color in (("elevated", ui.STATUS["Elevated"]["fg"]), ("high", ui.STATUS["High"]["fg"])):
                fig.add_hline(y=rule[lvl], line_dash="dash", line_width=1, line_color=color, opacity=0.6,
                              annotation_text=lvl.capitalize(), annotation_position="top left",
                              annotation_font=dict(size=10, color=color))
    return ui.style_figure(fig, r.unit)


def report_excerpts(terms: list[str], k: int = 6, both: bool = False) -> list[dict]:
    reps = db.list_reports(conn)[: 2 if both else 1]
    out = []
    for rep in reps:
        paras = fedreports.split_paragraphs(rep["text"])
        for text in fedreports.select_excerpts(paras, terms, k=k if not both else max(2, k // 2)):
            out.append({"title": f"{rep['title']} [{rep['report_date']}]", "url": rep["url"], "text": text})
    return out


def show_guard_warnings(answer: str, evidence: str, ids: set[str]) -> None:
    bad = llm.validate_citations(answer, ids)
    if bad:
        st.warning(f"This answer cites sources that don't exist ({', '.join(bad)}). Treat those statements as unsupported.",
                   icon=":material/report:")
    odd = llm.find_unsupported_numbers(answer, evidence)
    if odd:
        st.warning("These numbers weren't found in the supplied evidence. Verify them before use: "
                   + ", ".join(f"{n:g}" for n in odd), icon=":material/fact_check:")


def lede(text: str) -> None:
    st.markdown(f'<p class="rr-lede">{text}</p>', unsafe_allow_html=True)


def fred_key_check() -> tuple[bool, str]:
    """Check the key's format locally and describe it without revealing it."""
    raw = os.getenv("FRED_API_KEY", "")
    key = raw.strip().strip('"').strip("'")
    if not key:
        return False, "No key found. Add <code>FRED_API_KEY=yourkey</code> to <code>.env</code> next to app.py."
    masked = f"<code>{key[:4]}…{key[-4:]}</code> ({len(key)} characters)"
    if key == "abcdefghijklmnopqrstuvwxyz123456":
        return False, f"The app is using FRED's example key {masked}. Paste your own key from fredaccount.stlouisfed.org/apikeys."
    if not re.fullmatch(r"[a-z0-9]{32}", key):
        why = ("it has uppercase letters" if key.lower() != key and re.fullmatch(r"[A-Za-z0-9]{32}", key)
               else f"it should be exactly 32 lowercase letters and digits")
        return False, f"The key the app sees is {masked}, but {why}. Check for extra text, spaces or a comment on that line."
    return True, f"Key found: {masked}. If FRED still rejects it, make sure it's listed at fredaccount.stlouisfed.org/apikeys."


def keys_status() -> dict[str, bool]:
    return {"openai": llm.is_configured(), "fred": bool(os.getenv("FRED_API_KEY")),
            "sec": "@" in os.getenv("SEC_USER_AGENT", "")}


# ------------------------------------------------------------------ automatic data loading

REFRESH_HOURS = float(os.getenv("RISKRADAR_REFRESH_HOURS", "6"))
RETRY_MINUTES = 15  # after a failed load, wait this long before trying again on page open


@st.cache_resource
def refresh_lock():
    import threading
    return threading.Lock()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def data_is_stale() -> bool:
    """True when there's no successful load within REFRESH_HOURS and no attempt in the last RETRY_MINUTES."""
    metas = db.all_meta(conn)
    now = datetime.now(timezone.utc)
    successes = [t for t in (_parse_ts(m.get("last_success")) for m in metas) if t]
    attempts = [t for t in (_parse_ts(m.get("last_attempt")) for m in metas) if t]
    if successes and now - max(successes) < timedelta(hours=REFRESH_HOURS):
        return False
    return not attempts or now - max(attempts) > timedelta(minutes=RETRY_MINUTES)


def run_refresh() -> list[dict]:
    status = pipeline.refresh_all(
        conn, CFG, fred_key=os.getenv("FRED_API_KEY", ""), sec_user_agent=os.getenv("SEC_USER_AGENT", ""),
        ofr_override=os.getenv("OFR_LEVERAGE_MNEMONIC", ""))
    st.session_state["refresh_status"] = status
    return status


def fetch_fed_reports() -> None:
    import httpx

    with httpx.Client(headers={"User-Agent": os.getenv("SEC_USER_AGENT") or "RiskRadarAI research tool"}) as c:
        for rep in fedreports.fetch_latest_reports(c, n=2):
            db.save_report(conn, rep["url"], rep["title"], rep["report_date"], rep["text"])


@st.cache_resource
def report_attempts() -> dict:
    return {}


def reports_due() -> bool:
    """Try fetching Fed reports when none are stored, at most once per refresh window."""
    last = report_attempts().get("last")
    return not db.list_reports(conn) and (last is None or datetime.now(timezone.utc) - last > timedelta(hours=REFRESH_HOURS))


def auto_load() -> None:
    """Load fresh data on the first visit so the page is ready without any clicks."""
    if st.session_state.get("auto_loaded"):
        return
    st.session_state["auto_loaded"] = True
    if not (data_is_stale() or reports_due()):
        return
    loader = st.empty()
    with loader.container():
        st.markdown(ui.loading_html(), unsafe_allow_html=True)
        with refresh_lock():  # another session may be loading right now; wait, then re-check
            if data_is_stale():
                status = run_refresh()
                failed = [s for s in status if not s["ok"]]
                if failed:
                    st.session_state["refresh_warning"] = (
                        f"{len(failed)} of {len(status)} data sources couldn't be updated. See Data & method for details.")
            if reports_due():
                report_attempts()["last"] = datetime.now(timezone.utc)
                try:
                    fetch_fed_reports()
                except Exception:  # noqa: BLE001 - reports are optional context
                    pass
    loader.empty()


# ------------------------------------------------------------------ header

h_brand, h_status = st.columns([3, 2], vertical_alignment="center")
with h_brand:
    st.markdown(ui.header_html("Market and credit risk intelligence"), unsafe_allow_html=True)

auto_load()
if msg := st.session_state.pop("refresh_warning", None):
    st.toast(msg, icon=":material/warning:")

# ------------------------------------------------------------------ data

results = pipeline.build_results(conn, CFG)
db.insert_alerts(conn, engine.alerts_from_results(results))
stored_alerts = db.recent_alerts(conn, 200)
refresh_times = [r.last_refresh for r in results if r.last_refresh]
last_refresh = ui.pretty_datetime(max(refresh_times)) if refresh_times else "never"

with h_status:
    if refresh_times:
        st.markdown(ui.status_html(f"Live data, updated {last_refresh}", "#067647"), unsafe_allow_html=True)
    else:
        st.markdown(ui.status_html("No live data yet", "#667085"), unsafe_allow_html=True)


# ------------------------------------------------------------------ assistant (floating chat widget)

def ask_suggested(q: str) -> None:
    st.session_state["pending_q"] = q


def clear_chat() -> None:
    st.session_state.chat = []


def toggle_chat() -> None:
    st.session_state["chat_open"] = not st.session_state.get("chat_open", False)


def answer_question(prompt: str) -> str | None:
    both = any(w in prompt.lower() for w in ("change", "previous", "compared", "since", "versus", "vs"))
    excerpts = report_excerpts(fedreports.terms_for_question(prompt), k=6, both=both)
    evidence, ids = llm.build_evidence(results, stored_alerts[:25], excerpts)
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat[:-1]]
    try:
        with st.spinner("Thinking..."):
            answer = llm.chat(llm.chat_messages(history, prompt, evidence), max_tokens=1200)
    except llm.LLMError as e:
        st.error(str(e))
        return None
    st.markdown(answer)
    show_guard_warnings(answer, evidence, ids)
    return answer


@st.fragment
def chat_widget() -> None:
    """Launcher button fixed to the bottom-right corner; opens a chat window above it."""
    st.session_state.setdefault("chat", [])
    is_open = st.session_state.get("chat_open", False)
    ready = llm.is_configured()

    if is_open:
        with st.container(key="chatdrawer"):
            hl, hc, hx = st.columns([5, 1, 1], vertical_alignment="center", gap="small")
            hl.markdown(ui.chat_header_html(ready), unsafe_allow_html=True)
            if st.session_state.chat:
                hc.button("", icon=":material/delete_sweep:", key="chat_clear", on_click=clear_chat,
                          help="Clear conversation")
            hx.button("", icon=":material/close:", key="chat_close", on_click=toggle_chat, help="Close")

            msgs = st.container(height=430, border=False, key="chatmsgs")
            pending = st.session_state.pop("pending_q", None)
            with msgs:
                if not st.session_state.chat and not pending:
                    with st.chat_message("assistant", avatar=":material/radar:"):
                        st.markdown("Hi, I'm the RiskRadar assistant. Ask me about today's indicators, recent alerts "
                                    "or the latest Federal Reserve findings. I cite the evidence behind every answer."
                                    if ready else
                                    "Add `OPENAI_API_KEY` to your `.env` file and restart the app to start chatting.")
                    if ready:
                        for i, q in enumerate(EXAMPLE_QUESTIONS[:4]):
                            st.button(q, key=f"ex_{i}", on_click=ask_suggested, args=(q,), use_container_width=True)
                for m in st.session_state.chat:
                    with st.chat_message(m["role"], avatar=":material/radar:" if m["role"] == "assistant"
                                         else ":material/person:"):
                        st.markdown(m["content"])
            prompt = st.chat_input("Ask RiskRadar a question", key="home_chat", disabled=not ready) or pending
            if prompt and ready:
                st.session_state.chat.append({"role": "user", "content": prompt})
                with msgs:
                    with st.chat_message("user", avatar=":material/person:"):
                        st.markdown(prompt)
                    with st.chat_message("assistant", avatar=":material/radar:"):
                        answer = answer_question(prompt)
                if answer:
                    st.session_state.chat.append({"role": "assistant", "content": answer})
            st.caption("Research support only, not investment advice.")

    st.button("Close assistant" if is_open else "Ask RiskRadar", key="chat_fab", on_click=toggle_chat,
              icon=":material/keyboard_arrow_down:" if is_open else ":material/forum:", type="primary")


tab_dash, tab_alerts, tab_ai, tab_stress, tab_method = st.tabs(
    ["Overview", "Alerts", "AI briefing", "Stress test", "Data & method"])

# ------------------------------------------------------------------ overview (home)
GRID_COLS = 4
SEVERITY_RANK = {"High": 0, "Elevated": 1, "Normal": 2, "Insufficient data": 3}

with tab_dash:
    st.markdown(ui.overview_html(results, CATEGORY_ORDER, last_refresh), unsafe_allow_html=True)

    if all(r.latest is None for r in results):
        k = keys_status()
        missing = [n for n, ok in (("FRED API key", k["fred"]), ("SEC user agent", k["sec"])) if not ok]
        msg = ("Live data couldn't be loaded. Open **Data & method** to see why and click **Update now** after fixing it."
               if not missing else f"Add your {' and '.join(missing)} to the `.env` file and restart the app.")
        st.info(msg, icon=":material/info:")

    f1, f2, f3, _ = st.columns([1.3, 2.2, 1.2, 1.3], vertical_alignment="bottom")
    with f1:
        view = st.segmented_control("Show", ["All indicators", "Flagged only"], default="All indicators",
                                    label_visibility="collapsed") or "All indicators"
    with f2:
        cats_present = [c for c in CATEGORY_ORDER if any(r.category == c for r in results)]
        chosen = st.multiselect("Risk areas", cats_present, placeholder="All risk areas", label_visibility="collapsed")
    with f3:
        sort_by = st.selectbox("Sort", ["Sort by risk area", "Sort by severity"], label_visibility="collapsed")

    cards = [r for r in results if r.category in (chosen or cats_present)]
    if view == "Flagged only":
        cards = [r for r in cards if r.classification in ("High", "Elevated")]
    cat_rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    if sort_by == "Sort by severity":
        cards.sort(key=lambda r: (SEVERITY_RANK.get(r.classification, 9), cat_rank.get(r.category, 99)))
    else:
        cards.sort(key=lambda r: cat_rank.get(r.category, 99))

    if not cards:
        st.markdown('<div class="rr-empty">Nothing is flagged in the selected risk areas. '
                    'Switch to <b>All indicators</b> to see everything.</div>', unsafe_allow_html=True)
    for i in range(0, len(cards), GRID_COLS):
        cols = st.columns(GRID_COLS, gap="medium")
        for col, r in zip(cols, cards[i:i + GRID_COLS]):
            with col, st.container(key=f"card_{r.key}"):
                if r.latest is None:
                    st.markdown(ui.card_empty_html(r, r.error or "No data available for this indicator yet."),
                                unsafe_allow_html=True)
                    st.markdown(f'<a class="rr-link" href="{r.source_url}" target="_blank">View source</a>',
                                unsafe_allow_html=True)
                    continue
                change = fmt_change(r)
                unit = "" if r.unit in ("", "index", "index pts") else r.unit
                st.markdown(ui.card_head_html(r, fmt_num(r.latest), unit,
                                              f"{change} vs previous" if change else "No prior value",
                                              ui.pretty_date(r.obs_date)), unsafe_allow_html=True)
                st.plotly_chart(make_chart(r), key=f"chart_{r.key}", config={"displayModeBar": False})
                with st.expander("Details"):
                    st.markdown(f"**Previous value:** {fmt(r.previous, r.unit)}  \n"
                                f"**Observation date:** {ui.pretty_date(r.obs_date)}  \n"
                                f"**Last refreshed:** {ui.pretty_datetime(r.last_refresh)}  \n"
                                f"**Source:** [{r.source}]({r.source_url})")
                    if r.signals:
                        st.markdown("**Rule checks**")
                        st.markdown("\n".join(f"- {ui.STATUS[s.status]['label']}: {s.condition}" for s in r.signals))
                    if r.note:
                        st.caption(r.note)

    st.markdown(f'<div class="rr-foot">{DISCLAIMER} Research support only. This is not investment advice and does '
                f'not predict financial crises.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ alerts
with tab_alerts:
    lede("An alert is recorded each time an indicator crosses one of its thresholds. "
         "Thresholds live in <code>config/thresholds.toml</code> and are heuristic research signals.")
    if not stored_alerts:
        st.markdown('<div class="rr-empty">No alerts yet. Alerts appear here after a data refresh finds an indicator '
                    'above its normal range.</div>', unsafe_allow_html=True)
    else:
        df = pd.DataFrame(stored_alerts).rename(columns={
            "created_at": "Recorded", "category": "Risk area", "indicator": "Indicator",
            "current_value": "Current", "previous_value": "Previous", "condition": "Trigger",
            "severity": "Severity", "obs_date": "Observation date", "source_url": "Source"}).drop(columns=["id"])
        a1, a2, a3 = st.columns([1, 1, 3], vertical_alignment="bottom")
        a1.metric("High", int((df["Severity"] == "High").sum()))
        a2.metric("Elevated", int((df["Severity"] == "Elevated").sum()))
        with a3:
            sev = st.segmented_control("Severity", ["High", "Elevated"], default=["High", "Elevated"],
                                       selection_mode="multi", label_visibility="collapsed") or ["High", "Elevated"]
        df["Severity"] = df["Severity"].map(lambda s: f"{'🔴' if s == 'High' else '🟠'} {s}")
        df = df[df["Severity"].str.split(" ").str[-1].isin(sev)]
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"Source": st.column_config.LinkColumn("Source", display_text="Open"),
                                    "Current": st.column_config.NumberColumn(format="%.2f"),
                                    "Previous": st.column_config.NumberColumn(format="%.2f"),
                                    "Trigger": st.column_config.TextColumn(width="large")})

# ------------------------------------------------------------------ AI briefing
with tab_ai:
    lede("Get a written briefing on today's readings. The model receives the calculated metrics, recent alerts and "
         "stored Federal Reserve report excerpts. It interprets the numbers; it never calculates them.")
    if not db.list_reports(conn):
        st.caption("Tip: add a Federal Reserve report in Data & method for a richer briefing.")
    if st.button("Generate briefing", type="primary", icon=":material/auto_awesome:"):
        if not llm.is_configured():
            st.error("Add OPENAI_API_KEY to your .env file, then restart the app.", icon=":material/key:")
        else:
            terms = list(dict.fromkeys(sum(fedreports.TOPIC_TERMS.values(), [])))
            evidence, ids = llm.build_evidence(results, stored_alerts[:25], report_excerpts(terms, k=8))
            with st.spinner("Writing your briefing..."):
                try:
                    answer = llm.chat(llm.analysis_messages(evidence), max_tokens=2200)
                    db.save_analysis(conn, llm.model_name(), answer, evidence)
                except llm.LLMError as e:
                    st.error(str(e))
    last = db.last_analysis(conn)
    if last:
        with st.container(key="panel_analysis"):
            st.caption(f"Generated {ui.pretty_datetime(last['created_at'])} with {last['model']}")
            st.markdown(last["content"])
            ids = set(re.findall(r"^\[([MARS]\d+)\]", last["evidence"], flags=re.M))
            show_guard_warnings(last["content"], last["evidence"], ids)
        with st.expander("Evidence sent to the model"):
            st.code(last["evidence"], language="text")
        st.caption(DISCLAIMER)
    else:
        st.markdown('<div class="rr-empty">No briefing yet. Click <b>Generate briefing</b> to create one.</div>',
                    unsafe_allow_html=True)

# ------------------------------------------------------------------ stress test
with tab_stress:
    lede("Run what-if arithmetic on assumptions you choose. Results are hypothetical, not forecasts, and every "
         "calculation is deterministic Python.")
    by_key = {r.key: r for r in results}

    def latest_of(key):
        r = by_key.get(key)
        return r.latest if r and r.latest is not None and r.status == "ok" else None

    scenario = st.segmented_control("Scenario", SCENARIOS, default=SCENARIOS[0]) or SCENARIOS[0]
    col_in, col_out = st.columns([1, 1.15], gap="large")
    res = None
    with col_in, st.container(key="panel_assumptions"):
        st.markdown("**Assumptions**")
        try:
            if scenario == "Hedge fund leverage shock":
                lv = latest_of("hf_leverage")
                st.caption(f"Prefilled with the latest OFR leverage reading ({fmt(lv)})." if lv
                           else "No OFR leverage data loaded, so enter your own figure.")
                L = st.number_input("Gross-to-net leverage (x)", 1.0, 50.0, float(lv) if lv and lv >= 1 else 5.0, 0.5)
                shock = st.slider("Asset price shock (%)", -50.0, 0.0, -10.0, 0.5)
                res = stress.hedge_fund_leverage_shock(L, shock)
            elif scenario == "NDFI lending credit-loss":
                ex = latest_of("ndfi_loans")
                exposure = st.number_input("NDFI exposure ($bn)", 0.0, 100000.0, float(ex) if ex else 1000.0, 10.0)
                bps = st.slider("Credit spread widening (bps)", 0, 1000, 150, 10)
                lgd = st.slider("Loss given default (%)", 5, 100, 60)
                cap = st.number_input("Capital base to compare against ($bn, optional)", 0.0, 100000.0, 0.0, 10.0)
                res = stress.ndfi_credit_loss(exposure, bps, lgd, cap or None)
            elif scenario == "AI financing debt-service":
                t = st.selectbox("Company", CFG["ai_financing"]["tickers"])
                d = db.load_series(conn, f"edgar:{t}:total_debt")
                o = db.load_series(conn, f"edgar:{t}:operating_cash_flow")
                c = db.load_series(conn, f"edgar:{t}:capex")
                have = len(d) and len(o) and len(c)
                st.caption(f"Prefilled from the latest SEC filing (fiscal year ending {ui.pretty_date(o.index[-1])})."
                           if have else "No SEC data loaded, so enter your own figures.")
                debt = st.number_input("Total debt ($bn)", 0.0, 10000.0, float(d.iloc[-1]) if have else 50.0, 1.0)
                ocf = st.number_input("Operating cash flow ($bn)", 0.1, 10000.0, float(o.iloc[-1]) if have else 100.0, 1.0)
                capex = st.number_input("Capital expenditure ($bn)", 0.0, 10000.0, float(c.iloc[-1]) if have else 60.0, 1.0)
                rate = st.slider("Average interest rate on debt (%)", 0.0, 15.0, 4.5, 0.1)
                dec = st.slider("Operating cash flow decline (%)", 0, 90, 20)
                inc = st.slider("Refinancing rate increase (pp)", 0.0, 10.0, 2.0, 0.25)
                res = stress.ai_debt_service(debt, rate, ocf, capex, dec, inc)
            else:
                dq = latest_of("ag_delinquency")
                loans = st.number_input("Agricultural production loans outstanding ($bn)", 0.0, 10000.0, 100.0, 5.0,
                                        help="Enter your own exposure figure. It isn't pulled automatically.")
                base = st.number_input("Current delinquency rate (%)", 0.0, 100.0, float(dq) if dq else 1.0, 0.1)
                inc = st.slider("Increase in delinquency rate (pp)", 0.0, 10.0, 1.5, 0.1)
                lgdel = st.slider("Loss on added delinquent balances (%)", 0, 100, 30)
                res = stress.agricultural_loan_stress(loans, base, inc, lgdel)
        except ValueError as e:
            st.error(str(e))

    with col_out:
        if res:
            st.session_state.setdefault("stress_summaries", {})[res.name] = res.summary()
            with st.container(key="panel_results"):
                st.markdown("**Hypothetical results**")
                items = list(res.outputs.items())
                for i in range(0, len(items), 2):
                    mcols = st.columns(2)
                    for mc, (k, v) in zip(mcols, items[i:i + 2]):
                        mc.metric(k, f"{v:,.2f}" if isinstance(v, float) else str(v))
                if res.notes:
                    st.caption(" ".join(res.notes))
            with st.expander("Assumptions used"):
                st.dataframe(pd.DataFrame({"Assumption": list(res.assumptions), "Value": [
                    str(v) for v in res.assumptions.values()]}), hide_index=True, use_container_width=True)
            if st.button("Explain with AI", icon=":material/auto_awesome:"):
                if not llm.is_configured():
                    st.error("Add OPENAI_API_KEY to your .env file, then restart the app.", icon=":material/key:")
                else:
                    evidence, ids = llm.build_evidence(results, stored_alerts[:15], report_excerpts(
                        list(dict.fromkeys(sum(fedreports.TOPIC_TERMS.values(), []))), k=4), stress=[res.summary()])
                    q = ("Explain what the hypothetical stress result [S1] illustrates, which transmission channels it could "
                         "activate, and which observed indicators (cite [M#]) are most relevant to monitor. Keep "
                         "'Observed' and 'Hypothetical' clearly separate.")
                    try:
                        with st.spinner("Explaining the scenario..."):
                            answer = llm.chat(llm.chat_messages([], q, evidence), max_tokens=1200)
                        st.markdown(answer)
                        show_guard_warnings(answer, evidence, ids)
                    except llm.LLMError as e:
                        st.error(str(e))

# ------------------------------------------------------------------ data & method
with tab_method:
    m_left, m_right = st.columns([1, 1], gap="large")

    with m_left:
        st.subheader("Connections")
        k = keys_status()
        st.markdown(ui.connection_html([
            (fred_key_check()[0], "FRED", "Market, rates and lending data. " + fred_key_check()[1]),
            (k["sec"], "SEC EDGAR", "Company filings for AI financing." + ("" if k["sec"] else
             " Set <code>SEC_USER_AGENT</code> to your name and email in <code>.env</code>.")),
            (k["openai"], "AI model", (f"Briefings and assistant use <code>{llm.model_name()}</code>." if k["openai"] else
             "Add <code>OPENAI_API_KEY</code> to <code>.env</code> to turn on AI features.")),
            (True, "OFR Hedge Fund Monitor", "Hedge fund leverage. No key needed."),
        ]), unsafe_allow_html=True)
        st.caption(f"Data reloads automatically when you open the app and it is more than {REFRESH_HOURS:g} hours "
                   f"old. Last update: {last_refresh}.")
        if st.button("Update now", icon=":material/refresh:", key="manual_refresh"):
            with st.spinner("Updating FRED, OFR and SEC EDGAR. This can take a minute."):
                with refresh_lock():
                    status = run_refresh()
            ok = sum(s["ok"] for s in status)
            st.toast(f"{ok} of {len(status)} sources updated.", icon=":material/check_circle:")
            st.rerun()
        if "refresh_status" in st.session_state:
            with st.expander("Last update results"):
                st.dataframe(pd.DataFrame(st.session_state["refresh_status"]), hide_index=True, use_container_width=True,
                             column_config={"ok": st.column_config.CheckboxColumn("OK")})

    with m_right:
        st.subheader("Federal Reserve reports")
        reps = db.list_reports(conn)
        st.caption((f"{len(reps)} report{'s' if len(reps) != 1 else ''} stored, latest from "
                    f"{ui.pretty_date(reps[0]['report_date'])}." if reps else "No reports stored yet. ")
                   + " Report text feeds the AI briefing and assistant.")
        if st.button("Fetch latest reports", icon=":material/download:"):
            try:
                with st.spinner("Fetching the Financial Stability Report..."):
                    fetch_fed_reports()
                st.success("Reports saved.")
            except fedreports.ReportError as e:
                st.error(str(e))
        with st.expander("Paste an excerpt instead"):
            with st.form("manual_report", border=False):
                rdate = st.date_input("Report date", value=None, format="YYYY-MM-DD")
                rtext = st.text_area("Excerpt text", height=140, placeholder="Paste report text here")
                if st.form_submit_button("Save excerpt"):
                    if not rtext.strip() or rdate is None:
                        st.warning("Add both a date and some text.")
                    else:
                        rd = rdate.isoformat()
                        h = hashlib.sha1(rtext.encode()).hexdigest()[:10]
                        db.save_report(conn, f"manual:{rd}:{h}", f"Manually added excerpt ({rd})", rd, rtext)
                        st.success("Excerpt saved.")

    st.subheader("How to read this dashboard")
    st.markdown(f"{DISCLAIMER}\n\n- Each indicator is classified only from its own thresholds in `config/thresholds.toml`; "
                "there is **no composite risk score**.\n- All numbers are computed deterministically in Python; the AI only "
                "interprets the supplied evidence.\n- Missing data is shown as unavailable and is never filled in.")
    st.subheader("Known data limitations")
    st.markdown(
        "- FRED has told users that, starting April 2026, the ICE BofA high-yield spread series carries only about 3 years of "
        "history, and S&P 500 history on FRED is limited to about 10 years, so percentile and drawdown rules use shorter windows.\n"
        "- Several series are quarterly or monthly and lag; check each observation date.\n"
        "- SEC XBRL tags vary by company. Debt and capex definitions may differ across firms (tags used are shown per indicator); "
        "capex excludes finance leases unless the company tags them as PP&E purchases.\n"
        "- The OFR leverage series is resolved at runtime; verify the selected series name below.")

    with st.expander("Threshold rules"):
        rows = [{"Indicator": r.label, "Risk area": r.category, "Rule": ru.get("name", ru["type"]), "Type": ru["type"],
                 "Elevated": ru["elevated"], "High": ru["high"]} for r in results for ru in r.rules_config]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    with st.expander("Stored series"):
        meta = db.all_meta(conn)
        if meta:
            st.dataframe(pd.DataFrame(meta)[["series_key", "title", "source", "last_obs", "last_success", "last_attempt",
                                             "last_error"]], hide_index=True, use_container_width=True)
        else:
            st.write("Nothing stored yet.")
chat_widget()
