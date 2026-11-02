"""
Discounted cash flow valuation.

Forecasts unlevered free cash flow for a set number of years, discounts it at
the weighted average cost of capital (WACC), adds a Gordon-growth terminal
value, and bridges from enterprise value to a value per share.

Every input has a default taken from the company's own history, and any of
them can be overridden in config.py. The output records where each input came
from, so it's always clear which numbers are assumptions and which are data.

Methodology notes:
- Free cash flow = NOPAT + D&A - capex - increase in operating working capital.
- Operating working capital excludes cash and short-term debt, since those are
  financing items handled in the net debt bridge.
- Under IFRS 16, lease costs sit below EBIT (as depreciation and interest),
  so lease liabilities are treated as debt. Yahoo's "Total Debt" includes them.
- Cash flows are discounted from the end of each year (no mid-year adjustment).
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .data import get


@dataclass
class DCFInputs:
    base_revenue: float
    revenue_growth: list      # one rate per forecast year
    base_ebit_margin: float
    target_ebit_margin: float  # reached in the final forecast year
    tax_rate: float
    da_pct: float             # D&A as % of revenue
    capex_pct: float          # capex as % of revenue
    nwc_pct: float            # operating working capital as % of revenue
    terminal_growth: float
    risk_free: float
    erp: float
    beta: float
    cost_of_debt: float       # pre-tax
    debt: float
    cash: float
    shares: float
    market_cap: float
    price: float
    wacc_override: float | None = None


def _recent_mean(s: pd.Series, n: int = 3) -> float:
    s = s.dropna()
    return float(s.iloc[-n:].mean()) if len(s) else float("nan")


def _price_in_reporting_units(info: dict) -> float:
    """London prices on Yahoo are quoted in pence ('GBp'), but accounts are
    in pounds. Convert so price and per-share value are comparable."""
    price = info.get("currentPrice")
    if price is not None and info.get("currency") == "GBp":
        price = price / 100
    return price


def build_inputs(co: dict, overrides: dict, market: dict,
                 years: int = 5) -> tuple[DCFInputs, dict]:
    """Default every input from history, then apply overrides.
    Returns the inputs and a {name: source} record."""
    inc, bal, cf, info = co["income"], co["balance"], co["cashflow"], co["info"]

    revenue = get(inc, "Total Revenue", "Operating Revenue").dropna()
    inc, bal, cf = (df.reindex(revenue.index) for df in (inc, bal, cf))

    ebit = get(inc, "EBIT", "Operating Income")
    pretax, tax = get(inc, "Pretax Income"), get(inc, "Tax Provision")
    da = get(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
    capex = -get(cf, "Capital Expenditure")
    interest = get(inc, "Interest Expense", "Interest Expense Non Operating").abs()
    debt = get(bal, "Total Debt")
    cash = get(bal, "Cash And Cash Equivalents",
               "Cash Cash Equivalents And Short Term Investments")
    op_wc = ((get(bal, "Current Assets") - cash)
             - (get(bal, "Current Liabilities") - get(bal, "Current Debt").fillna(0)))

    growth_hist = revenue.pct_change(fill_method=None)
    eff_tax = (tax / pretax).where((pretax > 0) & (tax / pretax).between(0, 0.5))
    avg_debt = (debt + debt.shift(1)) / 2

    currency = info.get("financialCurrency")
    rf = market["risk_free"].get(currency)
    terminal_g = overrides.get("terminal_growth", 0.02)

    # Growth fades in a straight line from recent growth to terminal growth
    g_start = _recent_mean(growth_hist)
    growth_path = list(np.linspace(g_start, terminal_g, years + 1)[:years])

    kd_hist = _recent_mean(interest / avg_debt)
    kd_default = kd_hist if (rf is not None and rf <= kd_hist <= rf + 0.06) \
        else (rf + 0.02 if rf is not None else float("nan"))

    defaults = {
        "base_revenue": (float(revenue.iloc[-1]), "latest reported"),
        "revenue_growth": (growth_path, "3-yr avg growth fading to terminal"),
        "base_ebit_margin": (float((ebit / revenue).iloc[-1]), "latest reported"),
        "tax_rate": (_recent_mean(eff_tax) if eff_tax.notna().any() else 0.25,
                     "3-yr effective rate"),
        "da_pct": (_recent_mean(da / revenue), "3-yr average"),
        "capex_pct": (_recent_mean(capex / revenue), "3-yr average"),
        "nwc_pct": (float((op_wc / revenue).dropna().iloc[-1])
                    if (op_wc / revenue).notna().any() else 0.0, "latest reported"),
        "terminal_growth": (terminal_g, "default 2%"),
        "risk_free": (rf, f"config ({currency})"),
        "erp": (market["equity_risk_premium"], "config"),
        "beta": (info.get("beta"), "data feed"),
        "cost_of_debt": (kd_default, "interest / avg debt" if kd_default == kd_hist
                         else "risk-free + 2%"),
        "debt": (float(debt.iloc[-1]), "latest reported"),
        "cash": (float(cash.iloc[-1]), "latest reported"),
        "shares": (info.get("sharesOutstanding"), "data feed"),
        "market_cap": (info.get("marketCap"), "data feed"),
        "price": (_price_in_reporting_units(info), "data feed"),
    }
    defaults["target_ebit_margin"] = (defaults["base_ebit_margin"][0], "held flat")

    values, sources = {}, {}
    for name, (value, source) in defaults.items():
        if name in overrides:
            value, source = overrides[name], "override"
            if name == "revenue_growth" and not isinstance(value, list):
                value = [value] * years
        values[name], sources[name] = value, source

    missing = [k for k in ("risk_free", "erp", "beta", "shares", "price")
               if values[k] is None]
    if missing:
        raise ValueError("Missing inputs: " + ", ".join(missing)
                         + " - set them in config.py")
    return DCFInputs(**values), sources


def wacc(x: DCFInputs) -> dict:
    cost_of_equity = x.risk_free + x.beta * x.erp
    after_tax_kd = x.cost_of_debt * (1 - x.tax_rate)
    e, d = x.market_cap, x.debt
    w = e / (e + d) * cost_of_equity + d / (e + d) * after_tax_kd
    return {"Cost of equity": cost_of_equity, "After-tax cost of debt": after_tax_kd,
            "Equity weight": e / (e + d), "Debt weight": d / (e + d),
            "WACC": x.wacc_override if x.wacc_override is not None else w}


def value(x: DCFInputs) -> dict:
    """Run the DCF and return the forecast table and valuation bridge."""
    r = wacc(x)["WACC"]
    if x.terminal_growth >= r:
        raise ValueError("Terminal growth must be below WACC")

    n = len(x.revenue_growth)
    rows, prev_rev = [], x.base_revenue
    for t, g in enumerate(x.revenue_growth, start=1):
        rev = prev_rev * (1 + g)
        margin = x.base_ebit_margin + (x.target_ebit_margin - x.base_ebit_margin) * t / n
        ebit = rev * margin
        nopat = ebit * (1 - x.tax_rate)
        da, capex = rev * x.da_pct, rev * x.capex_pct
        d_nwc = x.nwc_pct * (rev - prev_rev)
        fcf = nopat + da - capex - d_nwc
        disc = 1 / (1 + r) ** t
        rows.append({"Revenue": rev, "Growth": g, "EBIT margin": margin, "EBIT": ebit,
                     "NOPAT": nopat, "D&A": da, "Capex": capex, "Change in NWC": d_nwc,
                     "Free cash flow": fcf, "Discount factor": disc, "PV of FCF": fcf * disc})
        prev_rev = rev

    forecast = pd.DataFrame(rows, index=[f"Y{t}" for t in range(1, n + 1)])
    terminal = forecast["Free cash flow"].iloc[-1] * (1 + x.terminal_growth) / (r - x.terminal_growth)
    pv_terminal = terminal * forecast["Discount factor"].iloc[-1]
    ev = forecast["PV of FCF"].sum() + pv_terminal
    equity = ev - (x.debt - x.cash)
    per_share = equity / x.shares

    return {
        "forecast": forecast,
        "WACC": r,
        "PV of forecast FCF": forecast["PV of FCF"].sum(),
        "PV of terminal value": pv_terminal,
        "Enterprise value": ev,
        "Net debt": x.debt - x.cash,
        "Equity value": equity,
        "Value per share": per_share,
        "Current price": x.price,
        "Upside": per_share / x.price - 1,
        "Terminal value share of EV": pv_terminal / ev,
    }


def _apply(x: DCFInputs, name: str, v: float) -> DCFInputs:
    """Return a copy of the inputs with one assumption changed. 'wacc' and
    'growth_shift' (added to every forecast year's growth) are special cases;
    any other name must be a DCFInputs field."""
    if name == "wacc":
        return replace(x, wacc_override=v)
    if name == "growth_shift":
        return replace(x, revenue_growth=[g + v for g in x.revenue_growth])
    return replace(x, **{name: v})


def sensitivity(x: DCFInputs, row: str, row_values, col: str, col_values) -> pd.DataFrame:
    """Value per share across two inputs."""
    out = pd.DataFrame(index=row_values, columns=col_values, dtype=float)
    for rv in row_values:
        for cv in col_values:
            y = _apply(_apply(x, row, rv), col, cv)
            try:
                out.loc[rv, cv] = value(y)["Value per share"]
            except ValueError:
                out.loc[rv, cv] = np.nan
    out.index.name, out.columns.name = row, col
    return out


def implied(x: DCFInputs, name: str, low: float, high: float) -> float | None:
    """Reverse DCF: the value of one assumption that makes the DCF value equal
    the current share price, holding everything else fixed. Uses bisection,
    which works because value per share moves in one direction as each of
    these assumptions changes. Returns None if no value in [low, high] works."""
    def gap(v):
        return value(_apply(x, name, v))["Value per share"] - x.price

    try:
        g_low, g_high = gap(low), gap(high)
    except ValueError:
        return None
    if g_low * g_high > 0:
        return None
    for _ in range(60):
        mid = (low + high) / 2
        g_mid = gap(mid)
        if g_low * g_mid <= 0:
            high = mid
        else:
            low, g_low = mid, g_mid
    return (low + high) / 2


def reverse_dcf(x: DCFInputs) -> pd.DataFrame:
    """For each key assumption, what it would need to be (with everything else
    unchanged) to justify today's share price."""
    r = wacc(x)["WACC"]
    levers = {
        "Target EBIT margin": ("target_ebit_margin", x.target_ebit_margin, 0.0, 0.9),
        "Revenue growth shift (every year)": ("growth_shift", 0.0, -0.3, 0.6),
        "Terminal growth": ("terminal_growth", x.terminal_growth, -0.05, r - 0.001),
        "WACC": ("wacc", r, x.terminal_growth + 0.001, 0.4),
    }
    rows = []
    for label, (name, current, low, high) in levers.items():
        needed = implied(x, name, low, high)
        rows.append({"Assumption": label, "Current": current, "Needed to justify price": needed})
    return pd.DataFrame(rows).set_index("Assumption")
