"""
Comparable company analysis.

Values a company by applying its peers' valuation multiples to its own
figures. If similar businesses trade at 12x EBITDA, a company with EUR 1bn of
EBITDA is worth roughly EUR 12bn as a whole business (enterprise value).

Methodology notes:
- Multiples are trailing: market value today divided by the latest reported
  full year. Banks usually use forward multiples (next year's consensus
  forecasts), which aren't available from free data.
- Enterprise value = market cap + total debt - cash, matching the DCF's net
  debt definition (leases included).
- The peer median is used rather than the mean, so one unusual peer can't
  drag the result.
- Multiples over a zero or negative denominator (a loss-making year) are left
  blank, as are companies whose share price and accounts are in different
  currencies, since the ratio would be meaningless without conversion.
- Peers use reported figures, so their multiples can be distorted by one-off
  items the same way Rolls-Royce's reported profit was.
- Peers can be given adjusted figures (from their own results) in
  config.PEER_ADJUSTMENTS, and the code flags figures that look inconsistent,
  such as EBIT above EBITDA, which usually means one-off gains.
- For the target company, any underlying figures set in the DCF overrides
  (revenue, margin, tax rate, cash) are used, so both methods start from the
  same base year.
"""

import numpy as np
import pandas as pd

from .data import get

MULTIPLES = ["EV / Sales", "EV / EBITDA", "EV / EBIT", "P / E"]
METRIC_FOR = {"EV / Sales": "Sales", "EV / EBITDA": "EBITDA",
              "EV / EBIT": "EBIT", "P / E": "Earnings"}


def _latest(s: pd.Series) -> float:
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def _same_currency(info: dict) -> bool:
    """Price currency and reporting currency must match ('GBp' counts as GBP)."""
    trade = (info.get("currency") or "").upper()
    report = (info.get("financialCurrency") or "").upper()
    return bool(trade) and trade == report


def company_metrics(co: dict, overrides: dict | None = None,
                    adjustments: dict | None = None) -> dict:
    """Latest-year sales, EBITDA, EBIT and earnings, plus market cap and net
    debt. Overrides from the DCF config replace reported figures, and
    `adjustments` (keys Sales / EBITDA / EBIT / Earnings) replace them
    directly, e.g. a peer's adjusted operating profit from its results."""
    overrides = overrides or {}
    inc, bal, cf, info = co["income"], co["balance"], co["cashflow"], co["info"]

    revenue = get(inc, "Total Revenue", "Operating Revenue").dropna()
    inc, bal, cf = (df.reindex(revenue.index) for df in (inc, bal, cf))

    sales = _latest(revenue)
    ebit = _latest(get(inc, "EBIT", "Operating Income"))
    da = _latest(get(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion"))
    ebitda = _latest(get(inc, "Normalized EBITDA", "EBITDA"))
    earnings = _latest(get(inc, "Net Income Common Stockholders", "Net Income"))
    debt = _latest(get(bal, "Total Debt"))
    cash = _latest(get(bal, "Cash And Cash Equivalents",
                       "Cash Cash Equivalents And Short Term Investments"))

    # Use the same underlying base year as the DCF where it was overridden
    if "base_revenue" in overrides:
        sales = overrides["base_revenue"]
    if "base_ebit_margin" in overrides:
        ebit = sales * overrides["base_ebit_margin"]
        ebitda = ebit + da
        # Net interest: expense minus any interest income
        expense = abs(_latest(get(inc, "Interest Expense", "Interest Expense Non Operating")))
        income = abs(_latest(get(inc, "Interest Income", "Interest Income Non Operating")))
        interest = (0 if np.isnan(expense) else expense) - (0 if np.isnan(income) else income)
        tax = overrides.get("tax_rate", 0.25)
        earnings = (ebit - interest) * (1 - tax)
    cash = overrides.get("cash", cash)

    adjusted = sorted((adjustments or {}).keys())
    figures = {"Sales": sales, "EBITDA": ebitda, "EBIT": ebit, "Earnings": earnings}
    figures.update(adjustments or {})

    return {
        "Name": info.get("longName") or "",
        "Currency": info.get("financialCurrency") or "",
        "Market cap": info.get("marketCap"),
        "Net debt": debt - cash,
        **figures,
        "Adjusted": adjusted,
        "Shares": info.get("sharesOutstanding"),
        "Comparable": _same_currency(info),
    }


def figures_table(target: str, target_metrics: dict, peers: dict) -> pd.DataFrame:
    """The underlying figures behind each multiple, in millions of each
    company's own reporting currency, so odd results can be traced."""
    rows = {}
    for t, m in {target: target_metrics, **peers}.items():
        rows[t] = {"Currency": m["Currency"],
                   **{k: (m[k] or np.nan) / 1e6 for k in
                      ["Market cap", "Net debt", "Sales", "EBITDA", "EBIT", "Earnings"]}}
    return pd.DataFrame(rows).T


def warnings(m: dict) -> list[str]:
    """Signs that reported figures include one-off items."""
    out = []
    if m["EBIT"] > m["EBITDA"] > 0:
        out.append("EBIT is above EBITDA, which is impossible on a consistent basis; "
                   "reported EBIT probably includes one-off gains")
    if m["Earnings"] > m["EBIT"] > 0:
        out.append("net income is above operating profit, suggesting large "
                   "non-operating gains")
    return out


def multiples(m: dict) -> dict:
    """Valuation multiples for one company; blank where meaningless."""
    out = {k: np.nan for k in MULTIPLES}
    if not m["Comparable"] or not m["Market cap"]:
        return out
    ev = m["Market cap"] + m["Net debt"]
    for k in MULTIPLES:
        denom = m[METRIC_FOR[k]]
        if denom and denom > 0:
            out[k] = (m["Market cap"] if k == "P / E" else ev) / denom
    return out


def peer_table(target: str, target_metrics: dict, peers: dict) -> pd.DataFrame:
    """One row per company (target first), with the peer median at the bottom.
    `peers` maps ticker -> metrics dict."""
    rows = {target: multiples(target_metrics)}
    for t, m in peers.items():
        rows[t] = multiples(m)
    table = pd.DataFrame(rows).T[MULTIPLES]
    table.loc["Peer median"] = table.drop(index=target).median()
    names = {target: target_metrics["Name"], **{t: m["Name"] for t, m in peers.items()}}
    table.insert(0, "Company", [names.get(t, "") for t in table.index])
    return table


def implied_value(target_metrics: dict, medians: pd.Series, price: float) -> pd.DataFrame:
    """Apply each peer median multiple to the target's own figures."""
    rows = []
    for k in MULTIPLES:
        mult, metric = medians.get(k), target_metrics[METRIC_FOR[k]]
        if pd.isna(mult) or not metric or metric <= 0:
            continue
        if k == "P / E":
            equity = mult * metric
            ev = equity + target_metrics["Net debt"]
        else:
            ev = mult * metric
            equity = ev - target_metrics["Net debt"]
        per_share = equity / target_metrics["Shares"]
        rows.append({"Multiple": k, "Peer median": mult, "Applied to": metric,
                     "Implied EV": ev, "Implied equity": equity,
                     "Value per share": per_share, "Upside": per_share / price - 1})
    return pd.DataFrame(rows).set_index("Multiple")
