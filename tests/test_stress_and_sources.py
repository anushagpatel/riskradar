import pandas as pd

from riskradar import edgar, fedreports, llm, ofr, stress


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- stress tests

def test_hedge_fund_shock_math():
    r = stress.hedge_fund_leverage_shock(5.0, -10.0)
    assert close(r.outputs["NAV change (% of initial NAV)"], -50.0)
    assert close(r.outputs["Remaining NAV (% of initial NAV)"], 50.0)
    # sales = s*(1-L) = -0.10 * -4 = 40% of initial gross assets
    assert close(r.outputs["Forced deleveraging sales (% of initial gross assets)"], 40.0)
    assert r.outputs["Fund wiped out"] == "no"


def test_hedge_fund_wipeout_and_validation():
    assert stress.hedge_fund_leverage_shock(10.0, -10.0).outputs["Fund wiped out"] == "yes"
    try:
        stress.hedge_fund_leverage_shock(0.5, -5)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_ndfi_credit_triangle():
    r = stress.ndfi_credit_loss(1000.0, 100.0, 50.0, bank_capital_bn=200.0)
    assert close(r.outputs["Added annual expected loss ($bn)"], 10.0)
    assert close(r.outputs["Implied PD increase (pp)"], 2.0)
    assert close(r.outputs["Added loss as % of stated capital"], 5.0)


def test_ai_debt_service():
    r = stress.ai_debt_service(100.0, 4.0, 50.0, 40.0, 20.0, 2.0)
    assert close(r.outputs["Interest expense before ($bn)"], 4.0)
    assert close(r.outputs["Interest expense after ($bn)"], 6.0)
    assert close(r.outputs["OCF / interest before (x)"], 12.5)
    assert close(r.outputs["OCF / interest after (x)"], 40.0 / 6.0)
    assert close(r.outputs["Capex / OCF after"], 1.0)


def test_agricultural_stress():
    r = stress.agricultural_loan_stress(100.0, 1.0, 2.0, 30.0)
    assert close(r.outputs["Delinquent balances after ($bn)"], 3.0)
    assert close(r.outputs["Illustrative loss on added delinquencies ($bn)"], 0.6)


def test_stress_summary_is_labeled_hypothetical():
    assert "HYPOTHETICAL" in stress.hedge_fund_leverage_shock(3.0, -5.0).summary()


# ---------------------------------------------------------------- EDGAR parsing

def _fact(end, val, start=None, form="10-K", fp="FY", filed="2025-02-01"):
    d = {"end": end, "val": val, "form": form, "fp": fp, "filed": filed}
    if start:
        d["start"] = start
    return d


FACTS = {"facts": {"us-gaap": {
    "Revenues": {"units": {"USD": [_fact("2022-12-31", 100e9, "2022-01-01"), _fact("2023-12-31", 120e9, "2023-01-01")]}},
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        _fact("2023-12-31", 999e9, "2023-01-01"),  # lower priority; must NOT override Revenues for 2023
        _fact("2024-12-31", 150e9, "2024-01-01"),
        _fact("2024-06-30", 70e9, "2024-01-01", form="10-Q", fp="Q2"),  # ignored: not a 10-K annual
        _fact("2024-03-31", 40e9, "2024-01-01"),  # ignored: duration ~90 days
    ]}},
    "LongTermDebt": {"units": {"USD": [_fact("2022-12-31", 10e9), _fact("2023-12-31", 12e9)]}},
    "LongTermDebtNoncurrent": {"units": {"USD": [_fact("2022-12-31", 9e9), _fact("2023-12-31", 11e9), _fact("2024-12-31", 20e9)]}},
}}}


def test_flow_merge_across_tags_with_priority():
    s, tags = edgar.extract_metric(FACTS, "revenue")
    assert list(s.round(1).values) == [100.0, 120.0, 150.0]
    assert tags == ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]


def test_debt_uses_single_tag_with_latest_data():
    s, tags = edgar.extract_metric(FACTS, "total_debt")
    assert tags == ["LongTermDebtNoncurrent"] and list(s.values) == [9.0, 11.0, 20.0]


def test_missing_metric_returns_empty_not_error():
    s, tags = edgar.extract_metric(FACTS, "capex")
    assert s.empty and tags == []


