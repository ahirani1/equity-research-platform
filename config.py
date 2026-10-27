"""
Companies to analyse and their peer groups.

Peers are chosen on business model and end market rather than just sector
classification. Tickers use Yahoo Finance format: '.L' London, '.PA' Paris,
'.AS' Amsterdam, '.DE' Germany, no suffix for US listings.
"""

COMPANIES = {
    "RR.L": {  # Rolls-Royce - aero engines, power systems
        "peers": ["SAF.PA", "GE", "MTX.DE"],
    },
    "TSCO.L": {  # Tesco - grocery retail
        "peers": ["SBRY.L", "AD.AS", "CA.PA"],
    },
    "ASML.AS": {  # ASML - semiconductor lithography equipment
        "peers": ["AMAT", "LRCX", "KLAC"],
    },
}
