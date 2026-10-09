#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 2c: fetch PRIMARY-SOURCE filings and extract key facts.

This is the highest-value script in the skill. For US issuers it downloads the
8-K Exhibit 99.1 earnings press releases straight from SEC EDGAR, plus the
10-Q/10-K, and saves plain text. Those documents settle revenue, segment
revenue, operating income, EPS, share count, dividend declarations, buybacks
and the FCF reconciliation - authoritatively.

Usage:
    python fetch_primary_source.py --market us --symbol GOOGL --out ./work
    python fetch_primary_source.py --market us --cik 0001652044 --out ./work
    python fetch_primary_source.py --market us --symbol GOOGL --out ./work \
        --grep "Wiz" "Anthropic" "acquisition"

For cn/hk this script prints the official disclosure portals to use and creates
the directory; retrieve those filings manually or via a search-capable agent.

Writes into <out>/primary/:
    <form>_<date>_<accession>.txt     plain text of each filing
    filings_index.tsv                 form, date, accession, url
    facts.txt                         key figures grepped out of the releases
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

UA = "Research research@example.com"
SLEEP = 0.25  # SEC fair-access: stay well under 10 req/s


def sec_get(url: str, host: str):
    """SEC requires a descriptive User-Agent, and data.sec.gov needs its own Host."""
    import requests
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    if host:
        headers["Host"] = host
    time.sleep(SLEEP)
    return requests.get(url, headers=headers, timeout=45)


def resolve_cik(symbol: str):
    """Ticker -> zero-padded CIK via SEC's company_tickers.json."""
    ok, r = C.retry(lambda: sec_get("https://www.sec.gov/files/company_tickers.json", ""),
                    tries=3, label="ticker map")
    if not ok:
        return None, None
    try:
        data = r.json()
    except Exception:
        return None, None
    sym = symbol.upper().replace(".", "-")
    for _, row in data.items():
        if str(row.get("ticker", "")).upper() == sym:
            return str(row["cik_str"]).zfill(10), row.get("title")
    return None, None


def list_filings(cik: str, forms=("8-K", "10-Q", "10-K"), since="2024-01-01"):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    ok, r = C.retry(lambda: sec_get(url, "data.sec.gov"), tries=3, label="submissions")
    if not ok:
        return []
    try:
        js = r.json()
    except Exception as exc:  # noqa: BLE001
        C.log(f"  [FAIL] submissions JSON: {exc}  "
              f"(usually a wrong Host header for data.sec.gov)")
        return []
    rec = js.get("filings", {}).get("recent", {})
    out = []
    n = len(rec.get("form", []))
    for i in range(n):
        if rec["form"][i] in forms and rec["filingDate"][i] >= since:
            out.append({
                "form": rec["form"][i],
                "date": rec["filingDate"][i],
                "acc": rec["accessionNumber"][i],
                "doc": rec["primaryDocument"][i],
            })
    return out


def filing_index(cik: str, acc: str):
    u = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
         f"{acc.replace('-', '')}/index.json")
    ok, r = C.retry(lambda: sec_get(u, ""), tries=3, quiet=True)
    if not ok:
        return []
    try:
        return (r.json().get("directory", {}) or {}).get("item", []) or []
    except Exception:
        return []


def to_text(url: str) -> str:
    from bs4 import BeautifulSoup
    import warnings
    try:
        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    except Exception:
        pass
    ok, r = C.retry(lambda: sec_get(url, ""), tries=2, quiet=True)
    if not ok:
        return ""
    try:
        soup = BeautifulSoup(r.text, "lxml")
        for t in soup(["script", "style"]):
            t.decompose()
        txt = soup.get_text("\n")
        return re.sub(r"\n\s*\n+", "\n", txt)
    except Exception:
        return re.sub(r"<[^>]+>", " ", r.text)


# Figures worth pulling out of a press release automatically.
FACT_PATTERNS = [
    ("revenue_growth", r"revenues increased (\d+)%[^.]{0,120}?to \$([\d,.]+) billion"),
    ("operating_income", r"[Oo]perating income[^.]{0,80}?\$([\d,.]+)\s*(?:billion|million)?"),
    ("operating_margin", r"operating margin[^.]{0,40}?(\d+)%"),
    ("net_income", r"[Nn]et income[^.]{0,80}?\$([\d,.]+)\s*(?:billion|million)?"),
    ("eps", r"EPS[^.]{0,60}?\$([\d.]+)"),
    ("other_income", r"[Oo]ther income[^.]{0,60}?\$([\d,.]+) billion"),
    ("capex_guide", r"[Cc]ap[Ee]x[^.]{0,90}?\$?([\d,]+)\s*to\s*\$?([\d,]+) billion"),
    ("dividend", r"quarterly cash dividend of \$([\d.]+) per share"),
    ("free_cash_flow", r"[Ff]ree cash flow[^.]{0,90}?\(?\$?\(?([\d,.]+)\)?"),
    ("buyback", r"[Rr]epurchas\w+[^.]{0,80}?\$([\d,.]+) billion"),
    ("backlog", r"backlog[^.]{0,80}?\$([\d,.]+) billion"),
    ("employees", r"([\d,]{4,})\s*$"),
]


def extract_facts(text: str):
    facts = []
    for name, pat in FACT_PATTERNS:
        for m in re.finditer(pat, text):
            snippet = text[max(0, m.start() - 90):m.end() + 90]
            snippet = re.sub(r"\s+", " ", snippet).strip()
            facts.append((name, m.group(0)[:120], snippet))
            break
    return facts


