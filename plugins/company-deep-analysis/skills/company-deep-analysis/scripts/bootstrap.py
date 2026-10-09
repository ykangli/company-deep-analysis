#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键准备依赖：自动创建独立虚拟环境并安装 requirements.txt。

用法：
    python bootstrap.py                 # 需要时装，不需要时跳过
    python bootstrap.py --check         # 只检查（0=齐全，1=缺依赖），不改动任何东西
    python bootstrap.py --force         # 删除并重建虚拟环境
    python bootstrap.py --system        # 不建 venv，装到当前解释器的用户目录
    python bootstrap.py --venv DIR      # 指定虚拟环境位置
    python bootstrap.py --mirror        # 直接用国内镜像（默认先用官方源）
    python bootstrap.py --index-url URL # 自定义 pip 源

设计要点：
  * 如果当前解释器**已经**能导入全部依赖，本脚本什么都不做（不浪费几百 MB）。
  * 否则在用户目录下建 venv（默认 `~/.company-deep-analysis/.venv`，独立于技能目录，
    因此技能升级/重装不会丢失），装完后写一个 `.cda-deps-ok` 标记。
  * 技能里的其它脚本通过 `_common.py` 在导入时自动"重入"该 venv，
    所以使用者之后无论用哪个 python 调用都能正常跑。
  * 国内网络下官方源可能超时，脚本会自动回退到清华/阿里镜像。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _deps as D  # noqa: E402  (imported after sys.path fix)

