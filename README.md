# company-deep-analysis

**给 AI Agent 用的上市公司深度分析技能包。** 输入一家公司，输出一份固定格式、数据可溯源的中文深度分析报告。

- 支持 **美股 / A股 / 港股**
- 固定 **12 章结构**，以《买入检查清单》**16 问**为骨架
- **数据真实性强制校验**：三级来源分级 + 一手文件反查 + 阻断式交付门禁
- 覆盖：近期大事件、高管访谈、**白宫官员投资（仅美股）**、**高管自身投资/内部人交易**、近期股价、**名人持仓（含持仓时间与成本）**、未来发展、投资安全边际

产出范例：[`plugins/company-deep-analysis/skills/company-deep-analysis/assets/example-report-google-20261008.md`](plugins/company-deep-analysis/skills/company-deep-analysis/assets/example-report-google-20261008.md)（Alphabet / GOOGL，12 章 / 6.4 万字 / 522 行表格）

---

## 一键安装

### Claude Code（插件市场）

```
/plugin marketplace add ykangli/company-deep-analysis
/plugin install company-deep-analysis@company-deep-analysis
```

装完新开一个会话即可用。

### OpenAI Codex

Codex 自带 `skill-installer` 技能，最省事：

```
安装 /company-deep-analysis 仓库里
plugins/company-deep-analysis/skills/company-deep-analysis 这个 skill
```

或直接调用它的脚本：

```bash
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo ykangli/company-deep-analysis \
  --path plugins/company-deep-analysis/skills/company-deep-analysis
```

也可以把本仓库注册成 Codex 的 git marketplace，追加到 `~/.codex/config.toml`：

```toml
[marketplaces.company-deep-analysis]
source_type = "git"
source = "https://github.com/ykangli/company-deep-analysis.git"
```

### DeepSeek Harness / 其他 Agent（通用一行）

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.ps1 | iex
```

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.sh | bash
```

脚本会自动探测本机已安装的 Agent，把 skill 装到它们的用户级技能目录：

| Agent | 安装位置 |
|---|---|
| Claude Code | `~/.claude/skills/company-deep-analysis` |
| OpenAI Codex | `${CODEX_HOME:-~/.codex}/skills/company-deep-analysis` |
| DeepSeek Harness | `${DSH_HOME:-~/.dsh}/skills/company-deep-analysis` |
| 通用 AGENTS 约定 | `~/.agents/skills/company-deep-analysis` |

只装某一个：

```powershell
# Windows
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.ps1))) -Target claude
```
```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.sh | bash -s -- --target codex
```

可选 `--target`：`auto`（默认）/ `all` / `claude` / `codex` / `dsh` / `agents` / `project`
加 `--force`（PowerShell 用 `-Force`）覆盖已安装版本。

### 手动安装（任何 Agent 都适用）

```bash
git clone --depth 1 https://github.com/ykangli/company-deep-analysis.git
# 把 plugins/company-deep-analysis/skills/company-deep-analysis
# 复制到你的 Agent 的技能目录即可
```

对只读 `AGENTS.md` 的 Agent（Cursor / Windsurf / Cline / Gemini CLI 等），在项目规则文件里加一行指针：

```markdown
## 上市公司深度分析
需要"分析某家公司 / 深度分析报告 / 买入检查清单"时，
先完整阅读 skills/company-deep-analysis/SKILL.md，并按其 Phase 0–7 执行。
```

---

## 依赖

```bash
# 不需要手动装。首次运行任何脚本时，会自动创建独立虚拟环境并安装依赖：
python ~/.dsh/skills/company-deep-analysis/scripts/bootstrap.py

# 也可以手动检查 / 强制重建 / 走国内镜像
python .../scripts/bootstrap.py --check
python .../scripts/bootstrap.py --force
python .../scripts/bootstrap.py --mirror
```

**依赖是自动的**：`install.ps1` / `install.sh` 装完 skill 后会立刻调用 `bootstrap.py`，它会在 `~/.company-deep-analysis/.venv`（Windows 为 `%LOCALAPPDATA%\company-deep-analysis\.venv`）建一个**独立虚拟环境**并安装 `requirements.txt`，然后写下就绪标记。之后无论你用哪个 `python` 调用脚本，脚本都会**自动重入**该虚拟环境——不需要 activate，也不会污染系统 Python。若当前解释器已经具备全部依赖，则整个步骤自动跳过，不创建任何 venv。

只需 Python ≥ 3.9；**装完先自检**：

```bash
python ~/.dsh/skills/company-deep-analysis/scripts/preflight.py --market us --symbol GOOGL
```

`preflight` 返回非 0 表示数据源不通——此时不要让 Agent 凭记忆写报告。

---

## 使用

对 Agent 说：

> 用 company-deep-analysis 分析一下宁德时代（300750）

Agent 会按 Phase 0→7 执行：预检 → 读清单与范例 → 抓一手披露 → 并行调研 → 算指标 → 按模板写作 → **跑校验器** → 交付。