def fetch_us(symbol, cik, out: C.Out, since: str, limit: int, grep_terms):
    if not cik:
        cik, title = resolve_cik(symbol)
        if not cik:
            return None, f"could not resolve CIK for {symbol}"
        C.log(f"  resolved {symbol} -> CIK {cik}  ({title})")

    filings = list_filings(cik, since=since)
    C.log(f"  filings since {since}: {len(filings)}")
    if not filings:
        return None, "no filings found"

    # newest first, cap the downloads
    filings = sorted(filings, key=lambda f: f["date"], reverse=True)[:limit]

    index_rows = []
    earnings_paths = []   # press releases, ranked first for fact extraction
    other_paths = []

    for f in filings:
        items = filing_index(cik, f["acc"])
        base = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{f['acc'].replace('-', '')}/")

        earnings, primary = [], []
        for it in items:
            n = it.get("name", "")
            low = n.lower()
            if not n.endswith(".htm"):
                continue
            # Skip the full-submission text dump and anything huge/duplicative;
            # we want the rendered exhibits, not the whole accession.
            if re.search(r"ex(hibit)?[-_]?99|ex991|ex-99", low):
                earnings.insert(0, n)
            elif n == f["doc"] or re.match(r"^(goog|d\d+)[-_.]", low):
                primary.append(n)
        # Highest value first: the earnings press release, then the 8-K body.
        picked = earnings[:1] + primary[:1]

        for n in picked:
            url = base + n
            txt = to_text(url)
            if len(txt) < 800:
                continue
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{f['form']}_{f['date']}_{n}")
            path = os.path.join(out.primary, safe + ".txt")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(txt)
            index_rows.append(f"{f['form']}\t{f['date']}\t{f['acc']}\t{url}\t{safe}.txt")
            if n in earnings:
                earnings_paths.append(path)
            else:
                other_paths.append(path)
            C.log(f"    {f['form']} {f['date']}  {n}  ({len(txt)} chars)")

    all_text_paths = earnings_paths + other_paths

    with open(os.path.join(out.primary, "filings_index.tsv"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write("form\tdate\taccession\turl\tfile\n")
        fh.write("\n".join(index_rows))

    # facts from the two most recent earnings releases
    facts_lines = ["=" * 90,
                   "AUTO-EXTRACTED FACTS (regex hits - ALWAYS read the filing text "
                   "to confirm; regex can mis-bind)",
                   "=" * 90]
    # facts from the two most recent earnings releases (ranked first above)
    earnings = earnings_paths[:2]
    for p in earnings:
        facts_lines.append("")
        facts_lines.append(f"--- {os.path.basename(p)}")
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        for name, hit, snip in extract_facts(txt):
            facts_lines.append(f"  [{name:<18}] {hit}")
            facts_lines.append(f"      ...{snip}...")

    # targeted reverse-verification greps
    if grep_terms:
        facts_lines.append("")
        facts_lines.append("=" * 90)
        facts_lines.append("REVERSE-VERIFICATION GREP (did the claim actually appear?)")
        facts_lines.append("=" * 90)
        for term in grep_terms:
            total = 0
            where = []
            for p in all_text_paths:
                try:
                    t = open(p, encoding="utf-8").read()
                except Exception:
                    continue
                c = len(re.findall(re.escape(term), t, re.I))
                if c:
                    total += c
                    where.append(f"{os.path.basename(p)}({c})")
            verdict = "FOUND" if total else "NOT FOUND in any downloaded filing"
            facts_lines.append(f"  '{term}': {verdict}  {', '.join(where[:4])}")
        facts_lines.append("")
        facts_lines.append("  If a claim's key noun does not appear in any filing, you")
        facts_lines.append("  MUST write 未能核实 rather than asserting the claim.")

    out.write_text(os.path.join("primary", "facts.txt"), "\n".join(facts_lines))
    C.log("")
    C.log("\n".join(facts_lines))
    return {"cik": cik, "n_filings": len(index_rows)}, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch primary-source filings")
    ap.add_argument("--market", required=True, choices=["us", "cn", "hk"])
    ap.add_argument("--symbol", default="")
    ap.add_argument("--cik", default="")
    ap.add_argument("--out", default="./work")
    ap.add_argument("--since", default="2024-01-01")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--grep", nargs="*", default=[],
                    help="terms to reverse-verify against the downloaded filings")
    args = ap.parse_args()

    C.setup_console()

    C.require("requests", "bs4")
    C.head(f"FETCH PRIMARY SOURCES  {args.market.upper()} / "
           f"{args.symbol or args.cik}")
    out = C.Out(args.out)

    if args.market != "us":
        C.log("  Official portals for this market:")
        if args.market == "cn":
            C.log("    - 巨潮资讯网  http://www.cninfo.com.cn/   (年报/半年报/季报/公告)")
            C.log("    - 上交所      http://www.sse.com.cn/")
            C.log("    - 深交所      http://www.szse.cn/")
        else:
            C.log("    - HKEX 披露易 https://www1.hkexnews.hk/   (年报/中报/公告/权益披露)")
        C.log("")
        C.log("  Download the two most recent annual/interim reports and the most")
        C.log("  recent results announcement, save them under:")
        C.log(f"    {out.primary}")
        C.log("  Then re-run with --grep to reverse-verify claims.")
        return 0

    info, err = fetch_us(args.symbol, args.cik, out, args.since, args.limit, args.grep)
    if err:
        C.log(f"\n[ABORT] {err}")
        return 2
    C.log("")
    C.log(f"wrote {out.primary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
