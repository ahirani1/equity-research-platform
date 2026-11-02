"""
Companies to analyse, their peer groups, and valuation assumptions.

Peers are chosen on business model and end market rather than just sector
classification. Tickers use Yahoo Finance format: '.L' London, '.PA' Paris,
'.AS' Amsterdam, '.DE' Germany, no suffix for US listings.
"""

# Market-wide inputs for the cost of capital. Record the source and date of
# each figure when you update it.
MARKET = {
    # 10-year government bond yield in each reporting currency
    "risk_free": {
        "GBP": 0.0535,   # UK 10-year gilt yield. Source: FT, date: 27 Oct 2026
        "EUR": 0.0335,   # German 10-year Bund yield. Source: Bundesbank, date: 27 Oct 2026
        "USD": None,     # US 10-year Treasury yield. Source: , date:
    },
    # Equity risk premium. Source: Damodaran implied ERP, date: Jan 2026
    "equity_risk_premium": 0.0423,
}

# DCF overrides go under "dcf". Anything not set defaults to the company's
# own history (see src/dcf.py). Available keys:
#   revenue_growth       single rate or a list of 5 (one per forecast year)
#   base_ebit_margin     starting margin, e.g. an "underlying" figure from the
#                        annual report when the reported one is distorted
#   target_ebit_margin   margin reached by year 5
#   tax_rate, da_pct, capex_pct, nwc_pct, terminal_growth, beta, cost_of_debt
COMPANIES = {
    "RR.L": {  # Rolls-Royce - aero engines, power systems
        "peers": ["SAF.PA", "GE", "MTX.DE"],
        "dcf": {},
    },
    "TSCO.L": {  # Tesco - grocery retail
        "peers": ["SBRY.L", "AD.AS", "CA.PA"],
        "dcf": {},
    },
    "ASML.AS": {  # ASML - semiconductor lithography equipment
        "peers": ["AMAT", "LRCX", "KLAC"],
        "dcf": {},
    },
}
