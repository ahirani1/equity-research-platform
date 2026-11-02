"""
Ratio analysis and DCF valuation for each company.

    python main.py                  # every company in config.py
    python main.py RR.L TSCO.L      # specific tickers
    python main.py --only ratios    # just the ratio analysis (or: --only dcf)
    python main.py --refresh        # re-download instead of using cached data
"""

import argparse

import numpy as np
import pandas as pd

from config import COMPANIES, MARKET
from src.data import fetch_company
from src.dcf import build_inputs, sensitivity, value, wacc
from src.ratios import compute_ratios, trend_flags

MULTIPLES = {"Net debt / EBITDA"}  # shown as 1.5x; everything else as a %


def format_table(ratios: pd.DataFrame) -> pd.DataFrame:
    table = ratios.T.astype(object)
    for row in table.index:
        fmt = "{:.1f}x" if row in MULTIPLES else "{:.1%}"
        table.loc[row] = ["–" if pd.isna(x) else fmt.format(x) for x in table.loc[row]]
    return table


def show_ratios(co: dict) -> None:
    ratios = compute_ratios(co)
    print(format_table(ratios))
    for flag in trend_flags(ratios) or ["No warning flags."]:
        print(" -", flag)


def money(x: float) -> str:
    """Large amounts in millions with thousands separators."""
    return f"{x / 1e6:,.0f}m"


def show_dcf(co: dict, overrides: dict) -> None:
    try:
        x, sources = build_inputs(co, overrides, MARKET)
    except ValueError as e:
        print(f"\nDCF skipped: {e}")
        return

    print("\n--- DCF inputs ---")
    pct = {"revenue_growth", "base_ebit_margin", "target_ebit_margin", "tax_rate",
           "da_pct", "capex_pct", "nwc_pct", "terminal_growth", "risk_free", "erp",
           "cost_of_debt"}
    for name, source in sources.items():
        v = getattr(x, name)
        if name == "revenue_growth":
            shown = ", ".join(f"{g:.1%}" for g in v)
        elif name in pct:
            shown = f"{v:.1%}"
        elif name in {"beta", "price"}:
            shown = f"{v:.2f}"
        else:
            shown = money(v)
        print(f"  {name:<20} {shown:<40} ({source})")

    print("\n--- Cost of capital ---")
    for k, v in wacc(x).items():
        print(f"  {k:<24} {v:.1%}")

    result = value(x)
    f = result["forecast"].copy()
    for col in f.columns:
        if col in {"Growth", "EBIT margin"}:
            f[col] = f[col].map("{:.1%}".format)
        elif col == "Discount factor":
            f[col] = f[col].map("{:.3f}".format)
        else:
            f[col] = f[col].map(money)
    print("\n--- Forecast ---")
    print(f.T)

    print("\n--- Valuation ---")
    for k in ["PV of forecast FCF", "PV of terminal value", "Enterprise value",
              "Net debt", "Equity value"]:
        print(f"  {k:<28} {money(result[k]):>12}")
    print(f"  {'Value per share':<28} {result['Value per share']:>12.2f}")
    print(f"  {'Current price':<28} {result['Current price']:>12.2f}")
    print(f"  {'Implied upside':<28} {result['Upside']:>12.1%}")
    tv_share = result["Terminal value share of EV"]
    print(f"  {'Terminal value % of EV':<28} {tv_share:>12.0%}")
    if tv_share > 0.75:
        print("  Note: most of the value sits in the terminal value, so the result "
              "is very sensitive to WACC and terminal growth.")
    if x.capex_pct < x.da_pct:
        print("  Note: capex is below D&A, so the asset base shrinks in the terminal "
              "year while revenue keeps growing. Consider setting capex_pct >= da_pct.")

    w = result["WACC"]
    t = x.terminal_growth
    table = sensitivity(x, "wacc", np.round(np.arange(w - 0.01, w + 0.0101, 0.005), 4),
                        "terminal_growth", np.round(np.arange(t - 0.01, t + 0.0101, 0.005), 4))
    print("\n--- Value per share: WACC (rows) vs terminal growth (columns) ---")
    print(_fmt_grid(table))

    m = x.target_ebit_margin
    table = sensitivity(x, "growth_shift", [-0.02, -0.01, 0.0, 0.01, 0.02],
                        "target_ebit_margin", np.round(np.arange(m - 0.02, m + 0.0201, 0.01), 4))
    print("\n--- Value per share: revenue growth shift (rows) vs target EBIT margin (columns) ---")
    print(_fmt_grid(table, row_signed=True))


def _fmt_grid(t: pd.DataFrame, row_signed: bool = False) -> pd.DataFrame:
    out = t.map(lambda v: "–" if pd.isna(v) else f"{v:.2f}")
    out.index = [f"{i:+.1%}" if row_signed else f"{i:.1%}" for i in t.index]
    out.columns = [f"{c:.1%}" for c in t.columns]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Equity research tool")
    parser.add_argument("tickers", nargs="*", help="Yahoo Finance tickers")
    parser.add_argument("--only", choices=["ratios", "dcf"], help="run one section")
    parser.add_argument("--refresh", action="store_true", help="re-download data")
    args = parser.parse_args()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)

    for ticker in args.tickers or COMPANIES:
        co = fetch_company(ticker, refresh=args.refresh)
        name = co["info"].get("longName") or ticker
        currency = co["info"].get("financialCurrency")
        print(f"\n=== {name} ({ticker}) | reporting currency: {currency} ===")

        if args.only != "dcf":
            show_ratios(co)
        if args.only != "ratios":
            show_dcf(co, COMPANIES.get(ticker, {}).get("dcf", {}))


if __name__ == "__main__":
    main()
