"""
Ratio analysis: turns the three statements into the metrics an analyst looks at
first - growth, profitability, returns, leverage and cash quality - plus simple
trend flags.
"""

import pandas as pd

from .data import get


def compute_ratios(co: dict, tax_rate_fallback: float = 0.25) -> pd.DataFrame:
    inc, bal, cf = co["income"], co["balance"], co["cashflow"]

    revenue = get(inc, "Total Revenue", "Operating Revenue")
    gross = get(inc, "Gross Profit")
    ebitda = get(inc, "EBITDA", "Normalized EBITDA")
    ebit = get(inc, "EBIT", "Operating Income")
    net_income = get(inc, "Net Income", "Net Income Common Stockholders")
    pretax = get(inc, "Pretax Income")
    tax = get(inc, "Tax Provision")

    equity = get(bal, "Stockholders Equity", "Common Stock Equity")
    total_debt = get(bal, "Total Debt")
    cash = get(bal, "Cash And Cash Equivalents",
               "Cash Cash Equivalents And Short Term Investments")
    invested_capital = get(bal, "Invested Capital")

    ocf = get(cf, "Operating Cash Flow")
    capex = get(cf, "Capital Expenditure")  # reported as a negative number
    fcf = ocf + capex

    # Effective tax rate, falling back when it's distorted (losses, one-offs)
    tax_rate = (tax / pretax).where((pretax > 0) & (tax / pretax).between(0, 0.5),
                                    tax_rate_fallback)
    nopat = ebit * (1 - tax_rate)

    # Returns use the average of opening and closing balances
    avg = lambda s: (s + s.shift(1)) / 2

    ratios = pd.DataFrame({
        "Revenue growth": revenue.pct_change(),
        "Gross margin": gross / revenue,
        "EBITDA margin": ebitda / revenue,
        "EBIT margin": ebit / revenue,
        "Net margin": net_income / revenue,
        "ROE": net_income / avg(equity),
        "ROIC": nopat / avg(invested_capital),
        "Net debt / EBITDA": (total_debt - cash) / ebitda,
        "FCF conversion": fcf / net_income,
        "Capex / revenue": -capex / revenue,
    })
    ratios.index = ratios.index.year
    ratios.index.name = "Fiscal year"
    return ratios


def trend_flags(ratios: pd.DataFrame) -> list[str]:
    """Plain-English flags for patterns worth investigating."""
    flags = []
    r = ratios.dropna(how="all")

    for col in ["Gross margin", "EBIT margin", "Net margin"]:
        s = r[col].dropna()
        if len(s) >= 3 and (s.diff().iloc[-2:] < 0).all():
            flags.append(f"{col} has fallen for the last 2 years "
                         f"({s.iloc[-3]:.1%} -> {s.iloc[-1]:.1%}).")

    g = r["Revenue growth"].dropna()
    if len(g) and g.iloc[-1] < 0:
        flags.append(f"Revenue shrank {abs(g.iloc[-1]):.1%} in the latest year.")

    nd = r["Net debt / EBITDA"].dropna()
    if len(nd) and nd.iloc[-1] > 3:
        flags.append(f"Leverage is high: net debt is {nd.iloc[-1]:.1f}x EBITDA.")

    fc = r["FCF conversion"].dropna()
    if len(fc) and fc.iloc[-1] < 0.7:
        flags.append(f"Weak cash conversion: FCF was {fc.iloc[-1]:.0%} of net income "
                     "in the latest year - check working capital and capex.")
    return flags
