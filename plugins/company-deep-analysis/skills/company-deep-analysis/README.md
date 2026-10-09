# company-deep-analysis — 上市公司深度分析 Skill

一个可跨 Agent 复用的技能包：**输入一家上市公司，输出一份固定格式、数据可溯源的中文深度分析报告**，并以《买入检查清单》16 问为骨架作答。

产出范例见 [`assets/example-report-google-20261008.md`](assets/example-report-google-20261008.md)（Alphabet / GOOGL，12 章 / 6.4 万字 / 522 行表格）。

---

## 它解决什么问题

让分析报告**可复现、可审计**。核心不是"写得更长"，而是三条硬约束：

1. **格式统一** —— 12 章固定结构 + 固定表格，任何人写出来的报告长得一样。
2. **数据真实性校验（强制）** —— 三级来源分级；每个承重数字必须有 L1/L2 来源；脚本做加总校验、反查一手文件、数字一致性校验；交付前跑 `verify_report.py`（**有 error 就阻断交付**）。
3. **证据分级** —— 全文区分 `【已核实】/【推算】/【未能核实】`，不允许用"可能/据传"填充。

## 覆盖能力

| 能力 | 落在哪里 |
|------|---------|
| 格式统一 | `references/01-report-template.md` + `assets/example-report-google-20261008.md` |
| **买入检查清单（内置）** | `references/00-buy-checklist.md` —— 16 题原文随技能分发 |
| **数据真实性校验** | `references/03-data-verification.md`、`references/07-evidence-grading.md`、`scripts/verify_report.py` |
| 公司近期大事件 | 报告第七章；`SKILL.md` Phase 4 |
| 高管访谈 | 报告 7.5 节（**必须含 CEO 与 CFO 原话**） |
| **白宫官员投资（仅美股）** | 报告第八章；`references/05-holders-insiders-officials.md` 第三部分 |
| **公司高管自己投资** | 报告 6.x；`references/05-...md` 第二部分 |
| 近期股价情况 | 报告第四章；`scripts/fetch_price_dividends.py` |
| **名人持仓（持仓时间 + 成本）** | 报告 6.x；`references/05-...md` 第一部分 |
| 检查清单 16 问逐条作答 | 报告第九章；清单原文 `references/00-buy-checklist.md` + 作答指引 `references/02-checklist-mapping.md` |
| 未来发展分析 | 报告第十章（驱动 / 风险 / 三情景 / 观察窗口） |
| 投资安全边际 | 报告第十一、十二章（评分表 + 价格纪律表） |

---

## 安装：跨 Agent 通用

这个包遵循 **Agent Skills** 约定（`SKILL.md` + YAML frontmatter + `references/` + `scripts/` + `assets/`），Claude、Codex、Cursor 等都能用。**整个文件夹复制到对应目录即可**，无需构建。

### Claude Code / Claude Desktop
```bash
# 个人级（所有项目可用）
cp -r company-deep-analysis ~/.claude/skills/
# 或项目级
cp -r company-deep-analysis .claude/skills/
```

### OpenAI Codex CLI
```bash
cp -r company-deep-analysis ~/.codex/skills/
# 项目级
cp -r company-deep-analysis .codex/skills/
```

### 通用 AGENTS.md 型 Agent（Cursor / Windsurf / Cline / Gemini CLI 等）
把 skill 放到项目内任意位置，然后在 `AGENTS.md` 里加一行指针：

```markdown
## 上市公司深度分析
需要"分析某家公司/深度分析报告/买入检查清单"时，
先完整阅读 `skills/company-deep-analysis/SKILL.md`，并按其 Phase 0–7 执行。
```

### 其他约定目录
部分工具会扫描 `~/.agents/skills/`、`.agents/skills/`。若不确定你的 Agent 扫哪里，**直接把路径写进它的规则文件**最稳。

