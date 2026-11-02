"""
Ratio analysis, DCF valuation and comparable company analysis for each company.

    python main.py                  # every company in config.py
    python main.py RR.L TSCO.L      # specific tickers
    python main.py --only ratios    # one section (or: --only dcf, --only comps)
    python main.py --only portfolio # the model portfolio analysis
    python main.py --refresh        # re-download instead of using cached data
"""

import argparse
import warnings

import numpy as np
import pandas as pd

import config
from config import COMPANIES, MARKET, PORTFOLIO
from src.comps import company_metrics, figures_table, implied_value, peer_table, one_off_warnings
from src.data import fetch_company
from src.dcf import _price_in_reporting_units, build_inputs, reverse_dcf, sensitivity, value, wacc
from src.portfolio import (compare_allocations, correlation_table, covariance,
                           daily_returns, equal_weight, fetch_prices,
                           minimum_variance, risk_contributions, risk_parity)
from src.ratios import compute_ratios, trend_flags

# yfinance triggers pandas deprecation warnings that aren't about this code
warnings.filterwarnings("ignore", module="yfinance")

MULTIPLES = {"Net debt / EBITDA"}  # shown as 1.5x; everything else as a %


def format_table(ratios: pd.DataFrame) -> pd.DataFrame:
    table = ratios.T.astype(object)
    for row in table.index:
        fmt = "{:.1f}x" if row in MULTIPLES else "{:.1%}"
        table.loc[row] = ["–" if pd.isna(x) else fmt.format(x) for x in table.loc[row]]
    return table


def show_ratios(co: dict) -> None:
    ratios = compute_ratios(co)
    print(format_table(ratios))
    for flag in trend_flags(ratios) or ["No warning flags."]:
        print(" -", flag)


def money(x: float) -> str:
    """Large amounts in millions with thousands separators."""
    return f"{x / 1e6:,.0f}m"


def show_dcf(co: dict, overrides: dict) -> None:
    try:
        x, sources = build_inputs(co, overrides, MARKET)
    except ValueError as e:
        print(f"\nDCF skipped: {e}")
        return

    print("\n--- DCF inputs ---")
    pct = {"revenue_growth", "base_ebit_margin", "target_ebit_margin", "tax_rate",
           "da_pct", "capex_pct", "target_capex_pct", "nwc_pct", "terminal_growth", "risk_free", "erp",
           "cost_of_debt"}
    for name, source in sources.items():
        v = getattr(x, name)
        if v is None:
            shown = "-"
        elif name == "revenue_growth":
            shown = ", ".join(f"{g:.1%}" for g in v)
        elif name in pct:
            shown = f"{v:.1%}"
        elif name in {"beta", "price"}:
            shown = f"{v:.2f}"
        else:
            shown = money(v)
        print(f"  {name:<20} {shown:<40} ({source})")

    print("\n--- Cost of capital ---")
    for k, v in wacc(x).items():
        print(f"  {k:<24} {v:.1%}")

    result = value(x)
    f = result["forecast"].copy()
    for col in f.columns:
        if col in {"Growth", "EBIT margin"}:
            f[col] = f[col].map("{:.1%}".format)
        elif col == "Discount factor":
            f[col] = f[col].map("{:.3f}".format)
        else:
            f[col] = f[col].map(money)
    print("\n--- Forecast ---")
    print(f.T)

    print("\n--- Valuation ---")
    for k in ["PV of forecast FCF", "PV of terminal value", "Enterprise value",
              "Net debt", "Equity value"]:
        print(f"  {k:<28} {money(result[k]):>12}")
    print(f"  {'Value per share':<28} {result['Value per share']:>12.2f}")
    print(f"  {'Current price':<28} {result['Current price']:>12.2f}")
    print(f"  {'Implied upside':<28} {result['Upside']:>12.1%}")
    tv_share = result["Terminal value share of EV"]
    print(f"  {'Terminal value % of EV':<28} {tv_share:>12.0%}")
    if tv_share > 0.75:
        print("  Note: most of the value sits in the terminal value, so the result "
              "is very sensitive to WACC and terminal growth.")
    final_capex = x.capex_pct if x.target_capex_pct is None else x.target_capex_pct
    if final_capex < x.da_pct:
        print("  Note: capex is below D&A, so the asset base shrinks in the terminal "
              "year while revenue keeps growing. Consider capex (or target_capex_pct) >= da_pct.")

    w = result["WACC"]
    t = x.terminal_growth
    table = sensitivity(x, "wacc", np.round(np.arange(w - 0.01, w + 0.0101, 0.005), 4),
                        "terminal_growth", np.round(np.arange(t - 0.01, t + 0.0101, 0.005), 4))
    print("\n--- Value per share: WACC (rows) vs terminal growth (columns) ---")
    print(_fmt_grid(table))

    m = x.target_ebit_margin
    table = sensitivity(x, "growth_shift", [-0.02, -0.01, 0.0, 0.01, 0.02],
                        "target_ebit_margin", np.round(np.arange(m - 0.02, m + 0.0201, 0.01), 4))
    print("\n--- Value per share: revenue growth shift (rows) vs target EBIT margin (columns) ---")
    print(_fmt_grid(table, row_signed=True))

    print(f"\n--- Reverse DCF: what the current price of {x.price:.2f} implies ---")
    print("  Each row changes one assumption, holding the rest fixed.")
    rev = reverse_dcf(x)
    for label, row in rev.iterrows():
        signed = label.startswith("Revenue growth shift")
        fmt = "{:+.1%}" if signed else "{:.1%}"
        needed = row["Needed to justify price"]
        shown = "not reachable" if needed is None or pd.isna(needed) else fmt.format(needed)
        print(f"  {label:<36} current {fmt.format(row['Current']):>7}   needed {shown:>13}")


