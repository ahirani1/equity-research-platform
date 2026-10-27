"""
Step 1: download data for each target company and print its ratio history
and trend flags.

    python run_step1.py            # uses cached data where available
    python run_step1.py --refresh  # forces a fresh download
"""

import sys

import pandas as pd

from config import COMPANIES
from src.data import fetch_company
from src.ratios import compute_ratios, trend_flags

pd.set_option("display.width", 160)

refresh = "--refresh" in sys.argv
MULTIPLES = {"Net debt / EBITDA"}  # shown as 1.5x; everything else as a %

for ticker in COMPANIES:
    co = fetch_company(ticker, refresh=refresh)
    name = co["info"].get("longName") or ticker
    print(f"\n=== {name} ({ticker}) | reporting currency: "
          f"{co['info'].get('financialCurrency')} ===")

    ratios = compute_ratios(co)
    table = ratios.T.astype(object)
    for row in table.index:
        fmt = "{:.1f}x" if row in MULTIPLES else "{:.1%}"
        table.loc[row] = [("" if pd.isna(x) else fmt.format(x)) for x in table.loc[row]]
    print(table)

    for f in trend_flags(ratios) or ["No warning flags."]:
        print(" -", f)
