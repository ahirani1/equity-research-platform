"""
Interactive dashboard for the equity research tool.

    streamlit run app.py

Pick a company in the sidebar, then move through the tabs: an overview with
the valuation summary, the ratio history, the DCF (with live assumption
sliders), the comparable company analysis, and my written view.
"""

import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from config import COMPANIES, MARKET, PORTFOLIO
from src.comps import (company_metrics, figures_table, implied_value, peer_table,
                       warnings)
from src.data import fetch_company
from src.dcf import (_price_in_reporting_units, build_inputs, reverse_dcf,
                     sensitivity, value, wacc)
from src.portfolio import (compare_allocations, correlation_table, covariance,
                           daily_returns, equal_weight, fetch_prices,
                           minimum_variance, portfolio_returns, risk_contributions,
                           risk_parity)
from src.ratios import compute_ratios, trend_flags

# yfinance triggers pandas deprecation warnings that aren't about this code
warnings.filterwarnings("ignore", module="yfinance")

SYMBOL = {"GBP": "£", "EUR": "€", "USD": "$"}
SUMMARY_DIR = Path(__file__).parent / "summaries"

st.set_page_config(page_title="Equity Research Platform", layout="wide")


@st.cache_data(show_spinner="Loading financial data...")
def load(ticker: str) -> dict:
    return fetch_company(ticker)


def pct(v: float) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:.1%}"


def millions(v: float, sym: str) -> str:
    if v is None or pd.isna(v):
        return "–"
    sign = "-" if v < 0 else ""
    return f"{sign}{sym}{abs(v) / 1e6:,.0f}m"


# ---------------------------------------------------------------- sidebar
st.sidebar.title("Equity Research Platform")
page = st.sidebar.radio("View", ["Company research", "Model portfolio"])


@st.cache_data(show_spinner="Loading price history...")
def load_prices(tickers: tuple, start: str) -> pd.DataFrame:
    return fetch_prices(list(tickers), start)


@st.cache_data(show_spinner=False)
def base_case_upside(tk: str) -> tuple:
    """DCF and comps upside for a researched company, at my base case."""
    co_ = load(tk)
    cfg_ = COMPANIES[tk]
    adj = getattr(config, "PEER_ADJUSTMENTS", {})
    px = _price_in_reporting_units(co_["info"])
    try:
        dcf_up = value(build_inputs(co_, cfg_.get("dcf", {}), MARKET)[0])["Upside"]
    except ValueError:
        dcf_up = np.nan
    tm = company_metrics(co_, cfg_.get("dcf", {}), adj.get(tk))
    pm = {p: company_metrics(load(p), adjustments=adj.get(p)) for p in cfg_.get("peers", [])}
    imp = implied_value(tm, peer_table(tk, tm, pm).loc["Peer median"], px)
    return dcf_up, (imp["Value per share"].median() / px - 1) if not imp.empty else np.nan


