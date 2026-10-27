"""
Your choices live here. Change the target companies and peer groups to
whatever you want to analyse - choosing comparable peers (and being able to
justify them) is one of the judgement calls interviewers ask about.

Tickers use Yahoo Finance format: '.L' = London, '.PA' = Paris, '.AS' =
Amsterdam, '.DE' = Germany, no suffix = US listing.
"""

COMPANIES = {
    "RR.L": {  # Rolls-Royce - aerospace engines
        "peers": ["SAF.PA", "GE", "MTX.DE"],
    },
    "TSCO.L": {  # Tesco - grocery retail
        "peers": ["SBRY.L", "AD.AS", "CA.PA"],
    },
    "ASML.AS": {  # ASML - semiconductor equipment
        "peers": ["AMAT", "LRCX", "KLAC"],
    },
}
