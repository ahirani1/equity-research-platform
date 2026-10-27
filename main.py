"""
Print a ratio history and warning flags for each company.

    python main.py                  # every company in config.py
    python main.py RR.L TSCO.L      # specific tickers
    python main.py --refresh        # re-download instead of using cached data
"""

import argparse

import pandas as pd

from config import COMPANIES
from src.data import fetch_company
from src.ratios import compute_ratios, trend_flags

MULTIPLES = {"Net debt / EBITDA"}  # shown as 1.5x; everything else as a %


def format_table(ratios: pd.DataFrame) -> pd.DataFrame:
    table = ratios.T.astype(object)
    for row in table.index:
        fmt = "{:.1f}x" if row in MULTIPLES else "{:.1%}"
        table.loc[row] = ["–" if pd.isna(x) else fmt.format(x) for x in table.loc[row]]
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="Financial ratio analysis")
    parser.add_argument("tickers", nargs="*", help="Yahoo Finance tickers")
    parser.add_argument("--refresh", action="store_true", help="re-download data")
    args = parser.parse_args()

    pd.set_option("display.width", 160)

    for ticker in args.tickers or COMPANIES:
        co = fetch_company(ticker, refresh=args.refresh)
        name = co["info"].get("longName") or ticker
        currency = co["info"].get("financialCurrency")
        print(f"\n=== {name} ({ticker}) | reporting currency: {currency} ===")

        ratios = compute_ratios(co)
        print(format_table(ratios))
        for flag in trend_flags(ratios) or ["No warning flags."]:
            print(" -", flag)


if __name__ == "__main__":
    main()
