# Equity Research Platform

A Python tool for the first stage of equity research on listed companies:
pulling financial statements, analysing performance against history, and
building towards peer comparison and DCF valuation.

I started this after writing equity research reports for my university
investment club, where most of the time went on collecting data and
rebuilding the same ratio tables by hand. The aim is to automate that part
so the effort goes into the judgement calls: which peers are genuinely
comparable, which assumptions drive the valuation, and where the reported
numbers can't be taken at face value.

## What it does

- Downloads income statement, balance sheet and cash flow data (Yahoo Finance)
  and caches it locally
- Calculates growth, margins, ROE, ROIC, leverage, cash conversion and capex
  intensity across the available history
- Flags patterns worth investigating, such as falling margins, negative equity,
  weak cash conversion or a large gap between reported and normalised profit

```
=== Tesco PLC (TSCO.L) | reporting currency: GBP ===
Fiscal year                   2023    2024    2025    2026
Revenue growth                   –    4.4%    2.5%    5.4%
EBIT margin                   2.3%    4.5%    4.3%    4.3%
ROIC                             –    9.7%    9.0%    9.8%
Net debt / EBITDA             3.9x    2.6x    2.6x    2.4x
...
```

## Methodology

- **Non-financial companies only.** For banks and insurers, debt is part of
  the operating business rather than financing, so free cash flow and
  EV/EBITDA aren't meaningful. They need price-to-book against ROE or a
  dividend discount model instead.
- **Returns use average capital.** ROE and ROIC divide a full year's profit
  by the average of opening and closing balances.
- **Ratios over a negative base are left blank.** Rolls-Royce had negative
  shareholders' equity for several years, which produced ROE figures like
  -110% and +644%. These are now shown as blank and flagged instead.
- **Invested capital = equity + total debt - cash**, applied the same way to
  every company.
- **Reported vs normalised profit.** Free data sources don't always strip out
  one-off items. Rolls-Royce's reported 2025 EBITDA margin is inflated by
  items its own "underlying" figures exclude, so headline numbers need
  checking against the annual report before they go into a valuation.

## Project structure

```
config.py        companies to analyse and their peer groups
main.py          entry point
src/data.py      data download, cleaning and caching
src/ratios.py    ratio calculations and warning flags
```

## Running it

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py                 # all companies in config.py
python main.py ASML.AS         # a single ticker
python main.py --refresh       # re-download the data
```

## Planned

- DCF valuation with a WACC build-up and sensitivity tables, with manual
  overrides for base-year figures where the data feed is misleading
- Comparable company analysis against each peer group
- Streamlit dashboard bringing it together, with a written summary per company
