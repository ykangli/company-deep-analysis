#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end self-test: run the whole pipeline and assert the gates hold.

Usage:
    python selftest.py --market us --symbol GOOGL --report <path-to-a-report>
    python selftest.py --market cn --symbol 603986            # data path only

Runs preflight -> fetch_financials -> fetch_price_dividends -> compute_metrics
and, when --report is given, verify_report. Prints a PASS/FAIL summary and
exits non-zero on the first hard failure.

Use this after installing the skill, after editing any script, or before
publishing a new version.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, label):
    cmd = [sys.executable] + args
    print("", flush=True)
    print(">" * 78, flush=True)
    print(">> " + " ".join(cmd), flush=True)
    print(">" * 78, flush=True)
    r = subprocess.run(cmd, cwd=HERE)
    ok = r.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {label} (exit {r.returncode})", flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill self-test")
    ap.add_argument("--market", default="us", choices=["us", "cn", "hk"])
    ap.add_argument("--symbol", default="GOOGL")
    ap.add_argument("--out", default="")
    ap.add_argument("--report", default="")
    ap.add_argument("--checklist", default="")
    ap.add_argument("--oneoff", action="append", default=[])
    args = ap.parse_args()

    work = args.out or os.path.join(tempfile.gettempdir(), f"cda_selftest_{args.market}")

    steps = [
        (["preflight.py", "--market", args.market, "--symbol", args.symbol],
         "Phase 0 preflight"),
        (["fetch_financials.py", "--market", args.market, "--symbol", args.symbol,
          "--out", work], "Phase 2a financials"),
        (["fetch_price_dividends.py", "--market", args.market, "--symbol", args.symbol,
          "--out", work], "Phase 2b price + dividends"),
    ]
    if args.market == "us":
        steps.append(
            (["fetch_primary_source.py", "--market", "us", "--symbol", args.symbol,
              "--out", work, "--since", "2026-01-01", "--limit", "3"],
             "Phase 2c primary sources"))

    results = []
    for a, label in steps:
        ok = run(a, label)
        results.append((label, ok))
        if not ok:
            break

    if all(ok for _, ok in results):
        cm = ["compute_metrics.py", "--work", work]
        for o in args.oneoff:
            cm += ["--oneoff", o]
        ok = run(cm, "Phase 3 metrics + reconciliation")
        results.append(("Phase 3 metrics", ok))

    if args.report and all(ok for _, ok in results):
        vr = ["verify_report.py", "--report", args.report, "--market", args.market,
              "--work", work]
        if args.checklist:
            vr += ["--checklist", args.checklist]
        ok = run(vr, "Phase 6 report verification")
        results.append(("Phase 6 verification", ok))

    print("", flush=True)
    print("=" * 78, flush=True)
    print("SELF-TEST SUMMARY", flush=True)
    print("=" * 78, flush=True)
    for label, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}", flush=True)
    print(f"\n  work dir: {work}", flush=True)

    failed = [l for l, ok in results if not ok]
    if failed:
        print(f"\n  => FAILED: {', '.join(failed)}", flush=True)
        return 1
    print("\n  => ALL PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