### 手工执行

```bash
S=~/.dsh/skills/company-deep-analysis/scripts

python $S/bootstrap.py                                  # 依赖（幂等，已就绪则跳过）
python $S/preflight.py               --market us --symbol GOOGL
python $S/fetch_financials.py        --market us --symbol GOOGL --out ./work
python $S/fetch_price_dividends.py   --market us --symbol GOOGL --out ./work
python $S/fetch_primary_source.py    --market us --symbol GOOGL --out ./work \
       --since 2026-01-01 --grep "Anthropic" "backlog"
python $S/compute_metrics.py         --work ./work --price 350.91 --shares 12.23e9
python $S/verify_report.py           --report ./报告.md --work ./work
```

一键跑完整链路：

```bash
python $S/selftest.py --market us --symbol GOOGL --report ./报告.md
```

---

## 仓库结构

```
company-deep-analysis/
├── .claude-plugin/marketplace.json          # Claude Code 插件市场清单
├── plugins/
│   └── company-deep-analysis/
│       ├── .claude-plugin/plugin.json       # Claude Code 插件清单
│       ├── README.md
│       └── skills/company-deep-analysis/    # ← skill 本体
│           ├── SKILL.md                     # 主入口：铁律 + Phase 0-7 + 反模式
│           ├── requirements.txt             # Python 依赖（bootstrap.py 自动安装）
│           ├── references/                  # 8 份方法论（清单/模板/校验/市场/持仓/估值/证据…）
│           │   └── 00-buy-checklist.md      # ★ 买入检查清单原文（四维度 16 题）
│           ├── scripts/                     # 10 个脚本（依赖/预检/财报/行情/一手/指标/校验/自检/共用）
│           └── assets/                      # 范例报告 + 人工质量门
├── install.ps1 / install.sh                 # 通用一键安装
├── publish.ps1 / publish.sh                 # 发布前校验 + 占位符替换 + git 初始化
│                                            #   .ps1 给 PowerShell，.sh 给 Git Bash / WSL
├── tools/reset-template.py                  # 把已 stamp 的仓库还原为占位符模板
├── README.md
└── LICENSE
```

**为什么 skill 放在 `plugins/.../skills/...` 而不是仓库根目录？**
因为要同时满足三种约定：Claude 插件市场要求插件在仓库内有自己的目录；Codex 的 `install-skill-from-github.py --path` 需要能精确指向含 `SKILL.md` 的目录；通用安装脚本需要一条稳定路径。三者共用同一份文件，不重复维护。

---

## 常见问题（均为实测踩过的坑）

**Q: Windows 上 `.\install.ps1` 报"未对文件进行数字签名 / 无法加载文件"？**

这是 PowerShell 执行策略（默认 `RemoteSigned`）拦截了磁盘上的未签名脚本。三种解法任选其一：

```powershell
# 1) 推荐：iex 形式不从磁盘加载文件，因此不触发签名检查
irm https://raw.githubusercontent.com/ykangli/company-deep-analysis/main/install.ps1 | iex

# 2) 显式绕过（仅本次进程）
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Target all

# 3) 克隆后为当前用户解除限制（谨慎）
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**Q: 安装脚本在中文环境下乱码或报语法错误？**

`install.ps1` 被刻意写成**纯 ASCII**：Windows PowerShell 5.1 在文件缺少 UTF-8 BOM 时按系统 ANSI 代码页读取 `.ps1`，中文字符串会被解码成乱码并导致解析失败。因此引导脚本只用英文输出——**skill 本体与生成的报告仍是中文**，不受影响。
同理，`publish.ps1`（维护者用，含中文提示）保存为**带 BOM 的 UTF-8**，请勿用会丢弃 BOM 的工具改写它。

**Q: 装完 agent 还是不认识这个 skill？**

- Claude Code 插件方式：**新开一个会话**；`~/.claude/skills/` 方式：重启会话。
- Codex：装完下次对话生效。
- DeepSeek Harness：热加载，无需重启。
- 通用 AGENTS 约定的 agent：确认规则文件（`AGENTS.md` 等）里有指向 `SKILL.md` 的说明。

**Q: Git Bash 里执行 `./publish.ps1` 报 `$'\357\273\277#': command not found` 或 `syntax error near unexpected token`？**

Git Bash 是 POSIX shell，不能执行 PowerShell 脚本（`\357\273\277` 就是文件开头的 UTF-8 BOM）。改用随仓库提供的包装脚本：

```bash
./publish.sh -Owner <你的GitHub用户名> -ValidateOnly
./publish.sh -Owner <你的GitHub用户名>
```

它会自动寻找 `pwsh`（PowerShell 7）或 `powershell`（5.1）并把参数原样转发给 `publish.ps1`。
`install.sh` 本身就是 bash 脚本，在 Git Bash 里可以直接运行，无需包装。

**Q: 某个数据源失败？**

东方财富接口会间歇性阻断，脚本已做三级回退（东财 → 新浪 → 腾讯）。先跑 `preflight.py`：返回非 0 表示数据源不通，**此时不要让 Agent 写报告**。

---

## 发布步骤（维护者）

**先选对你的 shell**——`publish.ps1` 是 PowerShell 脚本，POSIX shell 无法执行它：

| 你的终端 | 用哪个 | 命令 |
|---|---|---|
| PowerShell / Windows Terminal | `publish.ps1` | `.\publish.ps1 -Owner <你> -ValidateOnly` |
| **Git Bash / MSYS / WSL** | **`publish.sh`** | `./publish.sh -Owner <你> -ValidateOnly` |
| 其他 | 两者皆可 | `publish.sh` 会自动寻找 `pwsh` 或 `powershell` 并转发参数 |

> 若在 Git Bash 里误敲 `./publish.ps1`，会看到
> `./publish.ps1: line 1: $'\357\273\277#': command not found`
> ——`\357\273\277` 是 UTF-8 BOM 字节，说明 bash 正在把 PowerShell 脚本当 shell 脚本解析。改用 `./publish.sh` 即可。

```powershell
# 1. 改完 skill 后，先本地校验（不联网、不改 git）
.\publish.ps1 -Owner ykangli -ValidateOnly

