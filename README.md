# Equity Research Platform

A Python tool that automates the first stage of equity research for listed
non-financial companies: financial ratio analysis, peer comparables and DCF
valuation, presented in a Streamlit dashboard.

## Status

- [x] Step 1 – Data layer and ratio analysis
- [ ] Step 2 – DCF engine with WACC build-up and sensitivity tables
- [ ] Step 3 – Comparable company analysis
- [ ] Step 4 – Streamlit dashboard
- [ ] Step 5 – Investment summary

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_step1.py
```

Target companies and peer groups are set in `config.py`.

## Why non-financial companies only

Banks and insurers are valued differently: debt is their raw material rather
than financing, so free cash flow and EV/EBITDA aren't meaningful. They need
price-to-book vs ROE or a dividend discount model instead.