def show_comps(ticker: str, co: dict, cfg: dict, refresh: bool) -> None:
    overrides = cfg.get("dcf", {})
    adjustments = getattr(config, "PEER_ADJUSTMENTS", {})
    target = company_metrics(co, overrides, adjustments.get(ticker))
    peers = {}
    for p in cfg.get("peers", []):
        try:
            peers[p] = company_metrics(fetch_company(p, refresh=refresh),
                                       adjustments=adjustments.get(p))
        except Exception as e:  # one bad download shouldn't stop the rest
            print(f"  Skipped peer {p}: {e}")
    if not peers:
        print("\nComps skipped: no peers available.")
        return

    figs = figures_table(ticker, target, peers)
    for c in figs.columns[1:]:
        figs[c] = figs[c].map(lambda v: "–" if pd.isna(v) else f"{v:,.0f}")
    print("\n--- Figures used (millions, each company's reporting currency) ---")
    print(figs)

    table = peer_table(ticker, target, peers)
    shown = table.copy()
    for k in table.columns[1:]:
        shown[k] = table[k].map(lambda v: "–" if pd.isna(v) else f"{v:.1f}x")
    print("\n--- Comparable companies (trailing multiples) ---")
    print(shown)
    skipped = [t for t, m in peers.items() if not m["Comparable"]]
    if skipped:
        print("  Blank rows: share price and accounts in different currencies: "
              + ", ".join(skipped))
    if overrides:
        print("  Target figures use the underlying base year from the DCF overrides.")
    for t, m in {ticker: target, **peers}.items():
        if m["Adjusted"]:
            print(f"  {t}: adjusted figures used for " + ", ".join(m["Adjusted"]))
        for w in one_off_warnings(m):
            print(f"  Check {t}: {w}")

    price = _price_in_reporting_units(co["info"])
    implied = implied_value(target, table.loc["Peer median"], price)
    if implied.empty:
        return
    out = implied.copy()
    out["Peer median"] = implied["Peer median"].map("{:.1f}x".format)
    for c in ["Applied to", "Implied EV", "Implied equity"]:
        out[c] = implied[c].map(money)
    out["Value per share"] = implied["Value per share"].map("{:.2f}".format)
    out["Upside"] = implied["Upside"].map("{:+.1%}".format)
    print(f"\n--- Implied value from peer medians (current price {price:.2f}) ---")
    print(out)
    v = implied["Value per share"]
    print(f"  Range: {v.min():.2f} to {v.max():.2f} per share (median {v.median():.2f})")


