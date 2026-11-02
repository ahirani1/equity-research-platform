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

# Adjusted figures for peers whose reported numbers include one-off items.
# Keys: Sales, EBITDA, EBIT, Earnings (in the company's reporting currency).

PEER_ADJUSTMENTS = {
    # Safran FY2025 results (13 Feb 2026), adjusted figures in EUR.
    # Earnings: €1,401m dividend at a 40% payout of adjusted net income.
    "SAF.PA": {"Sales": 31_329e6, "EBITDA": 6_318e6, "EBIT": 5_197e6,
               "Earnings": 3_500e6},

    # Tesco 2025/26 adjusted profit after tax, 52 weeks (prelim results)
    "TSCO.L": {"Earnings": 1_917e6},

    # Sainsbury's FY2025/26 prelims: underlying figures, GBP.
    # Earnings: 22.3p underlying EPS x ~2.2bn shares (cross-check: £718m PBT less ~30% tax).
    "SBRY.L": {"EBITDA": 2_330e6, "EBIT": 1_025e6, "Earnings": 495e6},
}

COMPANIES = {
    "RR.L": {  # Rolls-Royce - aero engines, power systems
        "peers": ["SAF.PA", "GE", "MTX.DE"],
            "dcf": {
            # Source: Rolls-Royce FY2025 results, 26 Feb 2026
            "base_revenue": 20_059e6,      # underlying revenue
            "base_ebit_margin": 0.173,     # underlying operating margin
            "target_ebit_margin": 0.19,    # midpoint of 18-20% 2028 target
            "revenue_growth": [0.10, 0.10, 0.10, 0.06, 0.04],  # implied by 2028 targets
            "tax_rate": 0.25,              # UK rate; current low rate reflects past losses
            "capex_pct": 0.05,             # at least D&A
            },
    },
    "TSCO.L": {  # Tesco - grocery retail
            "peers": ["SBRY.L", "AD.AS", "JMT.LS"],               
               "dcf": {
               # Source: Tesco Preliminary Results 2025/26 (year to 28 Feb 2026)
               "base_revenue": 72_464e6,      # 52-week revenue inc. fuel, exc. VAT
               "base_ebit_margin": 0.0435,    # adjusted operating profit / revenue
               "target_ebit_margin": 0.0435,  # company aims to maintain margins
               "revenue_growth": [0.03, 0.03, 0.03, 0.025, 0.025],
               "tax_rate": 0.268,             # adjusted effective tax rate
               "capex_pct": 0.0255,           # = D&A; counts new store leases as investment
               "cash": 4_517e6,               # so net debt matches company's £10,563m
               },
    },
    "ASML.AS": {  # ASML - semiconductor lithography equipment
        "peers": ["AMAT", "LRCX", "KLAC", "ASM.AS"],
               "dcf": {
               # Source: ASML Annual Report 2025; 2030 targets from Nov 2024 Investor Day
               "base_ebit_margin": 0.346,     # income from operations / sales
               "target_ebit_margin": 0.40,    # 2030: 58% gross margin less ~18% opex
               "revenue_growth": [0.117, 0.0925, 0.0925, 0.0925, 0.0925],  # €36.5bn 2026, €52bn 2030
               "tax_rate": 0.177,             # 2025 effective tax rate
               "capex_pct": 0.05,             # 2025 actual
               "target_capex_pct": 0.035,     # near steady state by 2030
               "cash": 13_322e6,              # cash + short-term investments
               },
    },
}

# Model portfolio: a core of three funds plus my three researched stocks as
# satellite positions. Holdings are fixed; weights can be changed in the
# dashboard. Stock weights are tilted by my valuation work: Tesco looks
# roughly fairly valued; Rolls-Royce and ASML look expensive on both the DCF
# and comps, so they get smaller positions.
PORTFOLIO = {
    "start": "2020-01-01",      # first date of price history used
    "benchmark": "VWRP.L",      # market proxy for beta
    # Risk-free rate for the Sharpe ratio: average Bank Rate over the period,
    # weighted by time. Source: Bank of England, Official Bank Rate history,
    # Jan 2020 - Oct 2026 (approx.)
    "risk_free": 0.028,
    "weights": {
        "VWRP.L": 0.50,   # Vanguard FTSE All-World (accumulating)
        "IGLT.L": 0.20,   # iShares Core UK Gilts
        "SGLN.L": 0.10,   # iShares Physical Gold
        "TSCO.L": 0.10,
        "RR.L": 0.05,
        "ASML.AS": 0.05,
    },

    # Funds aren't valued with a DCF; fill these in from each fund's factsheet.
        "funds": {
        # Sources: fund factsheets / product pages, Sept-Oct 2026
        "VWRP.L": {"name": "Vanguard FTSE All-World", "role": "Core: global shares",
                   "ocf": 0.0014},
        "IGLT.L": {"name": "iShares Core UK Gilts", "role": "Core: stability and income",
                   "ocf": 0.0007, "yield": 0.0518, "duration": 6.97},
        "SGLN.L": {"name": "iShares Physical Gold", "role": "Core: diversifier",
                   "ocf": 0.0012},
    },
}