### 依赖（自动安装）
```bash
# 不需要手动装。首次运行任何脚本时，会自动创建独立虚拟环境并安装依赖：
python ~/.dsh/skills/company-deep-analysis/scripts/bootstrap.py

# 也可以手动检查 / 强制重建 / 走国内镜像
python .../scripts/bootstrap.py --check
python .../scripts/bootstrap.py --force
python .../scripts/bootstrap.py --mirror
```
Python ≥ 3.9。先跑预检：

```bash
python scripts/preflight.py --market us --symbol GOOGL
```

> **中国大陆网络提示**：本项目用东方财富 / 新浪 / 腾讯 / Yahoo / SEC 多源回退。东财接口会间歇性失败（这是常态，不是 bug），脚本已实现三级回退。若某市场全部源失败，`preflight.py` 会返回非 0——**此时不要凭记忆写报告**。

---

## 使用

### 自然语言触发
> 用 company-deep-analysis 分析一下宁德时代（300750），输出深度分析报告到 D:\investment\analysis

Agent 会按 Phase 0→7 执行：预检 → 读取清单与范例 → 抓一手披露 → 并行调研（大事件/高管访谈/名人持仓/内部人/白宫官员）→ 计算指标 → 按模板写作 → **跑校验器** → 交付。

### 手工执行（推荐，可控性最好）

```bash
# 0) 预检：数据不通就不要开始
python scripts/preflight.py --market us --symbol GOOGL

# 1) 财报（5 年 + 最新中期）
python scripts/fetch_financials.py --market us --symbol GOOGL --out ./work

# 2) 行情、分红、拆股、价格统计
python scripts/fetch_price_dividends.py --market us --symbol GOOGL --out ./work

# 3) 一手披露（美股：SEC 8-K/10-Q/10-K），并反查关键名词
python scripts/fetch_primary_source.py --market us --symbol GOOGL --out ./work \
    --since 2026-01-01 --grep "Anthropic" "backlog" "Wiz"

# 4) 指标计算（含核心利润剥离、PE 区间、DCF、反向 DCF）
python scripts/compute_metrics.py --work ./work --price 350.91 --shares 12.23e9 \
    --oneoff 2026=135.7 --oneoff 2025=24.6

# 5) 写作（此时才开写；对照 assets/example-report-google-20261008.md）

# 6) 校验（有 error 必须修完再交付）
python scripts/verify_report.py --report ./公司_代码_深度分析报告_YYYYMMDD.md \
        --work ./work --market us
```

### 市场参数

| 市场 | `--market` | 财报源 | 行情源（含回退） | 第八章 |
|------|:---------:|--------|----------------|:------:|
| 美股 | `us` | SEC EDGAR + 东财美股 | Yahoo → akshare | ✅ 必写 |
| A股 | `cn` | 东财 + 新浪 + 巨潮 | 新浪 → 东财 → 腾讯 | ❌ 删除 |
| 港股 | `hk` | 东财港股接口 | 新浪 → 东财 | ❌ 删除 |

---

## 目录结构

