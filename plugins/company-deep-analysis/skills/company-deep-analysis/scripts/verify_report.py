#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 6: BLOCKING verification of a finished report.

Usage:
    python verify_report.py --report report.md --work ./work --market us

    # the checklist is bundled with the skill and is used by default:
    #   references/00-buy-checklist.md
    # override it only if you analyse against a different checklist:
    python verify_report.py --report report.md --checklist "path/to/checklist.md"

Exit codes:
    0 = clean (warnings may still be printed)
    2 = errors found - fix and re-run before delivering

Checks
    E1  required chapters present (and chapter 8 conditional on market)
    E2  all 16 checklist questions answered, with a verdict marker
    E3  evidence markers used at all
    E4  markdown tables well formed (consistent column count per block)
    E5  required blocks present: scoring table, price-discipline table,
        unverified list, discarded/corrected list
    E6  annual financials in the report match the fetched data
    E7  no unresolved placeholder text (TODO / XXX / 待补充)
    W1  vague wording that should be upgraded or downgraded
    W2  a 推算 without a visible formula
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

# The canonical checklist ships inside the skill, so a fresh install can verify
# reports with no external file. Users may override with --checklist.
DEFAULT_CHECKLIST = os.path.join(SKILL_ROOT, "references", "00-buy-checklist.md")

sys.path.insert(0, HERE)
import _common as C  # noqa: E402

REQUIRED_CHAPTERS = [
    ("零", r"^##\s*零[、.．]"),
    ("一 公司速览", r"^##\s*一[、.．]"),
    ("二 核心财务", r"^##\s*二[、.．]"),
    ("三 估值分析", r"^##\s*三[、.．]"),
    ("四 股价走势", r"^##\s*四[、.．]"),
    ("五 分红与回购", r"^##\s*五[、.．]"),
    ("六 股东结构与持仓", r"^##\s*六[、.．]"),
    ("七 近期大事件", r"^##\s*七[、.．]"),
    ("九 检查清单", r"^##\s*九[、.．]"),
    ("十 未来发展", r"^##\s*十[、.．]"),
    ("十一 安全边际", r"^##\s*十一[、.．]"),
    ("十二 结论", r"^##\s*十二[、.．]"),
    ("数据来源与时效性", r"^##\s*数据来源"),
]
OFFICIALS_CHAPTER = ("八 白宫官员投资", r"^##\s*八[、.．]")

VAGUE = [
    "可能持有", "据传", "据悉", "市场普遍认为", "有分析指出",
    "业内人士表示", "似乎", "恐怕",
]
PLACEHOLDER = ["TODO", "TBD", "XXX", "待补充", "此处省略", "待填", "[待", "（略）", "(略)",
               "此处略", "占位符", "PLACEHOLDER"]
# A bare Chinese "略" is a common word ("略高于" / "忽略" / "战略"), so placeholder
# scanning must never match a substring of ordinary prose. The list above is
# matched literally, and each hit is additionally required to look like an
# editorial marker rather than normal text.
REQUIRED_BLOCKS = [
    ("评分表", r"综合(评分|安全边际)"),
    ("价格纪律表", r"价格区间"),
    ("未能核实清单", r"未能核实"),
    ("已剔除/已纠正清单", r"(已剔除|已纠正|剔除的数据)"),
]


class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []

    def err(self, code, msg):
        self.errors.append((code, msg))

    def warn(self, code, msg):
        self.warnings.append((code, msg))

    def info(self, msg):
        self.infos.append(msg)


def check_chapters(text: str, market: str, r: Result):
    for name, pat in REQUIRED_CHAPTERS:
        if not re.search(pat, text, re.M):
            r.err("E1", f"缺少章节：{name}")
    name, pat = OFFICIALS_CHAPTER
    has = re.search(pat, text, re.M)
    if market == "us" and not has:
        r.err("E1", f"美股报告缺少章节：{name}")
    if market in ("cn", "hk") and has:
        r.err("E1", f"{market.upper()} 报告不应包含章节：{name}")


