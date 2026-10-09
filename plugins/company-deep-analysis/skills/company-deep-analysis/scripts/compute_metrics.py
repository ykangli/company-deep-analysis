#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 3: compute every derived metric the report needs, with reconciliation.

Usage:
    python compute_metrics.py --work ./work

    # when reported net income contains a one-off / investment gain, pass it and
    # a core (adjusted) EPS is computed. Pre-tax amounts, in the statement unit.
    python compute_metrics.py --work ./work --oneoff 2026=135.7 --oneoff 2025=24.6

    python compute_metrics.py --work ./work --wacc 9.5 --terminal 3.0 --years 5

Reads   <work>/metrics_input.json, <work>/price_daily.csv, <work>/price_snapshot.json
Writes  <work>/metrics.txt          human-readable computed metrics
        <work>/reconciliation.txt   pass/fail table (a FAIL must be resolved)

Exit code 2 if reconciliation fails: fix the data before writing the report.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


# ------------------------------------------------------------------ helpers

def year_pairs(series: dict, key: str, years: int):
    """Return [(y0, v0), (y1, v1)] for key over the last `years` fiscal years."""
    s = series.get(key) or {}
    vals = []
    for p, v in s.items():
        try:
            y = int(str(p)[:4])
        except Exception:
            continue
        if v is not None:
            vals.append((y, float(v)))
    vals.sort()
    vals = vals[-years:]
    if len(vals) < 2:
        return None
    return vals[0], vals[-1]


def by_year(series: dict, key: str) -> dict:
    out = {}
    for p, v in (series.get(key) or {}).items():
        try:
            y = int(str(p)[:4])
        except Exception:
            continue
        if v is not None:
            out[y] = float(v)
    return dict(sorted(out.items()))


def latest(series: dict, key: str):
    d = by_year(series, key)
    if not d:
        return None, None
    y = max(d)
    return y, d[y]