def test_edgar_requires_descriptive_user_agent():
    try:
        edgar._headers("")
        assert False, "expected EdgarError"
    except edgar.EdgarError:
        pass
    assert "User-Agent" in edgar._headers("Jane Doe jane@example.com")


def test_restated_value_prefers_latest_filing():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        _fact("2023-12-31", 100e9, "2023-01-01", filed="2024-02-01"),
        _fact("2023-12-31", 101e9, "2023-01-01", filed="2025-02-01")]}}}}}
    s, _ = edgar.extract_metric(facts, "revenue")
    assert close(s.iloc[0], 101.0)


# ---------------------------------------------------------------- OFR / Fed reports

def test_ofr_candidate_picker():
    results = [
        {"mnemonic": "FPF-ALLQHF_FOO", "field": "description/name", "value": "Something else"},
        {"mnemonic": "FPF-ALLQHF_LEV_B", "field": "description/name", "value": "Leverage ratio B"},
        {"mnemonic": "FPF-ALLQHF_LEV_A", "field": "description/name", "value": "Leverage ratio A"},
        {"mnemonic": "FPF-STRATEGY_LEV", "field": "description/name", "value": "Leverage by strategy"},
        {"mnemonic": "FPF-ALLQHF_LEV_C", "field": "mnemonic", "value": "FPF-ALLQHF_LEV_C"},
    ]
    pick = ofr.pick_leverage_candidate(results, ["leverage"], "FPF-ALLQHF")
    assert pick["mnemonic"] == "FPF-ALLQHF_LEV_A"
    assert ofr.pick_leverage_candidate([], ["leverage"], "FPF-ALLQHF") is None


def test_fed_report_link_discovery_prefers_html_and_newest_first():
    html = ('<a href="/publications/files/financial-stability-report-20250425.pdf">pdf</a>'
            '<a href="/publications/financial-stability-report-20250425.htm">html</a>'
            '<a href="/publications/files/financial-stability-report-20251107.pdf">pdf2</a>')
    links = fedreports.find_report_links(html)
    assert [d for d, _ in links] == ["20251107", "20250425"]
    assert links[1][1].endswith(".htm") and links[1][1].startswith("https://www.federalreserve.gov")


def test_html_to_text_skips_scripts_and_splits_paragraphs():
    text = fedreports.html_to_text("<html><script>var x=1;</script><p>Hello hedge fund leverage.</p><p>Second.</p></html>")
    assert "var x" not in text and "Hello hedge fund leverage." in text


def test_excerpt_selection_ranks_by_keyword_hits():
    paras = ["x" * 130, "Hedge fund leverage remains high; hedge fund borrowing from prime brokers rose. " + "y" * 60,
             "Farmland values and agricultural credit conditions. " + "z" * 80]
    terms = fedreports.terms_for_question("What happens when highly leveraged hedge funds face corrections?")
    ex = fedreports.select_excerpts(fedreports.split_paragraphs(" \n\n ".join(paras)), terms, k=1)
    assert len(ex) == 1 and ex[0].startswith("Hedge fund leverage")


# ---------------------------------------------------------------- LLM guards

def test_validate_citations_flags_unknown_ids():
    ans = "Spreads rose [M1][A2]. Also [M9] and [R1]."
    assert llm.validate_citations(ans, {"M1", "A2", "R1"}) == ["M9"]


def test_unsupported_number_detection():
    evidence = "[M1] VIX | latest 18.24 | change +1.70% | obs 2026-11-25 | previous 17.94"
    ok = "VIX is 18.2 [M1], up 1.7% from 17.9."
    bad = "VIX is 18.2 [M1], while credit losses reached 7.5 percent."
    assert llm.find_unsupported_numbers(ok, evidence) == []
    assert llm.find_unsupported_numbers(bad, evidence) == [7.5]


def test_evidence_marks_unavailable_data_and_assigns_ids():
    from riskradar import engine
    spec = {"label": "X", "category": "Cat", "source": "fred", "rules": []}
    res = engine.build_result("x", spec, pd.Series(dtype=float), source_url="http://u", last_refresh=None, error="no key")
    text, ids = llm.build_evidence([res], [], [{"title": "FSR", "url": "http://r", "text": "excerpt"}])
    assert "DATA UNAVAILABLE" in text and {"M1", "R1"} <= ids
