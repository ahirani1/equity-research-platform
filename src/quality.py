"""
Credit strength and accounting quality.

Credit: can the company comfortably service and repay its debt?
- Interest cover = EBIT / interest expense. Below about 3x starts to look
  stretched; lenders often set covenants around 2-4x.
- Net debt / EBITDA: years of operating profit needed to repay net debt.
- Altman Z-score: a weighted combination of five ratios that historically
  separated companies that went bankrupt from those that didn't. Designed on
  US manufacturers, so it's a rough screen for other industries (retailers
  score high on the sales term, for example), not a verdict.

Accounting quality: how far reported profit is backed by cash.
- Cash conversion = operating cash flow / net income.
- Accruals ratio (Sloan) = (net income - operating cash flow) / average total
  assets. Profit that consistently runs ahead of cash is a warning sign,
  because accruals depend on estimates and reverse later.
- A reconciliation of every figure I've changed from the data feed, so the
  adjustments are visible rather than buried in the model.
"""

import numpy as np
import pandas as pd

from .data import get
from .dcf import build_inputs

Z_ZONES = [(2.99, "Safe"), (1.81, "Grey zone"), (-np.inf, "Distress zone")]


def _years(co: dict) -> tuple:
    """Statements restricted to years with reported revenue."""
    revenue = get(co["income"], "Total Revenue", "Operating Revenue").dropna()
    return revenue.index, (co[k].reindex(revenue.index)
                           for k in ("income", "balance", "cashflow"))


def credit_metrics(co: dict) -> pd.DataFrame:
    idx, (inc, bal, cf) = _years(co)
    ebit = get(inc, "EBIT", "Operating Income")
    ebitda = get(inc, "Normalized EBITDA", "EBITDA")
    interest = get(inc, "Interest Expense", "Interest Expense Non Operating").abs()
    debt = get(bal, "Total Debt")
    cash = get(bal, "Cash And Cash Equivalents",
               "Cash Cash Equivalents And Short Term Investments")
    equity = get(bal, "Stockholders Equity", "Common Stock Equity")
    out = pd.DataFrame({
        "Interest cover": (ebit / interest).where(interest > 0),
        "Net debt / EBITDA": ((debt - cash) / ebitda).where(ebitda > 0),
        "Debt / equity": (debt / equity).where(equity > 0),
    })
    out.index = out.index.year
    out.index.name = "Fiscal year"
    return out


def altman_z(co: dict, overrides: dict | None = None) -> dict | None:
    """Latest-year Altman Z-score and its components. If the DCF overrides set
    an underlying base year (revenue and EBIT margin), those figures are used,
    so one-off gains don't flatter the score."""
    idx, (inc, bal, cf) = _years(co)
    latest = lambda s: float(s.dropna().iloc[-1]) if s.notna().any() else np.nan

    total_assets = latest(get(bal, "Total Assets"))
    total_liab = latest(get(bal, "Total Liabilities Net Minority Interest",
                            "Total Liabilities"))
    working_capital = latest(get(bal, "Working Capital"))
    if np.isnan(working_capital):
        working_capital = latest(get(bal, "Current Assets") - get(bal, "Current Liabilities"))
    retained = latest(get(bal, "Retained Earnings"))
    ebit = latest(get(inc, "EBIT", "Operating Income"))
    sales = latest(get(inc, "Total Revenue", "Operating Revenue"))
    market_cap = co["info"].get("marketCap") or np.nan
    overrides = overrides or {}
    basis = "reported"
    if "base_revenue" in overrides:
        sales = overrides["base_revenue"]
        basis = "underlying"
    if "base_ebit_margin" in overrides:
        ebit = sales * overrides["base_ebit_margin"]
        basis = "underlying"

    if not total_assets or np.isnan(total_assets) or not total_liab or np.isnan(total_liab):
        return None
    parts = {
        "Working capital / assets (x1.2)": 1.2 * working_capital / total_assets,
        "Retained earnings / assets (x1.4)": 1.4 * retained / total_assets,
        "EBIT / assets (x3.3)": 3.3 * ebit / total_assets,
        "Market value of equity / liabilities (x0.6)": 0.6 * market_cap / total_liab,
        "Sales / assets (x1.0)": 1.0 * sales / total_assets,
    }
    if any(np.isnan(v) for v in parts.values()):
        return None
    z = sum(parts.values())
    zone = next(label for cut, label in Z_ZONES if z > cut)
    return {"Z-score": z, "Zone": zone, "Components": parts, "Basis": basis}


def accounting_quality(co: dict) -> pd.DataFrame:
    idx, (inc, bal, cf) = _years(co)
    net_income = get(inc, "Net Income", "Net Income Common Stockholders")
    ocf = get(cf, "Operating Cash Flow")
    assets = get(bal, "Total Assets")
    avg_assets = (assets + assets.shift(1)) / 2
    out = pd.DataFrame({
        "Cash conversion (OCF / net income)": (ocf / net_income).where(net_income > 0),
        "Accruals ratio": ((net_income - ocf) / avg_assets).where(avg_assets > 0),
    })
    out.index = out.index.year
    out.index.name = "Fiscal year"
    return out


def adjustments_table(co: dict, overrides: dict, peer_adjustments: dict | None,
                      market: dict) -> pd.DataFrame:
    """Every base-year figure I've overridden: data feed vs figure used, and
    the reason recorded in config.py comments lives alongside in the notes."""
    rows = []
    try:
        feed, _ = build_inputs(co, {}, market)
        used, sources = build_inputs(co, overrides, market)
    except ValueError:
        return pd.DataFrame()
    labels = {
        "base_revenue": "Base-year revenue", "base_ebit_margin": "Base-year EBIT margin",
        "target_ebit_margin": "Final-year EBIT margin", "tax_rate": "Tax rate",
        "capex_pct": "Capex (% of revenue)", "target_capex_pct": "Final-year capex",
        "cash": "Cash", "revenue_growth": "Revenue growth",
        "terminal_growth": "Terminal growth", "beta": "Beta",
        "cost_of_debt": "Cost of debt", "nwc_pct": "Working capital (% of revenue)",
        "da_pct": "D&A (% of revenue)",
    }
    for name in overrides:
        if name not in labels:
            continue
        rows.append({"Item": labels[name], "Data feed": getattr(feed, name),
                     "Used": getattr(used, name), "Type": name})
    for metric, value in (peer_adjustments or {}).items():
        rows.append({"Item": f"{metric} (comps)", "Data feed": None, "Used": value,
                     "Type": "money"})
    return pd.DataFrame(rows)