MIRRORS = [
    ("清华 TUNA", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里云", "https://mirrors.aliyun.com/pypi/simple/"),
]


def out(msg: str = "") -> None:
    print(msg, flush=True)


def rule(title: str) -> None:
    out("")
    out("=" * 74)
    out(title)
    out("=" * 74)


def run(cmd, label="", quiet=False):
    """Run a command with inherited stdio so progress bars reach the user."""
    if not quiet:
        out(f"  $ {' '.join(str(c) for c in cmd)}")
    try:
        rc = subprocess.call([str(c) for c in cmd])
    except FileNotFoundError as exc:
        out(f"  [FAIL] 找不到可执行文件: {exc}")
        return 127
    if rc != 0 and label:
        out(f"  [FAIL] {label} (exit {rc})")
    return rc


def verify(python_exe, quiet=False) -> bool:
    code = ("import pandas, requests, akshare, bs4, lxml, sys;"
            "print('ok', sys.version.split()[0])")
    try:
        r = subprocess.run([python_exe, "-c", code], capture_output=True, text=True,
                           timeout=180)
    except Exception as exc:
        if not quiet:
            out(f"  [FAIL] 校验失败: {type(exc).__name__}: {exc}")
        return False
    if r.returncode == 0:
        if not quiet:
            out(f"  [OK]   依赖校验通过 ({r.stdout.strip()})")
        return True
    if not quiet:
        err = (r.stderr or "").strip().splitlines()
        out(f"  [FAIL] 依赖校验失败: {err[-1] if err else 'unknown'}")
    return False


def write_marker(venv: str, extra=None) -> None:
    payload = {
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "packages": [pkg for _, pkg in D.REQUIRED],
        "python": sys.version.split()[0],
        "requirements": os.path.basename(D.requirements_file()),
    }
    if extra:
        payload.update(extra)
    with open(os.path.join(venv, D.MARKER), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def pip_install(python_exe, index_url, quiet, extra_args=()):
    cmd = [python_exe, "-m", "pip", "install", "--no-input",
           "--disable-pip-version-check"]
    if index_url:
        cmd += ["--index-url", index_url]
    cmd += list(extra_args)
    cmd += ["-r", D.requirements_file()]
    return run(cmd, label="pip install 失败", quiet=quiet)


def install_with_mirror_fallback(python_exe, explicit_index, quiet) -> str | None:
    """Try official PyPI first, then CN mirrors. Returns the index that worked."""
    attempts = []
    if explicit_index:
        attempts.append(("指定的源", explicit_index))
    else:
        attempts.append(("PyPI 官方源", None))
        attempts += MIRRORS

    for name, url in attempts:
        out("")
        out(f"  -- 尝试 {name}{' (' + url + ')' if url else ''}")
        rc = pip_install(python_exe, url, quiet)
        if rc == 0:
            return url or "pypi"
        if explicit_index:
            break  # user asked for a specific index; do not silently ignore it
        out(f"  -- {name} 失败，换下一个源")
    return None


def do_system(quiet) -> int:
    rule("安装依赖到当前解释器（--system）")
    out(f"  解释器: {sys.executable}")
    idx = install_with_mirror_fallback(sys.executable, INDEX_URL, quiet)
    if idx is None:
        out("\n  [FAIL] 所有源都失败。请检查网络，或手动执行：")
        out(f"    {sys.executable} -m pip install -r \"{D.requirements_file()}\"")
        return 1
    if not verify(sys.executable, quiet):
        return 1
    out("\n  [OK] 完成（--system 模式不创建 venv）")
    return 0


def do_venv(venv: str, quiet, force: bool) -> int:
    rule(f"创建虚拟环境并安装依赖")
    out(f"  目标 venv : {venv}")
    out(f"  基础解释器: {sys.executable}")

    if force and os.path.isdir(venv):
        out("  --force：删除旧虚拟环境")
        shutil.rmtree(venv, ignore_errors=True)

    if not os.path.exists(D.venv_python(venv)):
        os.makedirs(os.path.dirname(venv), exist_ok=True)
        rc = run([sys.executable, "-m", "venv", venv], label="创建 venv 失败", quiet=quiet)
        if rc != 0:
            out("\n  提示：若系统缺少 venv 模块（部分 Linux 需 python3-venv），")
            out("        可改用  python bootstrap.py --system")
            return 1

    py = D.venv_python(venv)
    run([py, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
         "--upgrade", "pip", "wheel", "setuptools"], quiet=quiet)

    idx = install_with_mirror_fallback(py, INDEX_URL, quiet)
    if idx is None:
        out("\n  [FAIL] 所有源都失败。请检查网络，或手动执行：")
        out(f"    {py} -m pip install -r \"{D.requirements_file()}\"")
        out("  也可以指定镜像：python bootstrap.py --mirror")
        return 1

    if not verify(py, quiet):
        out("\n  [FAIL] 安装后校验未通过。可尝试重建：python bootstrap.py --force")
        return 1

    write_marker(venv, {"index": idx})
    out(f"  [OK]   已写入标记 {D.MARKER}")
    return 0


INDEX_URL = None


def main() -> int:
    global INDEX_URL
    ap = argparse.ArgumentParser(description="准备 company-deep-analysis 的 Python 依赖")
    ap.add_argument("--check", action="store_true",
                    help="只检查依赖是否齐全，不做任何改动")
    ap.add_argument("--force", action="store_true", help="删除并重建虚拟环境")
    ap.add_argument("--system", action="store_true",
                    help="不建 venv，装到当前解释器的用户目录")
    ap.add_argument("--venv", default=None, help="虚拟环境目录（默认用户目录下）")
    ap.add_argument("--index-url", default=None, help="自定义 pip 源")
    ap.add_argument("--mirror", action="store_true", help="直接用国内镜像")
    ap.add_argument("--quiet", action="store_true", help="减少输出")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.mirror:
        INDEX_URL = MIRRORS[0][1]
    elif args.index_url:
        INDEX_URL = args.index_url

    quiet = args.quiet

    # ---- fast path: current interpreter already has everything ------------
    if not args.force:
        if D.has_everything():
            if args.check:
                if not quiet:
                    out("[OK] 当前解释器已具备全部依赖，无需安装")
                return 0
            rule("依赖检查")
            out(f"  解释器 : {sys.executable}")
            out(f"  结果   : 全部依赖已可用 -> 无需安装，也不会创建虚拟环境")
            return 0
        if args.check:
            miss = D.missing_packages()
            if not quiet:
                out(f"[MISSING] 缺少: {', '.join(miss)}")
                out(f"  修复: {sys.executable} \"{os.path.abspath(__file__)}\"")
            return 1

    if not os.path.exists(D.requirements_file()):
        out(f"[FAIL] 找不到 {D.requirements_file()}")
        return 1

    if not quiet:
        rule("准备依赖")
        miss = D.missing_packages()
        out(f"  当前解释器 : {sys.executable}")
        out(f"  缺少       : {', '.join(miss) if miss else '（无）'}")

    if args.system:
        return do_system(quiet)

    venv = os.path.abspath(args.venv) if args.venv else D.default_venv()
    return do_venv(venv, quiet, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