def portfolio_risk_free() -> tuple[float, str]:
    rf = PORTFOLIO.get("risk_free")
    if rf is not None:
        return rf, "config"
    return MARKET["risk_free"]["GBP"], "today's gilt yield (set PORTFOLIO risk_free for the period average)"


def show_portfolio(refresh: bool) -> None:
    weights = pd.Series(PORTFOLIO["weights"], dtype=float)
    weights /= weights.sum()
    prices = fetch_prices(list(weights.index), PORTFOLIO["start"], refresh)
    returns = daily_returns(prices)
    cov = covariance(returns)
    rf, rf_source = portfolio_risk_free()

    print(f"\n=== Model portfolio | {returns.index[0]:%d %b %Y} to "
          f"{returns.index[-1]:%d %b %Y}, in GBP ===")
    allocations = {
        "My weights": weights,
        "Equal weight": equal_weight(list(weights.index)),
        "Minimum variance": minimum_variance(cov),
        "Risk parity": risk_parity(cov),
    }
    print("\n--- Weights ---")
    print(pd.DataFrame(allocations).map("{:.1%}".format))

    table = compare_allocations(returns, allocations, rf, PORTFOLIO["benchmark"])
    shown = table.copy().astype(object)
    for row in table.index:
        fmt = "{:.2f}" if row in ("Sharpe ratio", "Beta vs global equity") else "{:.1%}"
        shown.loc[row] = [fmt.format(v) for v in table.loc[row]]
    print("\n--- Results ---")
    print(shown)
    print(f"  Risk-free rate {rf:.2%} ({rf_source}).")

    print("\n--- Share of risk vs share of money (my weights) ---")
    rc = risk_contributions(weights, cov)
    print(pd.DataFrame({"Weight": weights, "Share of risk": rc}).map("{:.1%}".format))

    print("\n--- Correlation of daily returns ---")
    print(correlation_table(returns).round(2))


def _fmt_grid(t: pd.DataFrame, row_signed: bool = False) -> pd.DataFrame:
    out = t.map(lambda v: "–" if pd.isna(v) else f"{v:.2f}")
    out.index = [f"{i:+.1%}" if row_signed else f"{i:.1%}" for i in t.index]
    out.columns = [f"{c:.1%}" for c in t.columns]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Equity research tool")
    parser.add_argument("tickers", nargs="*", help="Yahoo Finance tickers")
    parser.add_argument("--only", choices=["ratios", "dcf", "comps", "portfolio"], help="run one section")
    parser.add_argument("--refresh", action="store_true", help="re-download data")
    args = parser.parse_args()

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)

    if args.only == "portfolio":
        show_portfolio(args.refresh)
        return

    for ticker in args.tickers or COMPANIES:
        co = fetch_company(ticker, refresh=args.refresh)
        name = co["info"].get("longName") or ticker
        currency = co["info"].get("financialCurrency")
        print(f"\n=== {name} ({ticker}) | reporting currency: {currency} ===")

        cfg = COMPANIES.get(ticker, {})
        if args.only in (None, "ratios"):
            show_ratios(co)
        if args.only in (None, "dcf"):
            show_dcf(co, cfg.get("dcf", {}))
        if args.only in (None, "comps"):
            show_comps(ticker, co, cfg, args.refresh)


if __name__ == "__main__":
    main()