# 2. 正式发布：替换占位符 + 校验 + git init/commit
.\publish.ps1 -Owner ykangli -Version 1.0.0

# 3. 按脚本打印的指令推送
git push -u origin main
```

**注意 `publish.ps1` 的 stamp 是单向的**：它把 `ykangli` / `company-deep-analysis` / `ykangli/company-deep-analysis` / `@company-deep-analysis` 替换成真实值并直接改写工作区文件。首次发布后照常提交即可；若之后要改 owner/仓库名或发布 fork，用下面的工具还原成模板再重新 stamp：

```bash
python tools/reset-template.py --owner <当前owner> --repo <当前仓库名>
```

`publish.ps1` 会检查：frontmatter 的 `name` 与目录名是否一致、18 个必需文件是否齐全、8 个 Python 脚本能否编译、两个 JSON 清单是否合法且 `source` 路径存在、是否混入缓存或临时文件。
加 `-RunSelfTest` 还会联网跑一次完整自检。

---

## 校验器会拦什么

`verify_report.py` 共 7 类 error / 2 类 warning，**有 error 就阻断交付**：

| 码 | 检查 |
|:--:|------|
| E1 | 12 章是否齐全（第八章按市场条件强制：美股必写，A股/港股必须删除） |
| E2 | 检查清单 16 题是否全答、每题是否有评级 |
| E3 | 是否使用证据标记 |
| E4 | 每张表格列数是否一致 |
| E5 | 评分表 / 价格纪律表 / 未能核实清单 / 已剔除清单是否齐备 |
| E6 | 报告内年度财务数字与抓取数据是否一致（阈值 60%） |
| E7 | 是否残留 TODO / 待补充 等占位内容 |
| W1 | 模糊表述（据传 / 据悉 / 市场普遍认为） |
| W2 | `【推算】` 附近是否看得到公式 |

实测：范例报告 18/18 财务数字一致、0 error 通过；故意构造的残缺报告被检出 **22 个 error**。

---

## 设计取舍

- **固定 12 章而非自由发挥**：报告的价值在于横向可比与不漏项。自由结构必然漏掉"盈利质量""反向 DCF"这类最容易忽略却最关键的环节。
- **强制"反向 DCF"**：正向 DCF 只告诉你"你认为值多少"；反向 DCF 告诉你"现价已经假设了什么"——后者才是安全边际判断的起点。
- **强制"未能核实"**：一份语气确定但有关键编造的报告，危害远大于一份如实标注缺口的报告。
- **强制反查一手文件**：开发过程中就发生过实例——某 Agent 把"商誉增加"归因为某收购，而当时手上的 8-K 新闻稿里根本没有该公司名；后来下载 10-Q 才确认该收购属实（**且 8-K 确实不含并购明细**）。因此"反查"成了硬性步骤，且 `fetch_primary_source.py` 内置 `--grep`。
- **阻断式校验**：非阻断的"建议"没人会执行。

---

## 已知限制

- **不构成投资建议。** 输出估值区间与价格纪律，不给买卖指令。
- A股/港股一手披露需手动获取（巨潮/交易所/HKEX 无稳定公开 API），脚本只给入口；美股为全自动。
- 白宫官员一节依赖公开检索，结论经常是"未能核实到任何一条"——这是**正常且诚实**的结果。
- 13F 不披露成本，持仓成本只能是推算并强制标注。
- 东方财富接口不稳定，脚本已做三级回退；若全部源失效必须停止，不得凭记忆写。

---

## License

MIT — 见 [LICENSE](LICENSE)。报告内容基于公开信息，不构成任何证券的买卖建议。
