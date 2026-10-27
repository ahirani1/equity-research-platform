"""
Ratio analysis: turns the three statements into the metrics an analyst looks at
first - growth, profitability, returns, leverage and cash quality - plus simple
trend flags.

Design choices worth being able to explain:
- Ratios over a zero or negative base (e.g. ROE when equity is negative) are
  left blank rather than shown, because the number has no meaning.
- Invested capital is defined as equity + total debt - cash, so the definition
  is transparent and the same for every company.
- Reported EBITDA is shown next to Yahoo's "normalised" EBITDA, which strips
  out one-off items. A big gap between them means reported profit is distorted.
"""

import pandas as pd

from .data import get


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """num / den, but blank wherever the denominator is zero or negative."""
    return (num / den).where(den > 0)


def _avg(s: pd.Series) -> pd.Series:
    """Average of opening and closing balance, for ratios that compare a full
    year's profit with a balance-sheet figure. Blank if either balance is zero
    or negative: an average that straddles zero gives a meaningless return
    (e.g. equity going from -1.0 to +1.8 averages 0.4, so ROE looks like 1000%+)."""
    prev = s.shift(1)
    return ((s + prev) / 2).where((s > 0) & (prev > 0))


def compute_ratios(co: dict, tax_rate_fallback: float = 0.25) -> pd.DataFrame:
    inc, bal, cf = co["income"], co["balance"], co["cashflow"]

    # Only keep years where revenue was reported. Yahoo often returns a partial
    # oldest year with most line items missing.
    revenue = get(inc, "Total Revenue", "Operating Revenue")
    years = revenue.dropna().index
    inc, bal, cf = (df.reindex(years) for df in (inc, bal, cf))
    revenue = revenue.reindex(years)

    gross = get(inc, "Gross Profit")
    ebitda = get(inc, "EBITDA")
    ebitda_norm = get(inc, "Normalized EBITDA")
    ebit = get(inc, "EBIT", "Operating Income")
    net_income = get(inc, "Net Income", "Net Income Common Stockholders")
    pretax = get(inc, "Pretax Income")
    tax = get(inc, "Tax Provision")

    equity = get(bal, "Stockholders Equity", "Common Stock Equity")
    total_debt = get(bal, "Total Debt")
    cash = get(bal, "Cash And Cash Equivalents",
               "Cash Cash Equivalents And Short Term Investments")
    invested_capital = equity + total_debt - cash

    ocf = get(cf, "Operating Cash Flow")
    capex = get(cf, "Capital Expenditure")  # reported as a negative number
    fcf = ocf + capex

    # Effective tax rate, falling back when it's distorted (losses, one-offs)
    eff_tax = tax / pretax
    tax_rate = eff_tax.where((pretax > 0) & eff_tax.between(0, 0.5),
                             tax_rate_fallback)
    nopat = ebit * (1 - tax_rate)

    ratios = pd.DataFrame({
        "Revenue growth": revenue.pct_change(fill_method=None),
        "Gross margin": _safe_div(gross, revenue),
        "EBITDA margin": _safe_div(ebitda, revenue),
        "EBITDA margin (normalised)": _safe_div(ebitda_norm, revenue),
        "EBIT margin": _safe_div(ebit, revenue),
        "Net margin": _safe_div(net_income, revenue),
        "ROE": _safe_div(net_income, _avg(equity)),
        "ROIC": _safe_div(nopat, _avg(invested_capital)),
        "Net debt / EBITDA": _safe_div(total_debt - cash, ebitda_norm.fillna(ebitda)),
        "FCF conversion": _safe_div(fcf, net_income),
        "Capex / revenue": _safe_div(-capex, revenue),
    })
    ratios.index = ratios.index.year
    ratios.index.name = "Fiscal year"

    # Keep the raw inputs the flags need
    ratios.attrs["equity"] = equity.set_axis(ratios.index)
    ratios.attrs["ebitda"] = ebitda.set_axis(ratios.index)
    ratios.attrs["ebitda_norm"] = ebitda_norm.set_axis(ratios.index)
    return ratios


def trend_flags(ratios: pd.DataFrame) -> list[str]:
    """Plain-English flags for patterns worth investigating."""
    flags = []
    r = ratios

    for col in ["Gross margin", "EBIT margin", "Net margin"]:
        s = r[col].dropna()
        if len(s) >= 3 and (s.diff().iloc[-2:] < 0).all():
            flags.append(f"{col} has fallen for the last 2 years "
                         f"({s.iloc[-3]:.1%} -> {s.iloc[-1]:.1%}).")

    g = r["Revenue growth"].dropna()
    if len(g) and g.iloc[-1] < 0:
        flags.append(f"Revenue shrank {abs(g.iloc[-1]):.1%} in the latest year.")

    eq = r.attrs.get("equity", pd.Series(dtype=float)).dropna()
    neg_years = [str(y) for y, v in eq.items() if v <= 0]
    if neg_years:
        flags.append("Shareholders' equity was negative in " + ", ".join(neg_years)
                     + " - ROE and ROIC are not meaningful around those years.")

    rep = r.attrs.get("ebitda", pd.Series(dtype=float))
    norm = r.attrs.get("ebitda_norm", pd.Series(dtype=float))
    both = pd.concat([rep, norm], axis=1).dropna()
    if len(both):
        y, (a, b) = both.index[-1], both.iloc[-1]
        if b > 0 and abs(a - b) / b > 0.2:
            flags.append(f"Reported EBITDA in {y} is {a / b - 1:+.0%} vs normalised - "
                         "large one-off items; use underlying figures from the "
                         "annual report.")

    nd = r["Net debt / EBITDA"].dropna()
    if len(nd) and nd.iloc[-1] > 3:
        flags.append(f"Leverage is high: net debt is {nd.iloc[-1]:.1f}x EBITDA.")

    fc = r["FCF conversion"].dropna()
    if len(fc) and fc.iloc[-1] < 0.7:
        flags.append(f"Weak cash conversion: FCF was {fc.iloc[-1]:.0%} of net income "
                     "in the latest year - check working capital and capex.")
    return flags
