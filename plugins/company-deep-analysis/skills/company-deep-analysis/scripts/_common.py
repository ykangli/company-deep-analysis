# -*- coding: utf-8 -*-
"""Shared helpers for the company-deep-analysis skill."""
from __future__ import annotations

import io
import json
import os
import sys
import time
import datetime as dt

# ---------------------------------------------------------------- dependencies
#
# Importing this module hands the process over to the skill's managed virtual
# environment when one exists (created by bootstrap.py). Every script imports
# _common before touching pandas/akshare, so a user can invoke any script with
# ANY python on PATH and still end up in the environment that has the deps.
#
# _deps has no side effects and imports only the standard library, so this is
# safe even when no venv exists yet.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _deps as _D
except Exception:                                    # pragma: no cover
    _D = None
else:
    _D.reexec_into_venv()


def require(*modules: str) -> None:
    """Exit with an actionable message when a third-party import is missing."""
    import importlib
    missing = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    if not missing:
        return

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    log("")
    log("=" * 78)
    log("缺少 Python 依赖：" + ", ".join(missing))
    log("=" * 78)
    log("")
    log("  一次性安装依赖（推荐：自动建独立虚拟环境，不污染系统 Python）")
    log(f'      python "{os.path.join(here, "bootstrap.py")}"')
    log("")
    log("  国内网络较慢时：")
    log(f'      python "{os.path.join(here, "bootstrap.py")}" --mirror')
    log("")
    log("  若你更愿意自己管理依赖：")
    log(f'      pip install -r "{os.path.join(root, "requirements.txt")}"')
    log("")
    raise SystemExit(3)


def dependency_report() -> str:
    """One-line description of the current dependency environment."""
    if _D is None:
        return "无法加载 _deps.py（技能目录不完整？）"
    venv = _D.active_venv()
    missing = _D.missing_packages()
    where = venv if (venv and _D.running_in(venv)) else sys.executable
    if missing:
        return f"缺少 {', '.join(missing)}   [解释器 {where}]"
    return f"齐全                [解释器 {where}]"


# ---------------------------------------------------------------- console

def setup_console() -> None:
    """Force UTF-8 stdout so Chinese output survives every console."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def log(msg: str = "") -> None:
    print(msg, flush=True)


def head(title: str) -> None:
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


# ---------------------------------------------------------------- retry

def retry(fn, tries: int = 4, delay: float = 3.0, label: str = "", quiet: bool = False):
    """Call fn() up to `tries` times, sleeping `delay` between attempts.

    Public data endpoints rate-limit and proxy-block intermittently; retrying is
    the normal case, not an error path. Returns (ok, value_or_exception).
    """
    last = None
    for i in range(1, tries + 1):
        try:
            return True, fn()
        except Exception as exc:  # noqa: BLE001 - endpoint failures are expected
            last = exc
            if i < tries:
                time.sleep(delay)
    if not quiet:
        log(f"  [FAIL] {label or getattr(fn, '__name__', 'call')}: "
            f"{type(last).__name__}: {str(last)[:150]}")
    return False, last


def first_ok(candidates, label: str = ""):
    """Try (name, callable) pairs in order; return (name, value) of the first success.

    Used for multi-source fallback: eastmoney -> sina -> tencent.
    """
    tried = []
    for name, fn in candidates:
        ok, val = retry(fn, tries=2, delay=2.0, quiet=True)
        if ok and val is not None:
            try:
                if hasattr(val, "empty") and val.empty:
                    tried.append(f"{name}(empty)")
                    continue
            except Exception:
                pass
            log(f"  [OK]   {label or ''} via {name}")
            return name, val
        tried.append(name)
    log(f"  [FAIL] {label or ''} - all sources failed: {', '.join(tried)}")
    return None, None


# ---------------------------------------------------------------- paths

def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


class Out:
    """A run directory holding fetched artefacts plus a transcript."""

    def __init__(self, root: str):
        self.root = ensure_dir(root)
        self.raw = ensure_dir(os.path.join(self.root, "raw"))
        self.primary = ensure_dir(os.path.join(self.root, "primary"))
        self._buf = io.StringIO()

    def write_text(self, name: str, text: str) -> str:
        p = os.path.join(self.root, name)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return p

    def write_json(self, name: str, obj) -> str:
        p = os.path.join(self.root, name)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, default=str)
        return p

    def write_csv(self, name: str, df, subdir: str = "raw") -> str:
        p = os.path.join(self.root, subdir, name)
        df.to_csv(p, index=False, encoding="utf-8-sig")
        return p


# ---------------------------------------------------------------- finance math

def safe_div(a, b):
    try:
        if a is None or b in (None, 0):
            return None
        return a / b
    except Exception:
        return None


def pct(a, b):
    """Percentage change from b to a."""
    r = safe_div(a, b)
    return None if r is None else (r - 1.0) * 100.0


def cagr(first, last, years):
    if not first or not last or first <= 0 or last <= 0 or years <= 0:
        return None
    return ((last / first) ** (1.0 / years) - 1.0) * 100.0


def fmt(v, nd=2, dash="n/a"):
    if v is None:
        return dash
    try:
        return f"{v:,.{nd}f}"
    except Exception:
        return str(v)


def today_str() -> str:
    return dt.date.today().strftime("%Y%m%d")


def ymd(d) -> str:
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


# ---------------------------------------------------------------- reconciliation

class Recon:
    """Collects reconciliation assertions so a failed sum aborts the run."""

    def __init__(self):
        self.items = []

    def check(self, label: str, lhs, rhs, tol_pct: float = 0.5) -> bool:
        ok = False
        diff_pct = None
        if lhs is not None and rhs not in (None, 0):
            diff_pct = abs(lhs - rhs) / abs(rhs) * 100.0
            ok = diff_pct <= tol_pct
        self.items.append((label, lhs, rhs, diff_pct, ok))
        flag = "OK  " if ok else "FAIL"
        log(f"  [{flag}] {label}: {fmt(lhs, 3)} vs {fmt(rhs, 3)}"
            + (f"  (diff {diff_pct:.3f}%)" if diff_pct is not None else "  (insufficient data)"))
        return ok

    def report(self) -> str:
        lines = []
        for label, lhs, rhs, diff, ok in self.items:
            lines.append(f"{'OK' if ok else 'FAIL'}\t{label}\t{fmt(lhs,3)}\t{fmt(rhs,3)}\t"
                         + (f"{diff:.4f}%" if diff is not None else "n/a"))
        return "\n".join(lines)

    def failures(self):
        return [i for i in self.items if not i[4]]