def portfolio_page() -> None:
    st.title("Model portfolio")
    st.caption("A core of three funds plus my three researched stocks as "
               "satellite positions. Holdings are fixed; change the weights below "
               "to see the effect. Everything is measured in pounds.")
    base_w = pd.Series(PORTFOLIO["weights"], dtype=float)
    funds = PORTFOLIO.get("funds", {})
    prices = load_prices(tuple(base_w.index), PORTFOLIO["start"])
    returns = daily_returns(prices)
    cov = covariance(returns)
    rf = PORTFOLIO.get("risk_free")
    rf_note = "set in config"
    if rf is None:
        rf, rf_note = MARKET["risk_free"]["GBP"], "today's gilt yield; the period average would be fairer"

    st.subheader("Holdings")
    rows = []
    for tk, w in base_w.items():
        if tk in funds:
            f = funds[tk]
            parts = []
            if f.get("ocf") is not None:
                parts.append(f"Ongoing charge {f['ocf']:.2%}")
            if f.get("yield") is not None:
                parts.append(f"Yield {f['yield']:.2%}")
            if f.get("duration") is not None:
                parts.append(f"Duration {f['duration']:.1f} yrs")
            detail = ", ".join(parts)
            rows.append({"Ticker": tk, "Holding": f["name"], "Role": f["role"],
                         "Weight %": round(w * 100, 1), "Valuation view": detail or "–"})
        else:
            dcf_up, comps_up = base_case_upside(tk)
            rows.append({"Ticker": tk, "Holding": load(tk)["info"].get("longName") or tk,
                         "Role": "Satellite: researched stock", "Weight %": round(w * 100, 1),
                         "Valuation view": f"DCF {dcf_up:+.0%}, comps {comps_up:+.0%} vs price"})
    edited = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch",
                            disabled=["Ticker", "Holding", "Role", "Valuation view"],
                            key="portfolio_weights")
    w = pd.Series(edited["Weight %"].values, index=edited["Ticker"].values, dtype=float)
    if w.sum() <= 0:
        st.error("Weights must add up to more than zero.")
        return
    if abs(w.sum() - 100) > 0.05:
        st.warning(f"Weights add up to {w.sum():.1f}%; they've been scaled to 100%.")
    w = w / w.sum()

    allocations = {"My weights": w, "Equal weight": equal_weight(list(w.index)),
                   "Minimum variance": minimum_variance(cov), "Risk parity": risk_parity(cov)}

    st.subheader("Allocation methods compared")
    st.caption(f"{returns.index[0]:%d %b %Y} to {returns.index[-1]:%d %b %Y}. "
               "Minimum variance and risk parity use only volatility and correlation, "
               "not return forecasts, which are too unreliable to optimise on. "
               f"Risk-free rate {rf:.2%} ({rf_note}).")
    res = compare_allocations(returns, allocations, rf, PORTFOLIO["benchmark"])
    wt = pd.DataFrame(allocations).map("{:.1%}".format)
    res_shown = res.copy().astype(object)
    for row in res.index:
        f_ = "{:.2f}" if row in ("Sharpe ratio", "Beta vs global equity") else "{:.1%}"
        res_shown.loc[row] = [f_.format(v) for v in res.loc[row]]
    st.markdown("**Weights**")
    st.dataframe(wt, width="stretch")
    st.markdown("**Results**")
    st.dataframe(res_shown, width="stretch")

    growth = go.Figure()
    for name, aw in allocations.items():
        v = 10_000 * (1 + portfolio_returns(returns, aw)).cumprod()
        growth.add_trace(go.Scatter(x=v.index, y=v, mode="lines", name=name))
    growth.update_layout(title="Growth of £10,000", yaxis_tickprefix="£",
                         height=380, margin=dict(t=40), legend=dict(orientation="h"))
    st.plotly_chart(growth, width="stretch")
    st.caption("Past performance over one period; it shows how the mixes behaved, "
               "not what they'll return.")

    left, right = st.columns(2)
    with left:
        st.subheader("Correlation")
        corr = correlation_table(returns)
        heat = go.Figure(go.Heatmap(z=corr.values, x=list(corr.columns), y=list(corr.index),
                                    text=corr.round(2).values, texttemplate="%{text}",
                                    colorscale="RdBu", zmin=-1, zmax=1, reversescale=True))
        heat.update_layout(height=420, margin=dict(t=20), yaxis=dict(autorange="reversed"))
        st.plotly_chart(heat, width="stretch")
        st.caption("1 = always move together, 0 = unrelated, negative = tend to move "
                   "in opposite directions. Low correlations are what make "
                   "diversification work.")
    with right:
        st.subheader("Share of money vs share of risk")
        rc = risk_contributions(w, cov)
        bars = go.Figure([go.Bar(name="Share of money", x=list(w.index), y=w.values),
                          go.Bar(name="Share of risk", x=list(w.index), y=rc.values)])
        bars.update_layout(barmode="group", yaxis_tickformat=".0%", height=420,
                           margin=dict(t=20), legend=dict(orientation="h"))
        st.plotly_chart(bars, width="stretch")
        st.caption("A holding whose risk share is bigger than its money share "
                   "drives more of the portfolio's swings than its size suggests.")


if page == "Model portfolio":
    portfolio_page()
    st.stop()

names = {t: (load(t)["info"].get("longName") or t) for t in COMPANIES}
ticker = st.sidebar.selectbox("Company", list(COMPANIES), format_func=lambda t: names[t])
cfg = COMPANIES[ticker]
co = load(ticker)
info = co["info"]
sym = SYMBOL.get(info.get("financialCurrency"), "")
price = _price_in_reporting_units(info)

st.sidebar.markdown(
    f"**Sector:** {info.get('sector') or '–'}  \n"
    f"**Reporting currency:** {info.get('financialCurrency')}  \n"
    f"**Share price:** {sym}{price:,.2f}"
)
st.sidebar.caption("Data: Yahoo Finance, with adjustments from company results "
                   "where reported figures include one-off items.")

st.title(names[ticker])

# ------------------------------------------------- base-case calculations
overrides = cfg.get("dcf", {})
try:
    base_inputs, sources = build_inputs(co, overrides, MARKET)
except ValueError as e:
    base_inputs, sources = None, {}
    dcf_error = str(e)