def load(work: str):
    with open(os.path.join(work, "metrics_input.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_price(work: str):
    snap_p = os.path.join(work, "price_snapshot.json")
    snap = {}
    if os.path.exists(snap_p):
        with open(snap_p, encoding="utf-8") as fh:
            snap = json.load(fh)
    px, date = None, None
    daily_p = os.path.join(work, "raw", "price_daily.csv")
    if os.path.exists(daily_p):
        try:
            import pandas as pd
            d = pd.read_csv(daily_p)
            d["date"] = pd.to_datetime(d["date"])
            d = d.sort_values("date")
            px = float(d["close"].iloc[-1])
            date = str(d["date"].iloc[-1].date())
        except Exception:
            pass
    return px, date, snap


# ------------------------------------------------------------------ main compute

def compute(work: str, oneoff: dict, wacc: float, term: float, horizon: int,
            price_override, shares_override, fcf0_override, tax_override) -> tuple:
    p = load(work)
    S = p.get("series", {})
    IND = p.get("indicators", {})
    price, pdate, snap = load_price(work)
    if price_override:
        price = float(price_override)
    cur = p.get("currency", "?")
    L = []
    recon = C.Recon()

    L.append("=" * 96)
    L.append(f"COMPUTED METRICS  {p.get('market','?').upper()} / {p.get('symbol','?')}"
             f"   currency={cur}")
    L.append("=" * 96)

    rev = by_year(S, "revenue")
    ni = by_year(S, "net_income")
    op = by_year(S, "operating_income")
    gp = by_year(S, "gross_profit")
    ocf = by_year(S, "ocf")
    capex = by_year(S, "capex")
    equity = by_year(S, "equity")
    assets = by_year(S, "total_assets")
    liab = by_year(S, "total_liabilities")
    divs = by_year(S, "dividends_paid")
    bb = by_year(S, "buyback")
    eps = {k: v for k, v in (IND.get("eps") or {}).items()}
    eps = {int(k): float(v) for k, v in eps.items() if v is not None}

    years = sorted(rev)[-6:]
    if not years:
        return "no revenue series found in metrics_input.json", False

    # ---------------- reconciliation
    L.append("")
    L.append("-" * 96)
    L.append("RECONCILIATION (a FAIL means the data is inconsistent - fix before writing)")
    L.append("-" * 96)
    for y in years[-2:]:
        if y in assets and y in liab and y in equity:
            recon.check(f"{y} assets = liabilities + equity",
                        assets[y], liab[y] + equity[y], tol_pct=0.5)
        if y in op and y in gp:
            pass
    for y in years:
        if y in ni and y in eps:
            implied = ni[y] / eps[y] if eps[y] else None
            if implied:
                L.append(f"  [info] {y} implied diluted shares from NI/EPS = {implied:.3f}"
                         f" (x1e9 if unit is billions)")

    # ---------------- per-year table
    L.append("")
    L.append("-" * 96)
    L.append("ANNUAL SERIES")
    L.append("-" * 96)
    hdr = (f"{'year':<6}{'revenue':>13}{'op_income':>13}{'net_income':>13}"
           f"{'gross_m%':>10}{'op_m%':>9}{'net_m%':>9}")
    L.append(hdr)
    for y in years:
        gm = C.safe_div(gp.get(y), rev.get(y))
        om = C.safe_div(op.get(y), rev.get(y))
        nm = C.safe_div(ni.get(y), rev.get(y))
        L.append(f"{y:<6}{C.fmt(rev.get(y),1):>13}{C.fmt(op.get(y),1):>13}"
                 f"{C.fmt(ni.get(y),1):>13}"
                 f"{(gm*100 if gm else float('nan')):>10.2f}"
                 f"{(om*100 if om else float('nan')):>9.2f}"
                 f"{(nm*100 if nm else float('nan')):>9.2f}")

    # ---------------- ROE
    L.append("")
    L.append("-" * 96)
    L.append("ROE  (net income / average equity; fall back to year-end equity)")
    L.append("-" * 96)
    roe_hist = []
    for y in years:
        if y in ni and y in equity:
            prev = equity.get(y - 1)
            base = (prev + equity[y]) / 2 if prev else equity[y]
            r = C.safe_div(ni[y], base)
            if r:
                roe_hist.append(r * 100)
                L.append(f"  {y}: {r*100:6.2f}%   (NI {C.fmt(ni[y],1)} / avg equity "
                         f"{C.fmt(base,1)})")
    if roe_hist:
        L.append(f"  ---- 5y average: {sum(roe_hist[-5:])/len(roe_hist[-5:]):.2f}%")
    ind_roe = {int(k): v for k, v in (IND.get("roe") or {}).items() if v is not None}
    if ind_roe:
        L.append("  source-reported ROE: "
                 + ", ".join(f"{k}:{v:.2f}" for k, v in sorted(ind_roe.items())[-6:]))

    # ---------------- CAGR
    L.append("")
    L.append("-" * 96)
    L.append("CAGR")
    L.append("-" * 96)
    for label, series in [("revenue", rev), ("operating income", op), ("net income", ni),
                          ("OCF", ocf), ("EPS", {k: v for k, v in eps.items()})]:
        for n in (3, 5, 6):
            pr = year_pairs({"x": series}, "x", n + 1)
            if not pr:
                continue
            (y0, v0), (y1, v1) = pr
            span = y1 and (y1 - y0)
            if span <= 0:
                continue
            L.append(f"  {label:<18} {y0}->{y1} ({span}y): {C.fmt(C.cagr(v0, v1, span),2):>8}%"
                     f"   [{C.fmt(v0,2)} -> {C.fmt(v1,2)}]")

    # ---------------- FCF
    L.append("")
    L.append("-" * 96)
    L.append("FREE CASH FLOW  (OCF - capex; capex taken as magnitude)")
    L.append("-" * 96)
    fcf = {}
    for y in years:
        if y in ocf and y in capex:
            fcf[y] = ocf[y] - abs(capex[y])
            ratio = C.safe_div(fcf[y], ni.get(y))
            L.append(f"  {y}: OCF {C.fmt(ocf[y],2):>9}  capex {C.fmt(abs(capex[y]),2):>9}"
                     f"  FCF {C.fmt(fcf[y],2):>10}  FCF_margin "
                     f"{C.fmt(C.safe_div(fcf[y], rev.get(y))*100 if rev.get(y) else None,1):>6}%"
                     f"  FCF/NI {C.fmt(ratio*100 if ratio else None,0):>5}%")
    if fcf:
        pr = year_pairs({"x": fcf}, "x", 6)
        if pr:
            (y0, v0), (y1, v1) = pr
            L.append(f"  FCF CAGR {y0}->{y1}: {C.fmt(C.cagr(v0, v1, y1-y0),2)}%"
                     "   <-- if far below net-income CAGR, capex is eating the profit")

    # ---------------- share count
    L.append("")
    L.append("-" * 96)
    L.append("IMPLIED DILUTED SHARES (net income / EPS) - shows real buyback effect")
    L.append("-" * 96)
    sc = {}
    for y in years:
        if y in ni and y in eps and eps[y]:
            sc[y] = ni[y] / eps[y]
            L.append(f"  {y}: {sc[y]:.3f}")
    if len(sc) >= 2:
        ks = sorted(sc)
        chg = (sc[ks[-1]] / sc[ks[0]] - 1) * 100
        L.append(f"  {ks[0]} -> {ks[-1]}: {chg:+.2f}%  "
                 f"(negative = net buyback; positive = net dilution)")

    # ---------------- core earnings
    L.append("")
    L.append("-" * 96)
    L.append("CORE (ADJUSTED) EARNINGS - strip one-off / investment gains")
    L.append("-" * 96)
    if not oneoff:
        L.append("  no --oneoff supplied. If reported net income contains fair-value")
        L.append("  gains, disposal gains or similar, RE-RUN with --oneoff YEAR=PRETAX.")
    tax = None
    ind_tax = {}
    pretax = by_year(S, "pretax_income")
    taxpaid = by_year(S, "income_tax")
    for y in years:
        if y in pretax and y in taxpaid and pretax[y]:
            ind_tax[y] = taxpaid[y] / pretax[y]
    if ind_tax:
        L.append("  effective tax rate by year: "
                 + ", ".join(f"{k}:{v*100:.1f}%" for k, v in sorted(ind_tax.items())))
        if tax_override is not None:
            tax = tax_override
            L.append(f"  tax rate OVERRIDE supplied: {tax*100:.2f}%")
        else:
            # The latest year's rate is the best forward-looking proxy; the
            # multi-year average is shown for reference only.
            tax = ind_tax[max(ind_tax)]
            L.append(f"  tax rate used: {tax*100:.2f}% (latest year); "
                     f"multi-year average {sum(ind_tax.values())/len(ind_tax)*100:.2f}%")
    core = {}
    for y in years:
        oo = oneoff.get(str(y)) or oneoff.get(y)
        if oo is None or y not in ni or tax is None:
            continue
        c = ni[y] - oo * (1 - tax)
        core[y] = c
        eps_c = c / sc[y] if sc.get(y) else None
        L.append(f"  {y}: reported NI {C.fmt(ni[y],1)}  one-off(pretax) {C.fmt(oo,1)}"
                 f"  -> core NI {C.fmt(c,1)}  core EPS {C.fmt(eps_c,3)}")
    if core and price:
        y = max(core)
        # scale: unit may be 1e9 (us) or 1.0 (cn/hk)
        unit = p.get("unit", 1.0)
        core_eps_abs = (core[y] * unit) / (sc[y] * unit) if sc.get(y) else None
        if core_eps_abs:
            L.append(f"  {y} core P/E at {price}: {price/core_eps_abs:.2f}x")
        if y in eps:
            L.append(f"  {y} REPORTED P/E at {price}: {price/eps[y]:.2f}x"
                     "   <-- the misleading one")

    # ---------------- valuation
    unit = p.get("unit", 1.0)
    L.append("")
    L.append("-" * 96)
    L.append("VALUATION")
    L.append("-" * 96)
    shares = shares_override or snap.get("em_implied_shares")
    if not shares and sc:
        # Fall back to the implied diluted share count from the latest year.
        shares = sc[max(sc)] * unit
        L.append(f"  [info] share count derived from net income / EPS "
                 f"({max(sc)}): {C.fmt(shares/unit,4)} (x unit)")
    if shares:
        shares = float(shares)
    mcap = None
    if snap.get("em_market_cap"):
        mcap = float(snap["em_market_cap"])
    elif price and shares:
        mcap = price * shares
    L.append(f"  price={C.fmt(price,2)}  as_of={pdate}  shares={C.fmt(shares,4)}")
    L.append(f"  market cap = {C.fmt(mcap,2)}")
    y_last = max(ni) if ni else None
    if mcap and y_last and ni.get(y_last):
        ni_abs = ni[y_last] * unit
        L.append(f"  static P/E ({y_last}) = {mcap/ni_abs:.2f}x")
    if mcap and rev and y_last:
        L.append(f"  P/S ({y_last}) = {mcap/(rev[y_last]*unit):.2f}x")
    if mcap and equity and y_last:
        L.append(f"  P/B ({y_last}) = {mcap/(equity[y_last]*unit):.2f}x")
    if mcap and fcf and y_last and fcf.get(y_last):
        L.append(f"  FCF yield ({y_last}) = {fcf[y_last]*unit/mcap*100:.2f}%")
    if mcap and y_last:
        d = divs.get(y_last, 0) or 0
        b = bb.get(y_last, 0) or 0
        L.append(f"  shareholder return ({y_last}) = "
                 f"{(d+b)*unit/mcap*100:.2f}%   (buyback {C.fmt(b,2)} + div {C.fmt(d,2)})")

    # ---------------- PE band
    L.append("")
    L.append("-" * 96)
    L.append("HISTORICAL P/E BAND (price range per year vs that year's EPS)")
    L.append("-" * 96)
    band = pe_band(work, eps)
    L.extend(band)

    # ---------------- DCF + reverse DCF
    L.append("")
    L.append("-" * 96)
    L.append(f"DCF  (WACC {wacc}%, terminal growth {term}%, horizon {horizon}y)")
    L.append("-" * 96)
    if fcf:
        base_fcf = fcf0_override if fcf0_override else fcf[max(fcf)] * unit
        tag = "SUPPLIED" if fcf0_override else "latest reported"
        L.append(f"  starting FCF ({tag}) = {C.fmt(base_fcf,0)}")
        if base_fcf <= 0:
            L.append("  [WARN] starting FCF is NEGATIVE. Do NOT start the DCF here.")
            L.append("         Supply --fcf0 with a normalised steady-state FCF, or")
            L.append("         rely on the reverse DCF below as the primary method.")
        elif not fcf0_override:
            L.append("  [NOTE] a depressed capex-cycle FCF will understate the DCF.")
            L.append("         Re-run with --fcf0 <normalised FCF> and say so in the report.")
        for label, g in [("pessimistic", 0.04), ("neutral", 0.10), ("optimistic", 0.15)]:
            v = dcf(abs(base_fcf), g, horizon, term / 100, wacc / 100)
            per = v / shares if shares else None
            L.append(f"  {label:<12} g={g*100:.0f}%  ->  equity {C.fmt(v,0)}"
                     f"   per share {C.fmt(per,2)}")
    if mcap:
        implied = mcap * (wacc / 100 - term / 100)
        L.append("")
        L.append(f"  REVERSE DCF: at market cap {C.fmt(mcap,0)}, WACC {wacc}%, "
                 f"terminal {term}%,")
        L.append(f"  the market is implying steady-state FCF of about "
                 f"{C.fmt(implied,0)}")
        if fcf and unit:
            lf = fcf[max(fcf)] * unit
            if lf and lf > 0:
                L.append(f"  = {implied/lf:.2f}x the latest reported FCF "
                         f"({C.fmt(lf,0)}).  Ask: is that achievable, and how?")
            if core:
                cy = max(core)
                cn = core[cy] * unit
                if cn:
                    L.append(f"  = {implied/cn:.2f}x the {cy} core net income "
                             f"({C.fmt(cn,0)})")
        L.append("  Write this into the report: it states what the price already assumes.")

    # ---------------- scenario table
    L.append("")
    L.append("-" * 96)
    L.append("SCENARIO SHEET (fill the assumptions yourself; values are placeholders)")
    L.append("-" * 96)
    L.append("  For each scenario state: probability, revenue path, core EPS path,")
    L.append("  capex path, steady-state FCF, fair P/E range, target price, annualised")
    L.append("  return from today's price. Probabilities must sum to 100%.")
    if price:
        for label, target in [("pessimistic", 0.7), ("neutral", 1.2), ("optimistic", 1.8)]:
            t = price * target
            L.append(f"  {label:<12} price x{target:.1f} -> {C.fmt(t,2)}  "
                     f"({(target-1)*100:+.0f}%)")
    return "\n".join(L), not recon.failures(), recon


def dcf(fcf0: float, g: float, years: int, g_term: float, wacc: float) -> float:
    v, f = 0.0, fcf0
    for t in range(1, years + 1):
        f *= (1 + g)
        v += f / (1 + wacc) ** t
    tv = f * (1 + g_term) / (wacc - g_term) if wacc > g_term else 0.0
    return v + tv / (1 + wacc) ** years


def pe_band(work: str, eps: dict) -> list:
    import pandas as pd
    out = []
    p = os.path.join(work, "raw", "price_daily.csv")
    if not os.path.exists(p) or not eps:
        return ["  n/a - need both price_daily.csv and EPS series"]
    d = pd.read_csv(p)
    d["date"] = pd.to_datetime(d["date"])
    for y in sorted(eps)[-6:]:
        s = d[d["date"].dt.year == y]
        if s.empty:
            continue
        out.append(f"  {y}: price {s['low'].min():>9.2f} - {s['high'].max():>9.2f}"
                   f"   static P/E vs {y} EPS({eps[y]:.2f}): "
                   f"{s['low'].min()/eps[y]:>7.1f}x - {s['high'].max()/eps[y]:>7.1f}x")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute report metrics")
    ap.add_argument("--work", default="./work")
    ap.add_argument("--out", default=None)
    ap.add_argument("--oneoff", action="append", default=[],
                    help="YEAR=PRETAX_AMOUNT, repeatable")
    ap.add_argument("--price", type=float, default=None)
    ap.add_argument("--shares", type=float, default=None,
                    help="total shares OUTSTANDING (same unit as the statements)")
    ap.add_argument("--fcf0", type=float, default=None,
                    help="normalised starting FCF for the DCF (absolute currency)")
    ap.add_argument("--tax-rate", type=float, default=None,
                    help="override effective tax rate, e.g. 0.168 for 16.8%%")
    ap.add_argument("--wacc", type=float, default=9.5)
    ap.add_argument("--terminal", type=float, default=3.0)
    ap.add_argument("--years", type=int, default=5)
    args = ap.parse_args()

    C.setup_console()

    C.require("pandas")
    oneoff = {}
    for spec in args.oneoff:
        if "=" in spec:
            k, v = spec.split("=", 1)
            try:
                oneoff[k.strip()] = float(v)
            except ValueError:
                C.log(f"[WARN] bad --oneoff {spec}")

    text, ok, recon = compute(args.work, oneoff, args.wacc, args.terminal,
                              args.years, args.price, args.shares, args.fcf0,
                              args.tax_rate)
    C.log(text)
    outp = args.out or os.path.join(args.work, "metrics.txt")
    with open(outp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    with open(os.path.join(args.work, "reconciliation.txt"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(recon.report())
    C.log("")
    C.log(f"wrote {outp}")
    if not ok:
        C.log("")
        C.log("[FAIL] reconciliation failed. Fix the data before writing the report.")
        C.log("       See reconciliation.txt")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
