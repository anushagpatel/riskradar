"""Hypothetical stress tests. Deterministic arithmetic on user-chosen assumptions.

These are illustrations of mechanics, NOT forecasts or predictions. Every result carries its
assumptions so the numbers can be audited and reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StressResult:
    name: str
    outputs: dict[str, float | str]
    assumptions: dict[str, float | str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        out = "; ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in self.outputs.items())
        ass = "; ".join(f"{k}={v}" for k, v in self.assumptions.items())
        return f"{self.name}: {out}. Assumptions: {ass}. HYPOTHETICAL, not a forecast."


def hedge_fund_leverage_shock(leverage: float, price_shock_pct: float) -> StressResult:
    """Gross-assets / net-assets leverage L; asset prices move by s%.

    NAV change (% of NAV) = L * s. To restore leverage L, the fund must sell assets worth
    s*(1-L) of its initial gross assets (positive when prices fall and L > 1).
    """
    if leverage < 1:
        raise ValueError("Gross-to-net leverage must be >= 1")
    s = price_shock_pct / 100.0
    nav_change = leverage * s  # fraction of initial NAV
    wiped_out = nav_change <= -1.0
    new_nav_ratio = max(0.0, 1.0 + nav_change)
    sales_frac_gross = 0.0 if wiped_out else max(0.0, s * (1.0 - leverage))
    outputs = {
        "NAV change (% of initial NAV)": nav_change * 100.0,
        "Forced deleveraging sales (% of initial gross assets)": sales_frac_gross * 100.0,
        "Remaining NAV (% of initial NAV)": new_nav_ratio * 100.0,
        "Fund wiped out": "yes" if wiped_out else "no",
    }
    notes = ["Assumes the fund holds leverage constant after the shock (mechanical deleveraging only); "
             "ignores margin terms, hedges, liquidity and price impact of forced sales."]
    return StressResult("Hedge fund leverage shock", outputs,
                        {"gross-to-net leverage": leverage, "asset price shock %": price_shock_pct}, notes)


def ndfi_credit_loss(exposure_bn: float, spread_widening_bps: float, lgd_pct: float = 60.0,
                     bank_capital_bn: float | None = None) -> StressResult:
    """Credit-triangle approximation: spread ~ PD x LGD, so added annual expected loss
    ~= exposure x spread widening. Implied PD increase = widening / LGD."""
    if exposure_bn < 0 or not 0 < lgd_pct <= 100:
        raise ValueError("Exposure must be >= 0 and LGD in (0, 100]")
    widening = spread_widening_bps / 1e4
    added_loss = exposure_bn * widening
    implied_pd_pp = widening / (lgd_pct / 100.0) * 100.0
    outputs: dict[str, float | str] = {
        "Implied PD increase (pp)": implied_pd_pp,
        "Added annual expected loss ($bn)": added_loss,
    }
    if bank_capital_bn:
        outputs["Added loss as % of stated capital"] = added_loss / bank_capital_bn * 100.0
    return StressResult("NDFI lending credit-loss stress", outputs,
                        {"exposure $bn": exposure_bn, "spread widening bps": spread_widening_bps, "LGD %": lgd_pct,
                         "capital $bn": bank_capital_bn if bank_capital_bn else "not provided"},
                        ["Credit-triangle approximation; ignores correlation, collateral structure and timing."])


def ai_debt_service(debt_bn: float, avg_rate_pct: float, ocf_bn: float, capex_bn: float,
                    ocf_decline_pct: float, rate_increase_pp: float) -> StressResult:
    """Interest coverage and capex/OCF before and after an OCF decline and a refinancing-rate rise
    applied to the entire debt stock (a deliberately conservative simplification)."""
    if debt_bn < 0 or ocf_bn <= 0:
        raise ValueError("Debt must be >= 0 and operating cash flow must be positive")
    base_int = debt_bn * avg_rate_pct / 100.0
    new_ocf = ocf_bn * (1 - ocf_decline_pct / 100.0)
    new_int = debt_bn * (avg_rate_pct + rate_increase_pp) / 100.0
    cov = lambda o, i: float("inf") if i == 0 else o / i  # noqa: E731
    outputs = {
        "Interest expense before ($bn)": base_int,
        "Interest expense after ($bn)": new_int,
        "OCF / interest before (x)": cov(ocf_bn, base_int),
        "OCF / interest after (x)": cov(new_ocf, new_int) if new_ocf > 0 else 0.0,
        "Capex / OCF before": capex_bn / ocf_bn,
        "Capex / OCF after": capex_bn / new_ocf if new_ocf > 0 else float("inf"),
    }
    return StressResult("AI financing debt-service stress", outputs,
                        {"debt $bn": debt_bn, "avg rate %": avg_rate_pct, "OCF $bn": ocf_bn, "capex $bn": capex_bn,
                         "OCF decline %": ocf_decline_pct, "rate increase pp": rate_increase_pp},
                        ["Repricing the whole debt stock overstates near-term effects; most debt is fixed-rate."])


def agricultural_loan_stress(loans_bn: float, delinquency_pct: float, delinquency_increase_pp: float,
                             loss_given_delinquency_pct: float = 30.0) -> StressResult:
    """Delinquent balances and an illustrative loss on the *added* delinquent balances."""
    if loans_bn < 0 or delinquency_pct < 0:
        raise ValueError("Loans and delinquency must be >= 0")
    new_rate = delinquency_pct + delinquency_increase_pp
    base_del = loans_bn * delinquency_pct / 100.0
    new_del = loans_bn * new_rate / 100.0
    added_loss = (new_del - base_del) * loss_given_delinquency_pct / 100.0
    return StressResult("Agricultural lending stress", {
        "Delinquent balances before ($bn)": base_del,
        "Delinquent balances after ($bn)": new_del,
        "Illustrative loss on added delinquencies ($bn)": added_loss,
    }, {"loans $bn": loans_bn, "delinquency %": delinquency_pct, "increase pp": delinquency_increase_pp,
        "loss given delinquency %": loss_given_delinquency_pct},
        ["Illustrative only; actual losses depend on collateral (farmland values), guarantees and timing."])