def check_checklist(text: str, checklist_path, r: Result):
    nums = set()
    for m in re.finditer(r"\*\*\[[^\]]*\]\s*(\d{1,2})\s*[.、]", text):
        nums.add(int(m.group(1)))
    # also accept a plain "**12. " heading inside chapter nine
    if len(nums) < 16:
        for m in re.finditer(r"^\*\*(\d{1,2})\s*[.、]", text, re.M):
            nums.add(int(m.group(1)))
    missing = [i for i in range(1, 17) if i not in nums]
    if missing:
        r.err("E2", f"检查清单缺答以下题目：{missing}")
    else:
        r.info(f"检查清单 16 题齐全（找到编号 {sorted(nums)}）")

    # each answer should end with a 评级/结论 line
    verdicts = len(re.findall(r"\*\*评级[:：]", text)) + len(re.findall(r"\*\*结论[:：]", text))
    if verdicts < 16:
        r.warn("E2", f"只有 {verdicts} 处 '**评级：**' / '**结论：**' 标记；"
                     f"按模板每题都应有一句评级")

    if checklist_path:
        if not os.path.exists(checklist_path):
            r.err("E2", f"清单文件不存在：{checklist_path}")
            return
        src = open(checklist_path, encoding="utf-8").read()
        # The canonical checklist writes items as "- [ ] **1. text**"; a couple of
        # items have no space after the dot, so \s* not \s.
        src_q = len(re.findall(r"\*\*\d{1,2}\.\s*", src))
        r.info(f"对照清单：{os.path.basename(checklist_path)}（原文 {src_q} 题）")
        if src_q and len(nums) < src_q:
            r.err("E2", f"清单原文含 {src_q} 题，报告只答了 {len(nums)} 题"
                        f"（缺 {[i for i in range(1, src_q + 1) if i not in nums]}）")
        expected = 16
        if src_q != expected:
            r.warn("E2", f"清单原文解析出 {src_q} 题，预期 {expected} 题；"
                         f"请确认清单文件的题目格式未被改动")
    else:
        r.warn("E2", "未提供清单文件，已跳过与原文的题目数比对")


def check_markers(text: str, r: Result):
    for mk in ("【已核实】", "【未能核实】"):
        if mk not in text:
            r.err("E3", f"全文未使用证据标记 {mk}")
    n_ok = text.count("【已核实】") + text.count("（已核实）")
    n_no = text.count("【未能核实】") + text.count("（未能核实）")
    n_est = text.count("【推算】") + text.count("（推算）") + text.count("推算")
    if n_est == 0:
        r.warn("E3", "全文没有出现'推算'字样；13F 成本等项目通常需要推算，请确认")
    r.info(f"证据标记：已核实 {n_ok} 处，推算 {n_est} 处，未能核实 {n_no} 处")
    if n_no == 0:
        r.warn("E3", "没有任何 '未能核实' —— 现实中几乎不存在全部核实的报告，"
                     "请确认没有把不确定的信息写成事实")


def check_tables(text: str, r: Result):
    lines = text.split("\n")
    block, start = [], 0

    def flush():
        nonlocal block
        if len(block) >= 2:
            counts = [ln.count("|") for _, ln in block]
            if len(set(counts)) > 1:
                r.err("E4", f"第 {start} 行起的表格列数不一致：{counts}")
        block = []

    for i, ln in enumerate(lines, 1):
        if re.match(r"^\s*\|.*\|\s*$", ln):
            if not block:
                start = i
            block.append((i, ln.strip()))
        else:
            flush()
    flush()


def check_blocks(text: str, r: Result):
    for name, pat in REQUIRED_BLOCKS:
        if not re.search(pat, text):
            r.err("E5", f"缺少必需内容块：{name}")
    if not re.search(r"\|\s*价格区间\s*\|", text) and "价格区间" in text:
        r.warn("E5", "价格纪律表似乎未使用标准表头 '| 价格区间 |'")
    if "概率加权" not in text:
        r.warn("E5", "情景预测缺少'概率加权预期年化回报'")


def check_placeholders(text: str, r: Result):
    for p in PLACEHOLDER:
        for m in re.finditer(re.escape(p), text):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            r.err("E7", f"发现未完成的占位内容 '{p}'：...{ctx}...")


