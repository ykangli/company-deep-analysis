#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 2b: fetch price history, dividends, splits and derive price statistics.

Usage:
    python fetch_price_dividends.py --market us --symbol GOOGL --out ./work
    python fetch_price_dividends.py --market cn --symbol 603986 --out ./work
    python fetch_price_dividends.py --market hk --symbol 00700  --out ./work

Writes into <out>/:
    raw/price_daily.csv     date, open, high, low, close [, adj_close, volume]
    raw/dividends.csv       ex_date, amount
    raw/splits.csv          date, ratio
    price_stats.txt         returns, monthly closes, 52w range, drawdown, recent dailies
    price_snapshot.json     latest quote + market cap + multiples (where available)

Adjusted (total-return) figures are computed from adj_close when the source
provides it; otherwise the script says so instead of silently using raw prices.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


# ------------------------------------------------------------------ US

def yahoo_chart(symbol: str, years: int = 11):
    """Fetch daily history.

    NOTE: `range=max` makes Yahoo silently downgrade the interval to monthly
    (~264 rows for 22 years), which would corrupt every return and PE-band
    calculation. Always bound the window with period1/period2 instead, and
    verify the row count afterwards.
    """
    import requests
    import time as _t
    now = int(_t.time())
    p1 = now - int(years * 365.25 * 86400)
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = requests.get(
                f"https://{host}/v8/finance/chart/{symbol}",
                params={"period1": p1, "period2": now, "interval": "1d",
                        "events": "div,splits", "includeAdjustedClose": "true"},
                headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200:
                js = r.json()
                res = (js.get("chart", {}) or {}).get("result") or []
                if res:
                    n = len(res[0].get("timestamp") or [])
                    # ~250 trading days per year; anything far below means the
                    # interval was downgraded, so reject and try the next host.
                    if n >= years * 200:
                        return js
        except Exception:
            continue
    return None


def fetch_us(symbol: str, out: C.Out):
    import pandas as pd

    js = yahoo_chart(symbol, 11)
    daily = divs = splits = None
    meta = {}

    if js and js.get("chart", {}).get("result"):
        res = js["chart"]["result"][0]
        meta = res.get("meta", {}) or {}
        ts = res.get("timestamp") or []
        q = (res.get("indicators", {}).get("quote") or [{}])[0]
        adj = (res.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
        daily = pd.DataFrame({
            "date": pd.to_datetime(ts, unit="s").date,
            "open": q.get("open"), "high": q.get("high"),
            "low": q.get("low"), "close": q.get("close"),
            "volume": q.get("volume"),
        })
        if adj:
            daily["adj_close"] = adj
        ev = res.get("events", {}) or {}
        if ev.get("dividends"):
            divs = pd.DataFrame(
                [{"ex_date": pd.to_datetime(int(k), unit="s").date(), "amount": v["amount"]}
                 for k, v in ev["dividends"].items()]).sort_values("ex_date")
        if ev.get("splits"):
            splits = pd.DataFrame(
                [{"date": pd.to_datetime(int(k), unit="s").date(),
                  "ratio": v.get("splitRatio")} for k, v in ev["splits"].items()]
            ).sort_values("date")
        C.log(f"  [OK]   Yahoo chart: {len(daily)} rows, "
              f"{daily['date'].iloc[0]} .. {daily['date'].iloc[-1]}")

    if daily is None:
        import akshare as ak
        name, px = C.first_ok([("akshare_us_daily",
                                lambda: ak.stock_us_daily(symbol=symbol))],
                              label="US price")
        if px is not None:
            daily = px.rename(columns={"date": "date"})
            daily["date"] = pd.to_datetime(daily["date"]).dt.date
            C.log("  [WARN] no adjusted close available from this source; "
                  "total-return figures will be flagged as unavailable")

    if daily is None:
        return None, "US price data unreachable"

    daily = daily.dropna(subset=["close"]).reset_index(drop=True)
    out.write_csv("price_daily.csv", daily)
    if divs is not None:
        out.write_csv("dividends.csv", divs)
    if splits is not None:
        out.write_csv("splits.csv", splits)

    snap = {"market": "us", "symbol": symbol,
            "price": meta.get("regularMarketPrice"),
            "currency": meta.get("currency"),
            "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
            "as_of": str(pd.Timestamp.now("UTC").date())}
    snap.update(em_snapshot_us(symbol))
    out.write_json("price_snapshot.json", snap)
    C.log(f"  snapshot: {json.dumps(snap, ensure_ascii=False, default=str)[:300]}")
    return {"daily": daily, "dividends": divs, "splits": splits}, None


def em_snapshot_us(symbol: str):
    """Eastmoney push2 snapshot. Field map: f43 price, f116 mcap, f163 static PE,
    f164 PE(TTM), f167 PB. Verify by f116/f43 == share count before trusting."""
    import requests
    for attempt in range(4):
        try:
            r = requests.get("https://push2.eastmoney.com/api/qt/stock/get",
                             params={"secid": f"105.{symbol}",
                                     "fields": "f43,f44,f45,f46,f57,f58,f60,f116,f117,"
                                               "f163,f164,f167",
                                     "invt": 2, "fltt": 2},
                             headers={"User-Agent": UA,
                                      "Referer": "https://quote.eastmoney.com/"},
                             timeout=25)
            d = (r.json() or {}).get("data") or {}
            if d.get("f43"):
                out = {"em_price": d.get("f43"), "em_market_cap": d.get("f116"),
                       "em_static_pe": d.get("f163"), "em_pe_ttm": d.get("f164"),
                       "em_pb": d.get("f167")}
                if d.get("f43"):
                    out["em_implied_shares"] = (
                        round(d["f116"] / d["f43"]) if d.get("f116") else None)
                C.log("  [OK]   Eastmoney snapshot "
                      f"(static PE {d.get('f163')}, PE(TTM) {d.get('f164')}, "
                      f"PB {d.get('f167')})")
                return out
        except Exception:
            import time
            time.sleep(3)
    C.log("  [--]   Eastmoney snapshot unavailable (normal; fallback sources used)")
    return {}


# ------------------------------------------------------------------ CN

def fetch_cn(symbol: str, out: C.Out):
    import akshare as ak
    import pandas as pd

    pre = "sh" if str(symbol).startswith(("6", "9")) else "sz"
    name, px = C.first_ok([
        ("sina_qfq", lambda: ak.stock_zh_a_daily(symbol=pre + str(symbol), adjust="qfq")),
        ("em_hist", lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                               adjust="qfq")),
        ("tx_hist", lambda: ak.stock_zh_a_hist_tx(symbol=pre + str(symbol), adjust="qfq")),
    ], label="CN price")
    if px is None:
        return None, "CN price data unreachable (all three sources failed)"

    px = px.copy()
    px.columns = [str(c).lower() for c in px.columns]
    if "date" in px.columns:
        px["date"] = pd.to_datetime(px["date"]).dt.date
    # Every CN source is requested with adjust='qfq' (forward-adjusted), which
    # already folds dividends and splits into the price. Mirror it into
    # adj_close so the return statistics compute instead of reporting n/a.
    if name and "qfq" in name and "adj_close" not in px.columns:
        px["adj_close"] = px["close"]
    out.write_csv("price_daily.csv", px)

    divs = None
    ok, d = C.retry(lambda: ak.stock_fhps_detail_em(symbol=symbol), tries=2,
                    label="CN dividend")
    if ok and d is not None and not d.empty:
        divs = d
        out.write_csv("dividends.csv", divs)
        C.log(f"  [OK]   dividends: {d.shape}")

    val = None
    ok, v = C.retry(lambda: ak.stock_zh_valuation_baidu(
        symbol=symbol, indicator="市盈率(TTM)", period="近五年"), tries=2,
        label="CN PE history")
    if ok and v is not None and not v.empty:
        val = v
        out.write_csv("pe_history.csv", val)
        C.log(f"  [OK]   PE(TTM) history: {len(v)} points")

    snap = {"market": "cn", "symbol": symbol, "currency": "CNY",
            "last_close": float(px["close"].iloc[-1]),
            "last_date": str(px["date"].iloc[-1]),
            "pe_ttm_latest": (float(val["value"].iloc[-1]) if val is not None
                              and len(val) else None)}
    out.write_json("price_snapshot.json", snap)
    return {"daily": px.rename(columns={c: c for c in px.columns}),
            "dividends": divs, "splits": None, "pe_history": val}, None


# ------------------------------------------------------------------ HK

def fetch_hk(symbol: str, out: C.Out):
    import akshare as ak
    import pandas as pd

    sym = str(symbol).zfill(5)
    name, px = C.first_ok([
        ("sina_hk_daily", lambda: ak.stock_hk_daily(symbol=sym, adjust="qfq")),
        ("em_hk_hist", lambda: ak.stock_hk_hist(symbol=sym, period="daily",
                                                adjust="qfq")),
    ], label="HK price")
    if px is None:
        return None, "HK price data unreachable"

    px = px.copy()
    px.columns = [str(c).lower() for c in px.columns]
    if "date" in px.columns:
        px["date"] = pd.to_datetime(px["date"]).dt.date
    # Both HK sources are requested forward-adjusted (qlfq), so the close already
    # reflects dividends and splits. Mirror it into adj_close so returns compute.
    if "adj_close" not in px.columns:
        px["adj_close"] = px["close"]
    out.write_csv("price_daily.csv", px)

    divs = None
    ok, d = C.retry(lambda: ak.stock_hk_dividend_payout_em(symbol=sym), tries=2,
                    label="HK dividend")
    if ok and d is not None and not d.empty:
        divs = d
        out.write_csv("dividends.csv", divs)
        C.log(f"  [OK]   dividends: {d.shape}")

    val = None
    ok, v = C.retry(lambda: ak.stock_hk_valuation_baidu(
        symbol=sym, indicator="市盈率(TTM)", period="近五年"), tries=2,
        label="HK PE history")
    if ok and v is not None and not v.empty:
        val = v
        out.write_csv("pe_history.csv", val)
        C.log(f"  [OK]   PE(TTM) history: {len(v)} points")

    snap = {"market": "hk", "symbol": sym,
            "last_close": float(px["close"].iloc[-1]),
            "last_date": str(px["date"].iloc[-1]),
            "pe_ttm_latest": (float(val["value"].iloc[-1]) if val is not None
                              and len(val) else None)}
    out.write_json("price_snapshot.json", snap)
    return {"daily": px, "dividends": divs, "splits": None, "pe_history": val}, None


# ------------------------------------------------------------------ stats

def stats_text(data: dict, market: str) -> str:
    import pandas as pd

    d = data["daily"].copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    L = []
    has_adj = "adj_close" in d.columns and d["adj_close"].notna().any()

    L.append("=" * 90)
    L.append(f"PRICE STATISTICS  market={market}")
    L.append("=" * 90)
    L.append(f"rows={len(d)}  first={d['date'].iloc[0].date()}  "
             f"last={d['date'].iloc[-1].date()}  last_close={d['close'].iloc[-1]:.2f}")
    L.append(f"adjusted-close available: {has_adj}"
             + ("" if has_adj else "   <-- TOTAL RETURN UNAVAILABLE, SAY SO IN THE REPORT"))
    L.append("")
    L.append("-" * 90)
    L.append("TOTAL RETURN (dividend-adjusted)")
    L.append("-" * 90)
    if has_adj:
        adj = d.dropna(subset=["adj_close"])
        end_d, end_v = adj["date"].iloc[-1], adj["adj_close"].iloc[-1]
        for yrs in (1, 2, 3, 5, 6, 10):
            start = end_d - pd.DateOffset(years=yrs)
            s = adj[adj["date"] >= start]
            if s.empty:
                continue
            a0 = s["adj_close"].iloc[0]
            if not a0:
                continue
            tot = end_v / a0 - 1
            act = (end_d - s["date"].iloc[0]).days / 365.25
            ann = (end_v / a0) ** (1 / act) - 1 if act > 0 else float("nan")
            L.append(f"  {yrs}y  from {s['date'].iloc[0].date()}  "
                     f"cum {tot*100:7.1f}%   annualised {ann*100:6.2f}%")
    else:
        L.append("  n/a - source returned raw closes only")

    L.append("")
    L.append("-" * 90)
    L.append("ANNUAL RANGES (split-adjusted close basis - Yahoo adjusts for splits "
             "but not dividends; use adj_close for total return)")
    L.append("-" * 90)
    for y in sorted(d["date"].dt.year.unique())[-7:]:
        s = d[d["date"].dt.year == y]
        L.append(f"  {y}: open {s['open'].iloc[0]:>9.2f}  close {s['close'].iloc[-1]:>9.2f}"
                 f"  high {s['high'].max():>9.2f}  low {s['low'].min():>9.2f}")

    L.append("")
    L.append("-" * 90)
    L.append("MONTHLY CLOSES (last 24)")
    L.append("-" * 90)
    m = d.set_index("date")["close"].resample("ME").last().dropna()
    for k, v in m.tail(24).items():
        L.append(f"  {k.strftime('%Y-%m')}  {v:>10.2f}")

    L.append("")
    L.append("-" * 90)
    L.append("52-WEEK AND DRAWDOWN")
    L.append("-" * 90)
    end_d = d["date"].iloc[-1]
    w = d[d["date"] >= end_d - pd.DateOffset(years=1)]
    L.append(f"  52w high {w['high'].max():.2f} on {w.loc[w['high'].idxmax(),'date'].date()}")
    L.append(f"  52w low  {w['low'].min():.2f} on {w.loc[w['low'].idxmin(),'date'].date()}")
    peak = d["close"].cummax()
    dd = (d["close"] / peak - 1) * 100
    L.append(f"  max drawdown (close basis) {dd.min():.1f}% on {d.loc[dd.idxmin(),'date'].date()}")
    L.append(f"  current vs 52w high: "
             f"{(d['close'].iloc[-1]/w['high'].max()-1)*100:.1f}%")

    L.append("")
    L.append("-" * 90)
    L.append("QUARTERLY AVERAGE CLOSE (last 8, for cost-basis estimates)")
    L.append("-" * 90)
    q = d.set_index("date")["close"].resample("QE").agg(["mean", "min", "max"]).dropna()
    for k, r in q.tail(8).iterrows():
        L.append(f"  {k.strftime('%Y')}Q{ (k.month-1)//3+1 }: mean {r['mean']:>10.2f}"
                 f"  range {r['min']:.2f} - {r['max']:.2f}")

    L.append("")
    L.append("-" * 90)
    L.append("LAST 30 TRADING DAYS")
    L.append("-" * 90)
    for _, r in d.tail(30).iterrows():
        L.append(f"  {r['date'].date()}  o {r['open']:>9.2f}  h {r['high']:>9.2f}"
                 f"  l {r['low']:>9.2f}  c {r['close']:>9.2f}")
    return "\n".join(L)


def dividend_text(divs) -> str:
    if divs is None:
        return "DIVIDENDS: not available from the fetched sources.\n" \
               "If the company truly never paid a dividend, state that fact explicitly."
    L = ["=" * 90, "DIVIDEND HISTORY (raw source rows)", "=" * 90]
    try:
        L.append(divs.to_string(index=False)[:6000])
    except Exception:
        L.append(str(divs)[:6000])
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch price and dividend data")
    ap.add_argument("--market", required=True, choices=["us", "cn", "hk"])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--out", default="./work")
    args = ap.parse_args()

    C.setup_console()

    C.require("pandas", "requests", "akshare")
    C.head(f"FETCH PRICE + DIVIDENDS  {args.market.upper()} / {args.symbol}")
    out = C.Out(args.out)

    fn = {"us": fetch_us, "cn": fetch_cn, "hk": fetch_hk}[args.market]
    data, err = fn(args.symbol, out)
    if err:
        C.log(f"\n[ABORT] {err}")
        return 2

    text = stats_text(data, args.market) + "\n\n" + dividend_text(data["dividends"])
    out.write_text("price_stats.txt", text)
    C.log("")
    C.log(text)
    C.log("")
    C.log(f"wrote {os.path.join(out.root, 'price_stats.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
