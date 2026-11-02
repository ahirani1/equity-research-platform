"""
Leveraged buyout (LBO) analysis.

A private equity fund buys the whole company, funding most of the price with
debt, uses the company's cash flow to pay the debt down, and sells after a few
years. Its return comes from what's left for the shareholders at exit.

Two questions:
1. Returns: at a given takeover premium, what IRR and money multiple (MOIC)
   does the fund make, and where does the return come from?
2. Price floor: what is the highest price per share a fund could pay and
   still hit its target IRR? Banks show this alongside the DCF and comps.

Methodology notes:
- The operating forecast (revenue, margins, D&A, capex, working capital, tax)
  is the same one used in the DCF, so the two methods start from the same view.
- EBITDA is on the IFRS 16 basis (rent excluded), and existing net debt
  including leases is assumed to be refinanced at entry, consistent with
  treating leases as debt elsewhere in the project. A simplification: in a
  real deal, leases would stay in place rather than be refinanced.
- Two debt tranches: senior debt, repaid early from all spare cash (a "cash
  sweep"), and high-yield bonds, repaid in full at exit.
- Interest is charged on each year's opening balance, which avoids a
  circular calculation (interest depends on repayments, which depend on
  interest).
- No dividends are paid during the hold, so the fund's only cash flows are
  the equity it puts in at entry and the equity it receives at exit.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .dcf import DCFInputs, value


@dataclass
class LBOInputs:
    premium: float          # takeover premium over the current share price
    senior_multiple: float  # senior debt raised, as a multiple of entry EBITDA
    senior_rate: float      # interest rate on senior debt
    hy_multiple: float      # high-yield bonds raised, multiple of entry EBITDA
    hy_rate: float          # interest rate on high-yield bonds
    fees_pct: float         # deal and financing fees, % of enterprise value
    exit_multiple: float | None = None  # EV / EBITDA at exit; None = entry multiple
    target_irr: float = 0.20


def _entry_ebitda(x: DCFInputs) -> float:
    return x.base_revenue * (x.base_ebit_margin + x.da_pct)


def run(dcf: DCFInputs, lbo: LBOInputs) -> dict:
    """Run the buyout and return sources and uses, the yearly debt schedule,
    the returns and their attribution."""
    forecast = value(dcf)["forecast"]
    ebitda0 = _entry_ebitda(dcf)

    # ---- entry: what the fund pays and how it's funded
    offer_price = dcf.price * (1 + lbo.premium)
    equity_purchase = offer_price * dcf.shares
    existing_net_debt = dcf.debt - dcf.cash
    entry_ev = equity_purchase + existing_net_debt
    fees = lbo.fees_pct * entry_ev
    senior0 = lbo.senior_multiple * ebitda0
    hy0 = lbo.hy_multiple * ebitda0
    sponsor_equity = entry_ev + fees - senior0 - hy0
    entry_multiple = entry_ev / ebitda0

    sources = pd.Series({"Senior debt": senior0, "High-yield bonds": hy0,
                         "Sponsor equity": sponsor_equity})
    uses = pd.Series({"Purchase of shares": equity_purchase,
                      "Refinance existing net debt": existing_net_debt,
                      "Fees": fees})

    # ---- hold: pay debt down from cash flow
    senior, hy, cash = senior0, hy0, 0.0
    rows = []
    for year, f in forecast.iterrows():
        ebitda = f["EBIT"] + f["D&A"]
        interest = senior * lbo.senior_rate + hy * lbo.hy_rate
        taxable = f["EBIT"] - interest
        tax = max(taxable, 0) * dcf.tax_rate
        free_cash = ebitda - interest - tax - f["Capex"] - f["Change in NWC"]
        repay = min(max(free_cash, 0), senior)
        senior -= repay
        cash += free_cash - repay
        rows.append({"EBITDA": ebitda, "Interest": interest, "Tax": tax,
                     "Capex": f["Capex"], "Change in NWC": f["Change in NWC"],
                     "Cash for debt repayment": free_cash,
                     "Senior repaid": repay, "Senior debt (end)": senior,
                     "High-yield bonds (end)": hy, "Cash (end)": cash,
                     "Net debt / EBITDA": (senior + hy - cash) / ebitda,
                     "Interest cover (EBITDA / interest)": ebitda / interest if interest else np.nan})
    schedule = pd.DataFrame(rows, index=forecast.index)

    # ---- exit
    years = len(schedule)
    ebitda_exit = schedule["EBITDA"].iloc[-1]
    exit_multiple = lbo.exit_multiple if lbo.exit_multiple is not None else entry_multiple
    exit_ev = exit_multiple * ebitda_exit
    exit_net_debt = senior + hy - cash
    exit_equity = exit_ev - exit_net_debt
    moic = exit_equity / sponsor_equity if sponsor_equity > 0 else np.nan
    irr = moic ** (1 / years) - 1 if moic and moic > 0 else np.nan

    # ---- where the gain came from (sums exactly to the equity gain)
    entry_net_debt = senior0 + hy0
    attribution = pd.Series({
        "EBITDA growth": entry_multiple * (ebitda_exit - ebitda0),
        "Change in multiple": (exit_multiple - entry_multiple) * ebitda_exit,
        "Debt paydown and cash build": entry_net_debt - exit_net_debt,
        "Fees": -fees,
    })

    return {
        "sources": sources, "uses": uses, "schedule": schedule,
        "entry_ebitda": ebitda0, "entry_ev": entry_ev, "entry_multiple": entry_multiple,
        "offer_price": offer_price, "sponsor_equity": sponsor_equity,
        "total_debt_multiple": lbo.senior_multiple + lbo.hy_multiple,
        "equity_share": sponsor_equity / (entry_ev + fees),
        "exit_ev": exit_ev, "exit_multiple": exit_multiple, "exit_equity": exit_equity,
        "moic": moic, "irr": irr, "years": years, "attribution": attribution,
    }


def max_price(dcf: DCFInputs, lbo: LBOInputs) -> float | None:
    """Highest price per share that still gives the target IRR, by bisection
    on the premium. Unless an exit multiple is set, the fund is assumed to
    sell at the same EV / EBITDA multiple it paid, so a cheaper purchase isn't
    flattered by assuming a more expensive sale. The debt raised depends on
    EBITDA, not the price, so paying more means more equity and a lower IRR."""
    def gap(premium):
        r = run(dcf, replace(lbo, premium=premium))["irr"]
        return (r if not np.isnan(r) else 10.0) - lbo.target_irr

    lo, hi = -0.95, 2.0
    if gap(lo) < 0 or gap(hi) > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        if gap(mid) > 0:
            lo = mid
        else:
            hi = mid
    return dcf.price * (1 + (lo + hi) / 2)


def irr_grid(dcf: DCFInputs, lbo: LBOInputs, premiums, exit_multiples) -> pd.DataFrame:
    out = pd.DataFrame(index=premiums, columns=exit_multiples, dtype=float)
    for p in premiums:
        for m in exit_multiples:
            out.loc[p, m] = run(dcf, replace(lbo, premium=p, exit_multiple=m))["irr"]
    out.index.name, out.columns.name = "Premium", "Exit EV / EBITDA"
    return out


def from_config(cfg: dict) -> LBOInputs:
    keys = LBOInputs.__dataclass_fields__
    return LBOInputs(**{k: v for k, v in cfg.items() if k in keys})