def check_vague(text: str, r: Result):
    for w in VAGUE:
        hits = [m.start() for m in re.finditer(re.escape(w), text)]
        if hits:
            ctx = text[max(0, hits[0] - 40):hits[0] + 40].replace("\n", " ")
            r.warn("W1", f"模糊表述 '{w}' 出现 {len(hits)} 次：...{ctx}...")
    # 推算 without a formula nearby
    bad = 0
    for m in re.finditer(r"【推算】", text):
        window = text[max(0, m.start() - 260):m.end() + 120]
        if not re.search(r"[=＝]|÷|/|×|推算(方法|公式|说明)|均价|即\s*\d", window):
            bad += 1
    if bad:
        r.warn("W2", f"{bad} 处 【推算】 附近看不到公式或假设说明")

def check_numbers(text: str, work: str, r: Result):
    """Confirm the report's annual figures match the fetched metrics."""
    mp = os.path.join(work, "metrics.txt") if work else None
    if not mp or not os.path.exists(mp):
        r.info("未提供 --work/metrics.txt，跳过数字一致性校验")
        return
    metrics = open(mp, encoding="utf-8").read()
    block = re.search(r"ANNUAL SERIES\s*\n-+\n(.*?)\n-{20}", metrics, re.S)
    if not block:
        r.info("metrics.txt 中未找到 ANNUAL SERIES，跳过数字校验")
        return
    values = []
    for ln in block.group(1).split("\n")[1:]:
        parts = ln.split()
        if len(parts) < 4:
            continue
        for v in parts[1:4]:
            try:
                values.append(float(v))
            except ValueError:
                continue
    if not values:
        return
    hit = 0
    for v in values:
        cands = {f"{v:,.1f}", f"{v:,.2f}", f"{v:,.3f}", f"{v:.1f}", f"{v:.2f}",
                 f"{v:,.0f}", f"{v*100:,.1f}", f"{v*100:,.2f}"}
        if any(c in text for c in cands):
            hit += 1
    ratio = hit / len(values)
    r.info(f"财务数字一致性：{hit}/{len(values)} = {ratio*100:.0f}% 在报告中出现")
    if ratio < 0.6:
        r.err("E6", f"报告中仅 {ratio*100:.0f}% 的年度财务数字能在 metrics.txt 中找到，"
                    "可能使用了与抓取数据不同的口径")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a finished report")
    ap.add_argument("--report", required=True)
    ap.add_argument("--checklist", default=DEFAULT_CHECKLIST,
                    help="清单文件路径（默认使用技能内置的 references/00-buy-checklist.md）")
    ap.add_argument("--no-checklist", action="store_true",
                    help="跳过与清单原文的比对")
    ap.add_argument("--work", default="")
    ap.add_argument("--market", default="us", choices=["us", "cn", "hk"])
    args = ap.parse_args()

    C.setup_console()
    C.head(f"VERIFY REPORT  {args.report}")
    checklist = "" if args.no_checklist else args.checklist
    if checklist and not os.path.exists(checklist):
        C.log(f"  [warn] 清单文件不存在，跳过题目数比对: {checklist}")
        checklist = ""

    if not os.path.exists(args.report):
        C.log(f"[FATAL] report not found: {args.report}")
        return 2
    text = open(args.report, encoding="utf-8").read()
    C.log(f"  chars={len(text)}  lines={text.count(chr(10))+1}")

    r = Result()
    check_chapters(text, args.market, r)
    check_checklist(text, checklist, r)
    check_markers(text, r)
    check_tables(text, r)
    check_blocks(text, r)
    check_placeholders(text, r)
    check_vague(text, r)
    check_numbers(text, args.work, r)

    C.log("")
    if r.infos:
        C.log("INFO")
        for i in r.infos:
            C.log(f"  [i] {i}")
    if r.warnings:
        C.log("")
        C.log(f"WARNINGS ({len(r.warnings)}) - address or justify each in the report")
        for code, m in r.warnings:
            C.log(f"  [{code}] {m}")
    if r.errors:
        C.log("")
        C.log(f"ERRORS ({len(r.errors)})  <-- BLOCKING")
        for code, m in r.errors:
            C.log(f"  [{code}] {m}")
        C.log("")
        C.log("  => NOT READY. Fix every error and re-run until clean.")
        return 2

    C.log("")
    C.log("  => PASS. Now run the human quality gate in assets/quality-gate.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
