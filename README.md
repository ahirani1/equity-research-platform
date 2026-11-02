# Equity Research Platform

Live demo: https://aaryan-equity-research.streamlit.app

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
- Values each company with a five-year DCF: WACC build-up, forecast free cash
  flow, terminal value, bridge to value per share, and sensitivity tables for
  WACC vs terminal growth and revenue growth vs margin
- Runs a reverse DCF: for each key assumption, the value it would need to
  take to justify the current share price
- Checks credit strength (interest cover, leverage, Altman Z-score) and
  accounting quality (cash conversion, accruals), and lists every figure I've
  changed from the data feed next to the original
- Compares each company with a peer group on EV/Sales, EV/EBITDA, EV/EBIT and
  P/E, and values it at the peer median multiples
- Models a leveraged buyout of Tesco: sources and uses, a debt schedule with a
  cash sweep, IRR and money multiple, where the return comes from, and the
  highest price a private equity buyer could pay for a 20% IRR

```
=== Tesco PLC (TSCO.L) | reporting currency: GBP ===
Fiscal year                   2023    2024    2025    2026
Revenue growth                   –    4.4%    2.5%    5.4%
EBIT margin                   2.3%    4.5%    4.3%    4.3%
ROIC                             –    9.7%    9.0%    9.8%
Net debt / EBITDA             3.9x    2.6x    2.6x    2.4x
...
```

## Dashboard

```bash
streamlit run app.py
```

An interactive version of the analysis. Pick a company and move through:

- **Overview**: share price against the DCF and comps values, with a chart
  of each method's range
- **Financials**: ratio history, margin trends, credit strength, accounting
  quality and my adjustments to the data feed
- **DCF**: sliders for growth, margin, WACC, terminal growth, tax and capex
  that revalue the company live, plus the forecast, the bridge from enterprise
  value to share price, the reverse DCF and a sensitivity heatmap
- **Comparables**: peer multiples, the figures behind them and the implied
  values
- **LBO** (Tesco): buyout returns with sliders for the premium, debt and exit
  multiple; the price floor also appears on the overview chart
- **My view**: my written conclusion for each company (`summaries/<ticker>.md`)

A second view, **Model portfolio**, combines a core of three funds (global
shares, UK gilts, gold) with my three researched stocks as satellite
positions. It compares my weights, tilted by the valuation work, against equal
weight, minimum variance and risk parity on return, volatility, Sharpe ratio,
maximum drawdown and beta, and shows correlations and each holding's share of
risk. Everything is in pounds.

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
- **DCF inputs default to history and can be overridden.** Each input is
  printed with its source (history, data feed or my override), so it's clear
  which numbers are assumptions. Growth fades in a straight line from the
  recent average to the terminal rate.
- **Leases are treated as debt.** Under IFRS 16, lease costs sit below EBIT,
  so lease liabilities are included in net debt to stay consistent with the
  free cash flow definition.
- **London prices are converted from pence.** Yahoo quotes LSE shares in GBp
  while the accounts are in pounds.
- **Margin and capex can move towards targets.** Both change in a straight
  line to a target by the final forecast year. Useful for a company like ASML,
  which is investing heavily now but won't need to forever, and for following
  management's medium-term margin targets. Where a company has already guided
  to a year-one margin well above the base year (Rolls-Royce and ASML raised
  2026 guidance mid-year), the year-one margin can be set directly, while the
  base year stays as reported for the comps and credit checks.
- **Adjusted beta.** Raw betas from the data feed are Blume-adjusted
  (0.67 x raw + 0.33), since measured betas tend to drift towards 1.
- **Reverse DCF.** When my valuation and the market disagree, I solve for
  the margin, growth, terminal growth or WACC the share price implies (one at
  a time, by bisection) and judge whether those are realistic.
- **Comparable companies.** Trailing multiples (latest full year), enterprise
  value = market cap + debt - cash, and the peer median rather than the mean so
  one outlier can't dominate. Peers with a share price and accounts in
  different currencies are left out rather than mixed. The target uses the same
  underlying base year as its DCF, so the two methods are comparable.
- **Credit and accounting checks.** Interest cover = EBIT / interest. The
  Altman Z-score is a bankruptcy screen built on US manufacturers, so it's a
  rough signal for other sectors. The accruals ratio (net income minus
  operating cash flow, over average assets) flags profit running ahead of cash.
- **LBO on the DCF forecast.** The buyout uses the same operating forecast as
  the DCF. Senior debt is repaid from all spare cash; high-yield bonds are
  repaid at exit. The price floor assumes the fund sells at the multiple it
  paid, so a cheaper purchase isn't flattered by a more expensive sale.
  Existing net debt including leases is treated as refinanced, a
  simplification. Tesco's size (about £44bn of enterprise value) would make
  this the largest UK buyout on record, so the results show what the business
  could support rather than a prediction.
- **Portfolio in pounds.** Euro-listed holdings are converted at the daily
  EUR/GBP rate, so their risk includes currency risk for a UK investor.
- **No return forecasts in the optimisers.** Minimum variance and risk parity
  use only volatility and correlation, because expected returns estimated from
  past prices are too noisy and give extreme, unstable weights.
- **Funds aren't valued with a DCF.** A fund is worth its holdings, so each is
  assessed on its role, ongoing charge and (for gilts) yield and duration.
- **Reported vs normalised profit.** Free data sources don't always strip out
  one-off items. Rolls-Royce's reported 2025 EBITDA margin is inflated by
  items its own "underlying" figures exclude, so headline numbers need
  checking against the annual report before they go into a valuation.

## Project structure

```
config.py        companies to analyse and their peer groups
main.py          command-line entry point
app.py           Streamlit dashboard
summaries/       my written view on each company
src/data.py      data download, cleaning and caching
src/ratios.py    ratio calculations and warning flags
src/quality.py   credit metrics, accounting quality and adjustment log
src/dcf.py       DCF valuation, sensitivity analysis and reverse DCF
src/comps.py     comparable company analysis
src/lbo.py       leveraged buyout returns and price floor
src/portfolio.py portfolio risk and allocation
```

## Running it

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py                 # all companies in config.py
python main.py ASML.AS         # a single ticker
python main.py --only dcf      # just the DCF (or: ratios, quality, comps, lbo)
python main.py --only portfolio  # the model portfolio
python main.py --refresh       # re-download the data
```

## Planned

- Written equity research report on Rolls-Royce, Tesco and ASML
