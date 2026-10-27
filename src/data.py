"""
Downloads annual financial statements and company info from Yahoo Finance
(via yfinance), tidies them into a consistent shape, and caches them as CSV
so repeat runs don't hit the network.

Output shape for each statement: one row per fiscal year (oldest -> newest),
one column per line item, e.g.

              Total Revenue   Net Income   ...
    2022-12-31   1.2e10         8.0e8
    2023-12-31   1.4e10         1.1e9
"""

from pathlib import Path
import json

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

STATEMENTS = {
    "income": "income_stmt",
    "balance": "balance_sheet",
    "cashflow": "cashflow",
}

# Info fields we keep (yfinance's .info has ~150; most are noise for us)
INFO_FIELDS = [
    "longName", "sector", "industry", "currency", "financialCurrency",
    "marketCap", "sharesOutstanding", "currentPrice", "beta",
]


def _tidy(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance gives line items as rows and dates as columns, newest first.
    Flip it so years are rows, oldest first, and drop all-empty years."""
    df = raw.T
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df.dropna(how="all")


def fetch_company(ticker: str, refresh: bool = False) -> dict:
    """Return {'income': df, 'balance': df, 'cashflow': df, 'info': dict}
    for one ticker, using the local cache unless refresh=True."""
    folder = CACHE_DIR / ticker
    info_path = folder / "info.json"

    if not refresh and info_path.exists():
        out = {
            name: pd.read_csv(folder / f"{name}.csv", index_col=0, parse_dates=True)
            for name in STATEMENTS
        }
        out["info"] = json.loads(info_path.read_text())
        return out

    import yfinance as yf  # imported here so cached runs work offline

    t = yf.Ticker(ticker)
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, attr in STATEMENTS.items():
        df = _tidy(getattr(t, attr))
        if df.empty:
            raise ValueError(f"No {name} statement returned for {ticker}")
        df.to_csv(folder / f"{name}.csv")
        out[name] = df

    info = {k: t.info.get(k) for k in INFO_FIELDS}
    info_path.write_text(json.dumps(info, indent=2))
    out["info"] = info
    return out


def get(df: pd.DataFrame, *names: str) -> pd.Series:
    """Return the first line item that exists, trying each name in turn.
    Companies label things differently (e.g. 'Operating Income' vs 'EBIT'),
    so callers pass a few alternatives. Missing -> a series of NaN."""
    for n in names:
        if n in df.columns:
            return df[n].astype(float)
    return pd.Series(float("nan"), index=df.index, name=names[0])
