#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 2a: fetch 5+ fiscal years of financial statements and normalise them.

Usage:
    python fetch_financials.py --market us --symbol GOOGL --out ./work
    python fetch_financials.py --market cn --symbol 603986 --out ./work
    python fetch_financials.py --market hk --symbol 00700  --out ./work

Writes into <out>/:
    raw/*.csv            raw statement frames, untouched
    financials_dump.txt  human-readable multi-period dump (read this while writing)
    metrics_input.json   normalised series for compute_metrics.py

Contract: never invent a value. A series that cannot be mapped is written as
null and reported in the "unmapped" list so the report can say 未能核实.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


# ------------------------------------------------------------------ synonym maps

# item name (any of the aliases) -> normalised key
US_INCOME = {
    "revenue": ["营业收入", "主营收入", "总收入"],
    "cost_of_revenue": ["营业成本", "主营成本"],
    "gross_profit": ["毛利"],
    "operating_income": ["营业利润", "经营利润"],
    "net_income": ["净利润", "归属于母公司股东净利润", "归属于普通股股东净利润"],
    "pretax_income": ["持续经营税前利润", "税前利润"],
    "income_tax": ["所得税"],
    "rd_expense": ["研发费用"],
    "sga_expense": ["营业费用", "销售及管理费用"],
    "marketing_expense": ["营销费用"],
    "g_and_a": ["一般及行政费用"],
    "other_income": ["其他收入(支出)"],
}
US_BALANCE = {
    "total_assets": ["总资产"],
    "total_liabilities": ["总负债"],
    "equity": ["归属于母公司股东权益", "股东权益合计"],
    "cash": ["现金及现金等价物"],
    "marketable_securities_current": ["有价证券投资(流动)"],
    "marketable_securities_noncurrent": ["有价证券投资(非流动)"],
    "long_term_debt": ["长期负债"],
    "goodwill": ["商誉"],
    "ppe": ["物业、厂房及设备"],
    "inventory": ["存货"],
    "receivables": ["应收账款"],
    "current_liabilities": ["流动负债合计"],
    "current_assets": ["流动资产合计"],
}
US_CASHFLOW = {
    "ocf": ["经营活动产生的现金流量净额"],
    "capex": ["购买固定资产", "购建固定资产"],
    "buyback": ["回购股份"],
    "dividends_paid": ["股息支付"],
    "depreciation": ["折旧及摊销"],
    "debt_issued": ["发行债券"],
    "debt_repaid": ["赎回债券"],
    "icf": ["投资活动产生的现金流量净额"],
    "fcf_financing": ["筹资活动产生的现金流量净额"],
    "equity_securities_gain": ["权益性投资损益"],
    "sbc": ["基于股票的补偿费"],
}

US_INDICATOR = {
    "revenue": "OPERATE_INCOME",
    "gross_margin": "GROSS_PROFIT_RATIO",
    "net_margin": "NET_PROFIT_RATIO",
    "net_income": "PARENT_HOLDER_NETPROFIT",
    "eps": "DILUTED_EPS",
    "eps_basic": "BASIC_EPS",
    "roe": "ROE_AVG",
    "roa": "ROA",
    "debt_ratio": "DEBT_ASSET_RATIO",
    "current_ratio": "CURRENT_RATIO",
}


def pick(series_map: dict, aliases: list):
    for a in aliases:
        if a in series_map and series_map[a] is not None:
            return series_map[a]
    return None


def period_to_year(rep: str):
    """'2025/FY' -> 2025 ; '2026/Q2' -> (2026, 2)"""
    m = re.match(r"(\d{4})/(FY|Q\d)", str(rep))
    if not m:
        return None
    y = int(m.group(1))
    if m.group(2) == "FY":
        return (y, 0)
    return (y, int(m.group(2)[1:]))


# ------------------------------------------------------------------ US

def fetch_us(symbol: str, out: C.Out):
    import akshare as ak

    raw = {}
    for sym_name, key in [("资产负债表", "balance"),
                          ("综合损益表", "income"),
                          ("现金流量表", "cashflow")]:
        for ind, tag in [("年报", "A"), ("单季报", "Q")]:
            ok, df = C.retry(lambda s=sym_name, i=ind: ak.stock_financial_us_report_em(
                stock=symbol, symbol=s, indicator=i), tries=3, label=f"{sym_name}-{ind}")
            if ok and df is not None and not df.empty:
                out.write_csv(f"{key}_{tag}.csv", df)
                raw[f"{key}_{tag}"] = df
                C.log(f"  {sym_name}-{ind}: {df.shape[0]} rows")

    for ind, tag in [("年报", "A"), ("单季报", "Q")]:
        ok, df = C.retry(lambda i=ind: ak.stock_financial_us_analysis_indicator_em(
            symbol=symbol, indicator=i), tries=3, label=f"indicator-{ind}")
        if ok and df is not None and not df.empty:
            df = df.copy()
            df["REPORT_DATE"] = df["REPORT_DATE"].astype(str)
            out.write_csv(f"indicator_{tag}.csv", df)
            raw[f"indicator_{tag}"] = df
            C.log(f"  indicator-{ind}: {df.shape[0]} rows")

    if not raw:
        return None, None, "US financial statements unreachable"

    series = {}
    periods = []

    for key, alias_map in [("income", US_INCOME), ("balance", US_BALANCE),
                           ("cashflow", US_CASHFLOW)]:
        df = raw.get(f"{key}_A")
        if df is None:
            continue
        df = df[df["REPORT"].astype(str).str.contains("/FY", na=False)]
        for rep in df["REPORT"].unique():
            periods.append(str(rep))
        piv = df.pivot_table(index="ITEM_NAME", columns="REPORT", values="AMOUNT",
                             aggfunc="first")
        by_item = {k: {str(c): (None if v != v else float(v)) for c, v in row.items()}
                   for k, row in piv.iterrows()}
        for norm, aliases in alias_map.items():
            got = None
            for a in aliases:
                if a in by_item:
                    got = by_item[a]
                    break
            series[norm] = got

    periods = sorted(set(periods), key=lambda r: period_to_year(r) or (0, 0))
    years = [period_to_year(p)[0] for p in periods]

    # indicator series (same period labels)
    ind_A = raw.get("indicator_A")
    ind_series = {}
    if ind_A is not None:
        ind_A = ind_A.copy()
        for norm, col in US_INDICATOR.items():
            if col in ind_A.columns:
                m = {}
                for _, row in ind_A.iterrows():
                    y = str(row["REPORT_DATE"])[:4]
                    val = row.get(col)
                    try:
                        val = float(val)
                        if val != val:
                            val = None
                    except Exception:
                        val = None
                    m[y] = val
                ind_series[norm] = m

    q_eps = {}
    ind_Q = raw.get("indicator_Q")
    if ind_Q is not None and "DILUTED_EPS" in ind_Q.columns:
        for _, row in ind_Q.iterrows():
            q_eps[str(row["REPORT_DATE"])[:10]] = row.get("DILUTED_EPS")

    payload = {
        "market": "us", "symbol": symbol, "currency": "USD", "unit": 1e9,
        "unit_note": "all statement values divided by 1e9 (billions)",
        "sign_note": "capex / buyback / dividends_paid / debt_repaid are stored as "
                     "POSITIVE magnitudes (outflows); icf / fcf_financing keep their "
                     "reported sign (net flows)",
        "periods": periods, "years": years,
        "series": {k: (None if v is None else {p: (None if x is None else x / 1e9)
                                               for p, x in v.items()})
                   for k, v in series.items()},
        "indicators": ind_series,
        "quarterly_eps": q_eps,
    }
    _normalise_outflow_signs(payload["series"])
    return payload, raw, None


OUTFLOW_KEYS = ("capex", "buyback", "dividends_paid", "debt_repaid")


def _normalise_outflow_signs(series: dict) -> None:
    """Statement data stores outflows as negatives; reports show magnitudes."""
    for key in OUTFLOW_KEYS:
        m = series.get(key)
        if not m:
            continue
        series[key] = {k: (None if v is None else abs(v)) for k, v in m.items()}


# ------------------------------------------------------------------ CN

CN_ABSTRACT_KEYS = {
    "revenue": ["营业总收入", "营业收入"],
    "net_income": ["归母净利润", "净利润"],
    "deducted_net_income": ["扣非净利润", "扣除非经常性损益后的净利润"],
    "ocf": ["经营活动产生的现金流量净额", "经营现金流量净额"],
    "eps": ["基本每股收益", "摊薄每股收益"],
    "bps": ["每股净资产"],
    "roe": ["净资产收益率", "净资产收益率(加权)", "加权净资产收益率"],
    "gross_margin": ["销售毛利率", "毛利率"],
    "net_margin": ["销售净利率", "净利率"],
    "total_assets": ["总资产"],
    "equity": ["股东权益合计", "归属于母公司股东权益合计"],
}


def fetch_cn(symbol: str, out: C.Out):
    import akshare as ak

    raw = {}
    ok, abstract = C.retry(lambda: ak.stock_financial_abstract(symbol=symbol),
                           tries=3, label="financial_abstract")
    if ok and abstract is not None and not abstract.empty:
        out.write_csv("cn_abstract.csv", abstract)
        raw["abstract"] = abstract
        C.log(f"  abstract: {abstract.shape}")

    ok, ind = C.retry(lambda: ak.stock_financial_analysis_indicator(
        symbol=symbol, start_year="2019"), tries=3, label="analysis_indicator")
    if ok and ind is not None and not ind.empty:
        out.write_csv("cn_indicator.csv", ind)
        raw["indicator"] = ind
        C.log(f"  indicator: {ind.shape}")

    for stmt in ["资产负债表", "利润表", "现金流量表"]:
        ok, df = C.retry(lambda s=stmt: ak.stock_financial_report_sina(
            stock=("sh" if str(symbol).startswith("6") else "sz") + str(symbol),
            symbol=s), tries=2, label=f"sina-{stmt}")
        if ok and df is not None and not df.empty:
            out.write_csv(f"cn_{stmt}.csv", df)
            raw[stmt] = df
            C.log(f"  {stmt}: {df.shape}")

    if not raw:
        return None, None, "CN financial statements unreachable"

    series = {}
    interim = {}
    periods = []
    interim_periods = []
    if "abstract" in raw:
        ab = raw["abstract"]
        date_cols = [c for c in ab.columns if re.fullmatch(r"\d{8}", str(c))]
        # Annual and interim periods MUST be separated: mixing 20260630 into an
        # annual series silently corrupts every CAGR and margin calculation.
        annual_cols = sorted(c for c in date_cols if str(c).endswith("1231"))
        half_cols = sorted(c for c in date_cols if not str(c).endswith("1231"))
        periods = annual_cols
        interim_periods = half_cols
        for norm, names in CN_ABSTRACT_KEYS.items():
            for nm in names:
                hit = ab[ab["指标"].astype(str).str.strip() == nm]
                if not hit.empty:
                    row = hit.iloc[0]
                    series[norm] = {c: _num(row.get(c)) for c in annual_cols}
                    interim[norm] = {c: _num(row.get(c)) for c in half_cols}
                    break

    payload = {
        "market": "cn", "symbol": symbol, "currency": "CNY", "unit": 1.0,
        "unit_note": "CNY as reported (yuan); 'series' holds ANNUAL periods only",
        "periods": periods, "years": [int(p[:4]) for p in periods],
        "series": series,
        "interim": interim,
        "interim_periods": interim_periods,
        "indicators": {},
        "quarterly_eps": {},
    }
    return payload, raw, None


def _num(v):
    try:
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


# ------------------------------------------------------------------ HK

HK_KEYS = {
    "revenue": ["OPERATE_INCOME"],
    "net_income": ["HOLDER_PROFIT"],
    "eps": ["DILUTED_EPS", "BASIC_EPS"],
    "bps": ["BPS"],
    "roe": ["ROE_AVG"],
    "gross_margin": ["GROSS_PROFIT_RATIO"],
    "net_margin": ["NET_PROFIT_RATIO"],
    "gross_profit": ["GROSS_PROFIT"],
    "ocf_per_share": ["PER_NETCASH_OPERATE"],
}


def fetch_hk(symbol: str, out: C.Out):
    import akshare as ak

    sym = str(symbol).zfill(5)
    raw = {}
    for ind, tag in [("年度", "A"), ("报告期", "Q")]:
        ok, df = C.retry(lambda i=ind: ak.stock_financial_hk_analysis_indicator_em(
            symbol=sym, indicator=i), tries=2, label=f"hk-indicator-{ind}")
        if ok and df is not None and not df.empty:
            out.write_csv(f"hk_indicator_{tag}.csv", df)
            raw[f"indicator_{tag}"] = df
            C.log(f"  indicator-{ind}: {df.shape}")

    for stmt in ["资产负债表", "利润表", "现金流量表"]:
        ok, df = C.retry(lambda s=stmt: ak.stock_financial_hk_report_em(
            stock=sym, symbol=s, indicator="年度"), tries=2, label=f"hk-{stmt}")
        if ok and df is not None and not df.empty:
            out.write_csv(f"hk_{stmt}.csv", df)
            raw[stmt] = df
            C.log(f"  {stmt}: {df.shape}")

    if not raw:
        return None, None, "HK financial statements unreachable"

    series = {}
    periods = []
    ind = raw.get("indicator_A")
    if ind is not None:
        for _, row in ind.iterrows():
            p = str(row.get("REPORT_DATE", ""))[:10]
            if p:
                periods.append(p)
        periods = sorted(set(periods))
        for norm, cols in HK_KEYS.items():
            for col in cols:
                if col in ind.columns:
                    series[norm] = {str(r["REPORT_DATE"])[:10]: _num(r.get(col))
                                    for _, r in ind.iterrows()}
                    break

    payload = {
        "market": "hk", "symbol": sym, "currency": "REPORTED (verify: HKD/CNY/USD)",
        "unit": 1.0,
        "unit_note": "as reported; CHECK the reporting currency and state it in the report",
        "periods": periods, "years": [int(p[:4]) for p in periods],
        "series": series, "indicators": {}, "quarterly_eps": {},
    }
    return payload, raw, None


# ------------------------------------------------------------------ dump

def dump(payload: dict) -> str:
    lines = []
    lines.append(f"market={payload['market']} symbol={payload['symbol']} "
                 f"currency={payload['currency']}")
    lines.append(f"note: {payload['unit_note']}")
    lines.append("")
    years = payload.get("years", [])
    lines.append("PERIODS: " + ", ".join(map(str, payload.get("periods", []))))
    lines.append("")

    def row(label, mapping):
        if not mapping:
            return None
        vals = []
        for p in payload.get("periods", []):
            v = mapping.get(p)
            if v is None:
                v = mapping.get(str(p)[:10])
            if v is None and re.fullmatch(r"\d{4}", str(p)):
                for k, vv in mapping.items():
                    if str(k).startswith(str(p)):
                        v = vv
                        break
            vals.append(C.fmt(v, 3, dash="  n/a"))
        return f"{label:<28} " + " | ".join(f"{x:>12}" for x in vals)

    lines.append("-" * 100)
    lines.append("NORMALISED SERIES (annual)")
    lines.append("-" * 100)
    for k, v in payload.get("series", {}).items():
        r = row(k, v)
        if r:
            lines.append(r)

    if payload.get("indicators"):
        RATIO_KEYS = {"gross_margin", "net_margin", "roe", "roa", "debt_ratio",
                      "current_ratio"}
        ratio_ind = {k: v for k, v in payload["indicators"].items()
                     if k in RATIO_KEYS and v}
        if ratio_ind:
            lines.append("")
            lines.append("-" * 100)
            lines.append("INDICATORS (%)")
            lines.append("-" * 100)
            for k, v in ratio_ind.items():
                ks = sorted(v.keys())
                lines.append(f"{k:<28} " + " | ".join(f"{kk}:{C.fmt(v[kk],2)}" for kk in ks))

    if payload.get("quarterly_eps"):
        lines.append("")
        lines.append("-" * 100)
        lines.append("QUARTERLY DILUTED EPS (for TTM and PE bands)")
        lines.append("-" * 100)
        for k in sorted(payload["quarterly_eps"].keys()):
            lines.append(f"  {k}  {C.fmt(payload['quarterly_eps'][k], 3)}")

    missing = [k for k, v in payload.get("series", {}).items() if not v]
    if missing:
        lines.append("")
        lines.append("UNMAPPED / MISSING (write 未能核实 in the report): "
                     + ", ".join(missing))

    interim = payload.get("interim") or {}
    iper = payload.get("interim_periods") or []
    if interim and iper:
        lines.append("")
        lines.append("-" * 100)
        lines.append("LATEST INTERIM PERIODS (keep separate from the annual series)")
        lines.append("-" * 100)
        show = iper[-6:]
        lines.append(f"{'metric':<24} " + " | ".join(f"{p:>14}" for p in show))
        for k, m in interim.items():
            vals = [C.fmt(m.get(p), 3, dash="n/a") for p in show]
            if any(v != "n/a" for v in vals):
                lines.append(f"{k:<24} " + " | ".join(f"{v:>14}" for v in vals))
    return "\n".join(lines)


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch financial statements")
    ap.add_argument("--market", required=True, choices=["us", "cn", "hk"])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--out", default="./work")
    args = ap.parse_args()

    C.setup_console()

    C.require("pandas", "akshare")
    C.head(f"FETCH FINANCIALS  {args.market.upper()} / {args.symbol}")
    out = C.Out(args.out)

    fn = {"us": fetch_us, "cn": fetch_cn, "hk": fetch_hk}[args.market]
    payload, raw, err = fn(args.symbol, out)

    if err:
        C.log(f"\n[ABORT] {err}")
        return 2

    out.write_json("metrics_input.json", payload)
    text = dump(payload)
    out.write_text("financials_dump.txt", text)
    C.log("")
    C.log(text)
    C.log("")
    C.log(f"wrote {os.path.join(out.root, 'financials_dump.txt')}")
    C.log(f"wrote {os.path.join(out.root, 'metrics_input.json')}")
    n_periods = len(payload.get("periods", []))
    if n_periods < 5:
        C.log(f"\n[WARN] only {n_periods} annual periods found; "
              f"the report requires at least 5 fiscal years.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
