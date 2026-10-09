#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 0 preflight: confirm the environment and that data actually flows.

Usage:
    python preflight.py --market us --symbol GOOGL
    python preflight.py --market cn --symbol 603986
    python preflight.py --market hk --symbol 00700

Exit code 0 = ready to analyse. Non-zero = fix the environment first; do NOT
write a report from memory.
"""
from __future__ import annotations

import argparse
import os
import sys
import platform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402


def check_python() -> bool:
    C.log(f"Python      : {sys.version.split()[0]}  ({platform.system()} {platform.release()})")
    ok = sys.version_info >= (3, 9)
    C.log(f"  [{'OK' if ok else 'FAIL'}] version >= 3.9")
    return ok


def check_libs() -> dict:
    libs = {}
    for name in ("pandas", "requests", "akshare", "bs4", "lxml"):
        try:
            mod = __import__(name)
            ver = getattr(mod, "__version__", "?")
            libs[name] = ver
            C.log(f"  [OK]   {name:<10} {ver}")
        except Exception as exc:  # noqa: BLE001
            libs[name] = None
            C.log(f"  [FAIL] {name:<10} {type(exc).__name__}: {exc}")
    return libs


def check_net() -> bool:
    import requests
    targets = [
        ("Yahoo Finance", "https://query2.finance.yahoo.com/v8/finance/chart/GOOGL?range=5d&interval=1d"),
        ("SEC EDGAR", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001652044&type=8-K&count=1"),
        ("Eastmoney", "https://push2.eastmoney.com/api/qt/stock/get?secid=105.GOOGL&fields=f43&invt=2&fltt=2"),
        ("Sina Finance", "https://hq.sinajs.cn/list=sh603986"),
    ]
    any_ok = False
    for name, url in targets:
        ok, _ = C.retry(
            lambda u=url: requests.get(
                u, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
                timeout=15),
            tries=2, delay=2.0, quiet=True)
        C.log(f"  [{'OK' if ok else '--'}] {name}")
        any_ok = any_ok or ok
    return any_ok


def check_market(market: str, symbol: str) -> bool:
    import akshare as ak
    C.log("")
    C.log(f"Market probe: {market.upper()} / {symbol}")
    ok_any = False

    if market == "us":
        ok, df = C.retry(lambda: ak.stock_financial_us_report_em(
            stock=symbol, symbol="资产负债表", indicator="年报"), tries=2, quiet=True)
        if ok and df is not None and not df.empty:
            C.log(f"  [OK]   US balance sheet: {df.shape[0]} rows, "
                  f"{df['REPORT'].nunique()} periods")
            ok_any = True
        else:
            C.log("  [FAIL] US balance sheet not reachable")

        ok2, df2 = C.retry(lambda: ak.stock_financial_us_analysis_indicator_em(
            symbol=symbol, indicator="年报"), tries=2, quiet=True)
        C.log(f"  [{'OK' if ok2 else 'FAIL'}] US indicators")

        ok3, df3 = C.retry(lambda: ak.stock_us_daily(symbol=symbol), tries=2, quiet=True)
        if ok3 and df3 is not None and not df3.empty:
            C.log(f"  [OK]   US price series: {len(df3)} rows, "
                  f"{df3['date'].iloc[0]} .. {df3['date'].iloc[-1]}")
            ok_any = True

    elif market == "cn":
        ok, df = C.retry(lambda: ak.stock_financial_abstract(symbol=symbol), tries=2, quiet=True)
        if ok and df is not None and not df.empty:
            C.log(f"  [OK]   CN financial abstract: {df.shape}")
            ok_any = True
        ok2, df2 = C.retry(lambda: ak.stock_financial_analysis_indicator(
            symbol=symbol, start_year="2019"), tries=2, quiet=True)
        C.log(f"  [{'OK' if ok2 else 'FAIL'}] CN analysis indicators")
        # price: three-tier fallback
        pre = "sh" if str(symbol).startswith(("6", "9")) else "sz"
        name, px = C.first_ok([
            ("sina_daily", lambda: ak.stock_zh_a_daily(symbol=pre + str(symbol), adjust="qfq")),
            ("em_hist", lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")),
            ("tx_hist", lambda: ak.stock_zh_a_hist_tx(symbol=pre + str(symbol), adjust="qfq")),
        ], label="CN price")
        if px is not None:
            C.log(f"         rows={len(px)}, last={px.iloc[-1].to_dict()}")
            ok_any = True

    elif market == "hk":
        sym = str(symbol).zfill(5)
        ok, df = C.retry(lambda: ak.stock_financial_hk_analysis_indicator_em(
            symbol=sym, indicator="年度"), tries=2, quiet=True)
        if ok and df is not None and not df.empty:
            C.log(f"  [OK]   HK indicators: {df.shape}")
            ok_any = True
        name, px = C.first_ok([
            ("sina_hk_daily", lambda: ak.stock_hk_daily(symbol=sym)),
            ("em_hk_hist", lambda: ak.stock_hk_hist(symbol=sym, period="daily", adjust="qfq")),
        ], label="HK price")
        if px is not None:
            C.log(f"         rows={len(px)}")
            ok_any = True
    else:
        C.log(f"  [FAIL] unknown market {market}")

    return ok_any


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight for company-deep-analysis")
    ap.add_argument("--market", required=True, choices=["us", "cn", "hk"])
    ap.add_argument("--symbol", required=True)
    args = ap.parse_args()

    C.setup_console()

    C.require("requests", "pandas", "akshare")
    C.head("PREFLIGHT - environment and data reachability")

    C.log("Environment")
    py_ok = check_python()
    C.log("Libraries")
    libs = check_libs()
    C.log("Network")
    net_ok = check_net()
    mkt_ok = check_market(args.market, args.symbol)

    C.head("VERDICT")
    C.log(f"  python            : {'OK' if py_ok else 'FAIL'}")
    C.log(f"  core libraries    : {'OK' if all(libs.get(k) for k in ('pandas','requests','akshare')) else 'FAIL'}")
    C.log(f"  network (any)     : {'OK' if net_ok else 'FAIL'}")
    C.log(f"  market data       : {'OK' if mkt_ok else 'FAIL'}")

    if py_ok and mkt_ok:
        C.log("\n  => READY. Proceed to Phase 1 (read the checklist and the example report).")
        return 0
    C.log("\n  => NOT READY. Fix the failures above before gathering data.")
    C.log("     Do NOT write a report from memory. Partial fallback sources are")
    C.log("     acceptable for price data, but financial statements are mandatory.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
