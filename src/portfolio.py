"""
Portfolio analysis: risk, diversification and allocation for a fixed set of
holdings, measured in pounds from a UK investor's point of view.

Methodology notes:
- Daily adjusted closing prices (dividends reinvested) from Yahoo Finance.
  London prices quoted in pence are converted to pounds, and euro prices are
  converted at the daily EUR/GBP rate, so a euro-listed share's risk includes
  its currency risk for a UK investor.
- Dates are aligned across exchanges and only days where every holding has a
  price are used.
- Returns and volatility are annualised from daily data (252 trading days).
- Allocation methods that need only volatility and correlation (minimum
  variance, risk parity) are used rather than ones that also need expected
  returns, because expected returns estimated from past prices are too noisy
  and produce extreme, unstable weights.
- All allocations are long-only and fully invested (weights >= 0, sum to 1).
"""

from pathlib import Path

import numpy as np
import pandas as pd

PRICE_CACHE = Path(__file__).resolve().parent.parent / "data" / "prices"
TRADING_DAYS = 252
FX_TICKERS = {"EUR": "EURGBP=X", "USD": "USDGBP=X"}


def _download(ticker: str, start: str) -> tuple[pd.Series, str]:
    import yfinance as yf
    t = yf.Ticker(ticker)
    hist = t.history(start=start, auto_adjust=True)["Close"]
    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    currency = t.info.get("currency") or ""
    return hist, currency


def fetch_prices(tickers: list[str], start: str = "2020-01-01",
                 refresh: bool = False) -> pd.DataFrame:
    """Daily prices in GBP for each ticker, cached as CSV."""
    PRICE_CACHE.mkdir(parents=True, exist_ok=True)
    prices = {}
    for tk in tickers:
        path = PRICE_CACHE / f"{tk}.csv"
        if path.exists() and not refresh:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            series, currency = df["price"], df["currency"].iloc[0]
        else:
            series, currency = _download(tk, start)
            pd.DataFrame({"price": series, "currency": currency}).to_csv(path)
        prices[tk] = (series, currency)

    out = {}
    for tk, (series, currency) in prices.items():
        if currency == "GBp":
            out[tk] = series / 100
        elif currency == "GBP":
            out[tk] = series
        elif currency in FX_TICKERS:
            fx = fetch_fx(FX_TICKERS[currency], start, refresh)
            out[tk] = series * fx.reindex(series.index).ffill()
        else:
            raise ValueError(f"No currency conversion set up for {tk} ({currency})")
    return pd.DataFrame(out).dropna()


def fetch_fx(fx_ticker: str, start: str, refresh: bool) -> pd.Series:
    path = PRICE_CACHE / f"{fx_ticker}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)["price"]
    series, _ = _download(fx_ticker, start)
    pd.DataFrame({"price": series, "currency": "GBP"}).to_csv(path)
    return series


# ------------------------------------------------------------ statistics
def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Annualised covariance matrix."""
    return returns.cov() * TRADING_DAYS


def correlation_table(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr()


def max_drawdown(value: pd.Series) -> float:
    """Largest fall from a previous peak, as a negative fraction."""
    return float((value / value.cummax() - 1).min())


def stats(returns: pd.Series, risk_free: float, market: pd.Series | None = None) -> dict:
    """Headline statistics for one return series (a holding or a portfolio)."""
    value = (1 + returns).cumprod()
    years = len(returns) / TRADING_DAYS
    ann_return = float(value.iloc[-1] ** (1 / years) - 1)
    vol = float(returns.std() * np.sqrt(TRADING_DAYS))
    out = {
        "Annual return": ann_return,
        "Volatility": vol,
        "Sharpe ratio": (ann_return - risk_free) / vol if vol else np.nan,
        "Max drawdown": max_drawdown(value),
    }
    if market is not None:
        out["Beta vs global equity"] = float(returns.cov(market) / market.var())
    return out


def portfolio_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Daily portfolio returns, rebalanced back to the target weights daily."""
    return returns[weights.index] @ weights


def risk_contributions(weights: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Each holding's share of total portfolio variance (sums to 1)."""
    w = weights.values
    c = cov.loc[weights.index, weights.index].values
    marginal = c @ w
    total = w @ marginal
    return pd.Series(w * marginal / total, index=weights.index)


# ----------------------------------------------------------- allocations
def equal_weight(tickers: list[str]) -> pd.Series:
    return pd.Series(1 / len(tickers), index=tickers)


def minimum_variance(cov: pd.DataFrame, iterations: int = 5000) -> pd.Series:
    """Long-only weights with the lowest portfolio volatility, by projected
    gradient descent: step downhill on variance, then project back onto
    'weights >= 0 and sum to 1'."""
    n = len(cov)
    c = cov.values
    w = np.full(n, 1 / n)
    step = 1 / np.linalg.eigvalsh(c).max()
    for _ in range(iterations):
        w = _project_to_simplex(w - step * 2 * c @ w)
    return pd.Series(w, index=cov.index)


def risk_parity(cov: pd.DataFrame, iterations: int = 500) -> pd.Series:
    """Weights where every holding contributes the same share of risk.
    Uses the standard fixed-point iteration w_i proportional to
    1 / (marginal risk of i)."""
    c = cov.values
    w = np.full(len(c), 1 / len(c))
    for _ in range(iterations):
        marginal = c @ w
        w_new = 1 / marginal
        w_new /= w_new.sum()
        w = 0.5 * w + 0.5 * w_new
    # Refine so contributions are equal: w_i * (Cw)_i should be constant
    for _ in range(iterations):
        rc = w * (c @ w)
        w *= (rc.mean() / rc) ** 0.5
        w /= w.sum()
    return pd.Series(w, index=cov.index)


def _project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Closest point to v with all entries >= 0 summing to 1."""
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, len(v) + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1)
    return np.maximum(v - theta, 0)


def compare_allocations(returns: pd.DataFrame, allocations: dict[str, pd.Series],
                        risk_free: float, market: str) -> pd.DataFrame:
    """Statistics for each allocation side by side."""
    rows = {}
    for name, w in allocations.items():
        r = portfolio_returns(returns, w)
        rows[name] = stats(r, risk_free, returns[market])
    return pd.DataFrame(rows)