adjustments = getattr(config, "PEER_ADJUSTMENTS", {})
target_m = company_metrics(co, overrides, adjustments.get(ticker))
peers_m = {}
for p in cfg.get("peers", []):
    try:
        peers_m[p] = company_metrics(load(p), adjustments=adjustments.get(p))
    except Exception:
        pass
comp_table = peer_table(ticker, target_m, peers_m) if peers_m else None
implied = (implied_value(target_m, comp_table.loc["Peer median"], price)
           if comp_table is not None else pd.DataFrame())

tabs = st.tabs(["Overview", "Financials", "DCF", "Comparables", "My view"])

# ---------------------------------------------------------------- DCF tab
# Built before the overview so the overview can use the live slider values.
with tabs[2]:
    if base_inputs is None:
        st.error(f"DCF unavailable: {dcf_error}")
        x = None
    else:
        b = base_inputs
        base_wacc = wacc(b)["WACC"]
        st.subheader("Assumptions")
        # Each company gets its own slider state, so changes made on one
        # company don't carry over to another. The reset counter forces fresh
        # sliders when the button is pressed.
        reset_key = f"reset_{ticker}"
        st.session_state.setdefault(reset_key, 0)
        head, btn = st.columns([4, 1])
        head.caption("Sliders start at my base case. Move them to see how the "
                     "value changes.")
        if btn.button("Reset to my base case", key=f"btn_{ticker}"):
            st.session_state[reset_key] += 1
        k = f"{ticker}_{st.session_state[reset_key]}"
        c1, c2, c3 = st.columns(3)
        # Sliders work in percentage points so they read naturally (e.g. 10.5%)
        # Sliders work in percentage points so they read naturally (e.g. 10.5%)
        growth_shift = c1.slider(
            "Revenue growth shift (every year)", -5.0, 5.0, 0.0, 0.5,
            format="%+.1f%%", key=f"{k}_growth",
            help="Added to each forecast year's growth rate") / 100
        target_margin = c1.slider(
            "Final-year EBIT margin", 0.0,
            round(max(60.0, b.target_ebit_margin * 100 + 10), 1),
            round(b.target_ebit_margin * 100, 1), 0.5, format="%.1f%%",
            key=f"{k}_margin") / 100
        wacc_in = c2.slider("WACC", 4.0, 15.0, round(base_wacc * 100, 2), 0.25,
                            format="%.2f%%", key=f"{k}_wacc") / 100
        tg = c2.slider("Terminal growth", 0.0, 4.0, round(b.terminal_growth * 100, 2),
                       0.25, format="%.2f%%", key=f"{k}_tg") / 100
        tax = c3.slider("Tax rate", 0.0, 40.0, round(b.tax_rate * 100, 1), 0.5,
                        format="%.1f%%", key=f"{k}_tax") / 100
        final_capex = b.capex_pct if b.target_capex_pct is None else b.target_capex_pct
        capex_end = c3.slider("Final-year capex (% of revenue)", 0.0, 15.0,
                              round(final_capex * 100, 2), 0.25, format="%.2f%%",
                              key=f"{k}_capex") / 100

        x = replace(b, revenue_growth=[g + growth_shift for g in b.revenue_growth],
                    target_ebit_margin=target_margin, terminal_growth=tg,
                    tax_rate=tax, target_capex_pct=capex_end,
                    wacc_override=None if abs(wacc_in - base_wacc) < 1e-4 else wacc_in)

        if x.terminal_growth >= wacc(x)["WACC"]:
            st.error("Terminal growth must be below WACC.")
            x = None

    if x is not None:
        r = value(x)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Value per share", f"{sym}{r['Value per share']:,.2f}")
        m2.metric("Share price", f"{sym}{price:,.2f}")
        m3.metric("Implied upside", pct(r["Upside"]))
        m4.metric("Terminal value share of EV", f"{r['Terminal value share of EV']:.0%}")

        st.subheader("Forecast")
        f = r["forecast"].copy()
        shown = pd.DataFrame(index=f.index)
        for c in f.columns:
            if c in {"Growth", "EBIT margin"}:
                shown[c] = f[c].map(pct)
            elif c == "Discount factor":
                shown[c] = f[c].map("{:.3f}".format)
            else:
                shown[c] = f[c].map(lambda v: millions(v, sym))
        st.dataframe(shown.T, width="stretch")

        left, right = st.columns(2)
        with left:
            st.subheader("From enterprise value to share price")
            bridge = pd.DataFrame({"": [
                millions(r["PV of forecast FCF"], sym),
                millions(r["PV of terminal value"], sym),
                millions(r["Enterprise value"], sym),
                millions(abs(r["Net debt"]), sym),
                millions(r["Equity value"], sym),
                f"{x.shares / 1e6:,.0f}m",
                f"{sym}{r['Value per share']:,.2f}",
            ]}, index=["PV of forecast cash flows", "PV of terminal value",
                       "Enterprise value",
                       "Less net debt" if r["Net debt"] > 0 else "Plus net cash",
                       "Equity value", "Shares", "Value per share"])
            st.table(bridge)
            w = wacc(x)
            st.caption(f"Cost of equity {pct(w['Cost of equity'])} "
                       f"(risk-free {pct(x.risk_free)} + beta {x.beta:.2f} × ERP "
                       f"{pct(x.erp)}); after-tax cost of debt "
                       f"{pct(w['After-tax cost of debt'])}; WACC {pct(r['WACC'])}.")
        with right:
            st.subheader("What the share price implies")
            st.caption("Each row changes one assumption, holding the rest fixed, "
                       "until the DCF value equals today's price.")
            rev = reverse_dcf(x)
            rev_shown = pd.DataFrame({
                "Current": [(f"{v:+.1%}" if "shift" in k else pct(v))
                            for k, v in rev["Current"].items()],
                "Needed": [("not reachable" if v is None or pd.isna(v)
                            else (f"{v:+.1%}" if "shift" in k else pct(v)))
                           for k, v in rev["Needed to justify price"].items()],
            }, index=rev.index)
            st.table(rev_shown)

        st.subheader("Sensitivity: value per share")
        wv = r["WACC"]
        grid = sensitivity(x, "wacc", np.round(np.arange(wv - 0.01, wv + 0.0101, 0.005), 4),
                           "terminal_growth",
                           np.round(np.arange(tg - 0.01, tg + 0.0101, 0.005), 4))
        heat = go.Figure(go.Heatmap(
            z=grid.values, x=[pct(c) for c in grid.columns], y=[pct(i) for i in grid.index],
            text=[[f"{sym}{v:,.2f}" for v in row] for row in grid.values],
            texttemplate="%{text}", colorscale="RdYlGn", zmid=price,
            colorbar=dict(title="Value")))
        heat.update_layout(xaxis_title="Terminal growth", yaxis_title="WACC",
                           xaxis_type="category", yaxis_type="category",
                           height=380, margin=dict(t=20, b=20))
        st.plotly_chart(heat, width="stretch")
        st.caption(f"Green is above today's price ({sym}{price:,.2f}), red below.")

        with st.expander("All inputs and where they came from"):
            rows = []
            for name, source in sources.items():
                v = getattr(base_inputs, name)
                if v is None:
                    shown_v = "–"
                elif name == "revenue_growth":
                    shown_v = ", ".join(pct(g) for g in v)
                elif name in {"beta", "price"}:
                    shown_v = f"{v:.2f}"
                elif isinstance(v, float) and abs(v) < 1:
                    shown_v = pct(v)
                else:
                    shown_v = millions(v, sym)
                rows.append({"Input": name, "Base case": shown_v, "Source": source})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ----------------------------------------------------------- overview tab