```
company-deep-analysis/
├── SKILL.md                                   # 主入口：铁律 + Phase 0-7 工作流 + 反模式
├── README.md                                  # 本文件
├── requirements.txt                           # Python 依赖（bootstrap.py 自动安装）
├── references/
│   ├── 00-buy-checklist.md                    # ★ 买入检查清单原文（四维度 16 题）
│   ├── 01-report-template.md                  # 报告骨架（写作契约）
│   ├── 02-checklist-mapping.md                # 清单 16 问 → 证据 → 合格答案
│   ├── 03-data-verification.md                # 数据真实性校验协议（强制）
│   ├── 04-market-adapters.md                  # 美股/A股/港股 数据源与口径
│   ├── 05-holders-insiders-officials.md       # 名人持仓 / 内部人 / 白宫官员
│   ├── 06-valuation-and-margin.md             # 核心利润、估值、情景、安全边际
│   └── 07-evidence-grading.md                 # 证据分级 + 12 条标题陷阱
├── scripts/
│   ├── bootstrap.py                           # 依赖自动安装（建 venv，幂等）
│   ├── _deps.py                               # 依赖解析 + 虚拟环境定位
│   ├── preflight.py                           # Phase 0 环境与数据通路预检
│   ├── fetch_financials.py                    # Phase 2a 三大报表（us/cn/hk）
│   ├── fetch_price_dividends.py               # Phase 2b 行情/分红/收益统计
│   ├── fetch_primary_source.py                # Phase 2c 一手披露 + 反查 grep
│   ├── compute_metrics.py                     # Phase 3 指标计算 + 加总校验
│   ├── verify_report.py                       # Phase 6 阻断式校验（22 类检查）
│   ├── selftest.py                            # 端到端自检
│   └── _common.py                             # 共用：依赖重入、重试、多源回退、对账
└── assets/
    ├── example-report-google-20261008.md      # 范例报告（格式契约）
    └── quality-gate.md                        # 人工交付前检查表
```

---

## 校验器会拦什么

`verify_report.py` 的 7 类 error / 2 类 warning：

| 码 | 检查 | 级别 |
|:--:|------|:----:|
| E1 | 12 章是否齐全（第八章按市场条件强制） | 阻断 |
| E2 | 清单 16 题是否全答、每题是否有评级 | 阻断 |
| E3 | 是否使用证据标记；是否完全没有"未能核实" | 阻断 / 警告 |
| E4 | 每张表格的列数是否一致 | 阻断 |
| E5 | 评分表、价格纪律表、未能核实清单、已剔除清单是否齐备 | 阻断 |
| E6 | 报告中的年度财务数字与抓取数据是否一致（阈值 60%） | 阻断 |
| E7 | 是否残留 TODO / 待补充 等占位内容 | 阻断 |
| W1 | 模糊表述（据传/据悉/市场普遍认为…） | 警告 |
| W2 | `【推算】` 附近是否看得到公式 | 警告 |

实测：范例报告 18/18 财务数字一致、0 error 通过；故意构造的残缺报告被检出 **22 个 error**。

---

## 设计取舍（为什么长这样）

- **强制 12 章而非自由发挥**：报告的价值在于横向可比与不漏项。自由结构必然漏掉"盈利质量"或"反向 DCF"这类最容易忽略却最关键的环节。
- **强制"反向 DCF"**：正向 DCF 只能告诉你"你认为值多少"；反向 DCF 告诉你"现价已经假设了什么"——后者才是安全边际判断的起点。
- **强制"未能核实"**：一份写满确定语气但有关键编造的报告，危害远大于一份如实标注缺口的报告。
- **强制反查一手文件**：本项目开发过程中就发生过一次实例——某 agent 把"商誉增加"归因为某收购，而当时手上的 8-K 新闻稿里根本没有该公司名。后来下载 10-Q 才确认该收购属实（**且 8-K 确实不含并购明细**）。因此"反查"被写成了硬性步骤，并且 `fetch_primary_source.py` 内置 `--grep`。
- **阻断式校验**：非阻断的"建议"没人会执行。

---

## 已知限制

- **不构成投资建议**。报告输出估值区间与价格纪律，不给买卖指令。
- **A股/港股的一手披露需手动获取**（巨潮/交易所/HKEX 无稳定公开 API），脚本只给出入口。美股为全自动。
- **白宫官员一节依赖公开检索**，结论经常是"未能核实到任何一条"——这是**正常且诚实**的结果，不要为了填满版面而编造。
- **13F 无成本披露**，持仓成本只能是推算，报告已强制标注。
- 东财接口不稳定；脚本已回退，但若全部源失效，**必须停止而不是凭记忆写**。

---

## 许可与免责

内部研究工具。报告内容基于公开信息，不构成任何证券的买卖建议。使用者应独立判断并承担风险。