with tabs[0]:
    # The overview always shows my base case; slider changes appear separately
    dcf_value = value(base_inputs)["Value per share"] if base_inputs is not None else None
    scenario_value = value(x)["Value per share"] if x is not None else None
    comps_median = implied["Value per share"].median() if not implied.empty else None

    c1, c2, c3 = st.columns(3)
    c1.metric("Share price", f"{sym}{price:,.2f}")
    if dcf_value is not None:
        c2.metric("DCF value (my base case)", f"{sym}{dcf_value:,.2f}",
                  pct(dcf_value / price - 1))
    if comps_median is not None:
        c3.metric("Comps value (median)", f"{sym}{comps_median:,.2f}",
                  pct(comps_median / price - 1))

    if scenario_value is not None and dcf_value is not None and abs(scenario_value - dcf_value) > 0.005:
        st.info(f"With your changes on the DCF tab, the DCF value is "
                f"{sym}{scenario_value:,.2f} ({pct(scenario_value / price - 1)}).")

    st.subheader("Valuation summary")
    bars = []
    if base_inputs is not None:
        bx = base_inputs
        wv = value(bx)["WACC"]
        g = sensitivity(bx, "wacc", [wv - 0.01, wv + 0.01], "terminal_growth",
                        [bx.terminal_growth - 0.01, bx.terminal_growth + 0.01])
        bars.append(("DCF (WACC ±1%, terminal growth ±1%)",
                     np.nanmin(g.values), np.nanmax(g.values), dcf_value))
    if not implied.empty:
        for k, v in implied["Value per share"].items():
            bars.append((f"Comps: {k}", v, v, v))
    if bars:
        fig = go.Figure()
        for label, lo, hi, mid in bars:
            fig.add_trace(go.Scatter(
                x=[mid], y=[label], mode="markers",
                marker=dict(size=11, color="#1f4e79"),
                error_x=dict(type="data", symmetric=False, array=[hi - mid],
                             arrayminus=[mid - lo], thickness=6, width=0,
                             color="#8fb3d9"),
                showlegend=False,
                hovertemplate=f"{label}<br>{sym}%{{x:,.2f}}<extra></extra>"))
        fig.add_vline(x=price, line_dash="dash", line_color="#c0392b",
                      annotation_text=f"Share price {sym}{price:,.2f}",
                      annotation_position="top")
        fig.update_layout(height=120 + 45 * len(bars), margin=dict(t=40, b=30, l=10),
                          xaxis_title=f"Value per share ({sym})",
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
        st.caption("Each row is one valuation method. The DCF bar shows the range "
                   "across the sensitivity table; comps show each peer median "
                   "multiple applied to this company.")

    flags = trend_flags(compute_ratios(co))
    if flags:
        st.subheader("Things to check")
        for fl in flags:
            st.markdown(f"- {fl}")

# --------------------------------------------------------- financials tab
with tabs[1]:
    ratios = compute_ratios(co)
    st.subheader("Ratio history")
    table = ratios.T.astype(object)
    table.attrs = {}
    for row in table.index:
        f = "{:.1f}x" if row == "Net debt / EBITDA" else "{:.1%}"
        table.loc[row] = ["–" if pd.isna(v) else f.format(v) for v in table.loc[row]]
    table.columns = [str(c) for c in table.columns]
    st.dataframe(table, width="stretch", height=36 * (len(table) + 1) + 3)
    st.caption("Reported figures from the data feed, so they can include one-off "
               "items; the DCF and comps use underlying figures where I've set them. "
               "Ratios over a zero or negative base (e.g. ROE when equity is "
               "negative) are left blank because they aren't meaningful.")

    margins = ratios[["Gross margin", "EBITDA margin", "EBIT margin", "Net margin"]]
    fig = go.Figure()
    for c in margins.columns:
        fig.add_trace(go.Scatter(x=[str(i) for i in margins.index], y=margins[c],
                                 mode="lines+markers", name=c))
    fig.update_layout(yaxis_tickformat=".0%", xaxis_type="category", height=350,
                      margin=dict(t=30),
                      title="Margins", legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")

# -------------------------------------------------------- comparables tab
with tabs[3]:
    if comp_table is None:
        st.info("No peers available.")
    else:
        st.subheader("Trailing multiples")
        shown = comp_table.copy()
        for c in shown.columns[1:]:
            shown[c] = comp_table[c].map(lambda v: "–" if pd.isna(v) else f"{v:.1f}x")
        st.dataframe(shown, width="stretch")
        notes = []
        if overrides:
            notes.append("This company's figures use the same underlying base year as its DCF.")
        for t, mtr in {ticker: target_m, **peers_m}.items():
            if mtr["Adjusted"]:
                notes.append(f"{t}: adjusted figures from company results used for "
                             + ", ".join(mtr["Adjusted"]) + ".")
            for w_ in warnings(mtr):
                notes.append(f"Check {t}: {w_}.")
        for n in notes:
            st.caption(n)

        st.subheader("Implied value from peer medians")
        out = implied.copy()
        out["Peer median"] = implied["Peer median"].map("{:.1f}x".format)
        for c in ["Applied to", "Implied EV", "Implied equity"]:
            out[c] = implied[c].map(lambda v: millions(v, sym))
        out["Value per share"] = implied["Value per share"].map(lambda v: f"{sym}{v:,.2f}")
        out["Upside"] = implied["Upside"].map(lambda v: f"{v:+.1%}")
        st.dataframe(out, width="stretch")

        with st.expander("Figures behind the multiples (millions, own currency)"):
            figs = figures_table(ticker, target_m, peers_m)
            for c in figs.columns[1:]:
                figs[c] = figs[c].map(lambda v: "–" if pd.isna(v) else f"{v:,.0f}")
            st.dataframe(figs, width="stretch")

# ---------------------------------------------------------------- my view
with tabs[4]:
    path = SUMMARY_DIR / f"{ticker}.md"
    if path.exists():
        st.markdown(path.read_text())
    else:
        st.info(f"No written view yet. Add one at summaries/{ticker}.md.")
