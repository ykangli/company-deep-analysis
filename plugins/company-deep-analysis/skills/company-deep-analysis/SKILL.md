---
name: company-deep-analysis
description: Produce a single-file Chinese deep-analysis report on a listed company (US / A-share / HK) in a fixed 12-chapter format driven by the buy-checklist. Use when the user asks for a 深度分析报告 / 公司基本面分析 / 买入检查清单分析 / 分析这家公司值不值得买, or names a ticker and wants fundamentals, valuation, famous-investor holdings, insider trading, shareholder structure, recent events, executive interviews, future outlook and margin of safety. Enforces evidence grading (verified / estimated / unverified), one-primary-source verification of every load-bearing number, mandatory official-insider and officials-holdings sections for US stocks, and a blocking self-check before delivery.
license: For personal research use. Not investment advice.
---

# Company deep-analysis report

Turn "分析一下这家公司" into one deliverable: a Chinese Markdown report with a **fixed structure**, in which **every load-bearing number is traceable to a primary source**, and every claim is labelled with its evidence grade.

The output must be indistinguishable in format from `assets/example-report-google-20261008.md` — a real, fully worked report on Alphabet (GOOGL). **Read that file before writing anything.**

## Non-negotiable rules

These three override speed, length, and user pressure. Violating any of them invalidates the report.

1. **No fabrication. Ever.** A number you did not retrieve from a source is written as `未能核实`. Never estimate silently, never interpolate a missing year, never present a market rumour as a fact. A report with honest gaps is a good report; a report with one invented figure is worthless.
2. **Every load-bearing number needs one primary source.** Financial statements, share counts, dividends and buybacks come from filings (SEC EDGAR, 巨潮/交易所, HKEX) or the company's own earnings release — not from a news summary. If only secondary media is available, label it `【二手转述】`.
3. **Grade every claim.** Use exactly these three labels wherever a fact is asserted:
   - `【已核实】` — read from a primary source or an official data interface.
   - `【推算】` — derived by you from verified inputs; show the formula inline.
   - `【未能核实】` — searched and not found. **Write it down rather than omitting the item.**

Additionally: **a subagent's conclusion is `【二手转述】` until you verify it yourself.** subagents routinely promote an inference to a fact. See `references/07-evidence-grading.md` for the failure that motivated this rule.

## Workflow

Run the phases in order. Each gate must pass before the next phase starts.

### Phase 0 — Preflight (gate: data actually flows)

```bash
python scripts/preflight.py --market us --symbol GOOGL
```

Confirms network, the Python library set, and which sources respond for the target market. **If preflight fails, stop and report the environment problem — do not write a report from memory.** Public data endpoints rate-limit and intermittently proxy-block; that is normal, and the scripts already retry and fall back.

To exercise the whole pipeline at once (useful after install, or after editing any script):

```bash
python scripts/selftest.py --market us --symbol GOOGL --report <a-finished-report.md> \
    --checklist <checklist.md> --oneoff 2026=135.7
```

### Phase 1 — Scope and market routing

Read `references/04-market-adapters.md`. Decide the market, then fix the chapter set:

| Chapter | US | A-share | HK |
|---|---|---|---|
| 一–七, 九–十二 (core) | ✅ | ✅ | ✅ |
| **八、白宫官员投资情况** | ✅ **required** | ❌ omit | ❌ omit |
| 6.x 名人持仓 | 13F / Form 4 | 十大股东 / 龙虎榜 | HKEX 权益披露 |
| 6.x 内部人交易 | Form 4 | 董监高持股变动 | HKEX DI |

Also read the checklist once, and the example report once. Do not start gathering data before both are read.

### Phase 2 — Hard data (gate: 5 fiscal years + latest interim, reconciled)

```bash
python scripts/fetch_financials.py --market us --symbol GOOGL --out ./work
```

Produces income statement, balance sheet and cash-flow series (annual + quarterly) plus a normalised dump. Then:

```bash
python scripts/fetch_price_dividends.py --market us --symbol GOOGL --out ./work
python scripts/fetch_primary_source.py --market us --symbol GOOGL --out ./work
```

`fetch_primary_source.py` is the one that matters most: for US issuers it pulls the **8-K Exhibit 99.1 earnings press releases** straight from SEC EDGAR. That single source settles revenue, segment revenue, operating income, EPS, share count, dividend declaration, buyback, and FCF reconciliation — authoritative and quotable.

Reconcile before moving on: segment revenue must sum to total revenue; the balance sheet must balance; quarterly figures must sum to the annual figure. `compute_metrics.py` asserts these and aborts on mismatch.

### Phase 3 — Metric computation

```bash
python scripts/compute_metrics.py --work ./work --out ./work/metrics.txt
```

Computes ROE, margins, 5-year CAGR, free cash flow, share-count history, PE bands (static / TTM / **core**), reverse-DCF, and scenario valuations. Read `references/06-valuation-and-margin.md` for the method definitions.

**The single most important computation: separate core earnings from one-off and investment gains.** Many issuers report huge fair-value swings on equity stakes that flow through net income. Compute a core EPS and lead the valuation chapter with it. A GAAP P/E built on such a year is a valuation trap — this was the decisive finding in the Alphabet report (GAAP 17.6x vs core 33.6x).

### Phase 4 — Narrative research (parallelise)

Three independent streams. Dispatch them as background subagents in one message, then continue with Phase 3/5 yourself:

1. **Recent events + executive interviews** — regulatory/antitrust, product and technology, capital actions, litigation, management changes, and direct quotes from earnings calls and interviews with dates.
2. **Famous-investor holdings** — see `references/05-holders-insiders-officials.md`. Must return holding period, share counts by class, and **cost basis**.
3. **Officials' personal investments** (US only) + **insiders' own trading**.

Give every subagent the same instruction: cite a source and a date per claim; write `未能核实` rather than guessing; and **distinguish what they verified from what they inferred**. Then spot-check their load-bearing numbers yourself against the primary source (Phase 2 output) — expect to find at least one overstatement.

### Phase 5 — Write

Open `references/01-report-template.md` and fill it. Output path:

```
<out-dir>/<名称>_<代码>_深度分析报告_<YYYYMMDD>.md
```

Use `assets/example-report-google-20261008.md` as the format reference for tables, the blockquote header, the scoring table, and the price-discipline table. Match its density: this report type is table-heavy and citation-heavy by design.

`references/02-checklist-mapping.md` maps every checklist question to the chapters that must supply its evidence, and states what a defensible answer looks like. **All questions must be answered** — skipping one is a failed deliverable.

### Phase 6 — Verify (gate: blocking)

```bash
python scripts/verify_report.py --report <path> --checklist <checklist-path> --work ./work
```

Blocks delivery on: missing chapters, unanswered checklist questions, unsourced numbers, unbalanced tables, unreconciled financials, and claims asserted as fact that carry no evidence grade. Fix everything it reports and re-run until clean.

Then run the human quality gate in `assets/quality-gate.md`.

### Phase 7 — Deliver

State plainly: the output path, the market and currency, the data cutoff date, and the list of items marked `未能核实`. Never close with a buy/sell instruction — the report gives a valuation range and a price-discipline table, not advice.

## What the report must contain

Fixed chapter set; see the template for the full skeleton and every table.

- **零、核心结论摘要** — one-page table with scores, plus the three numbers a reader must remember.
- **一、公司速览** — what it does, in three sentences a 10-year-old understands; segment table; share-class structure.
- **二、核心财务数据** — 5 fiscal years + latest interim; ROE; CAGR; segment mix; cash flow and FCF; **earnings quality (core vs reported)**; balance sheet.
- **三、估值分析** — current multiples, 5-year PE band with position, peer comparison, multi-method intrinsic value, reverse-DCF, analyst consensus.
- **四、股价走势分析** — long-run and monthly prices, dated key points, recent dailies, attribution, drawdown statistics.
- **五、分红与回购** — full dividend history, buyback history, total shareholder yield, financing structure.
- **六、股东结构与名人持仓** — share classes; each famous holder with holding period, share count and cost; insiders' own trading; institutional holders.
- **七、近期大事件** — regulation, products, capital actions, management changes, **executive interview quotes with dates**.
- **八、白宫官员投资情况** — US only; see `references/05-holders-insiders-officials.md`.
- **九、买入检查清单逐条作答** — every question, with a verdict marker and a short verdict.
- **十、公司未来发展分析** — growth drivers, ranked risks, three-scenario forecast, observation windows.
- **十一、投资安全边际总结** — the multi-dimension scoring table.
- **十二、最终结论与操作建议** — conclusion, **price-discipline table**, one-paragraph summary.
- **数据来源与时效性说明** — sources, cutoff, and the discarded/unverifiable list.

## Reference index

| File | Load it when |
|---|---|
| `assets/example-report-google-20261008.md` | Always, before writing. The format contract. |
| `references/01-report-template.md` | Always. The skeleton to fill. |
| `references/02-checklist-mapping.md` | Always. Question → evidence map. |
| `references/03-data-verification.md` | Always. The verification protocol. |
| `references/04-market-adapters.md` | Phase 1. Market routing, sources, fallbacks. |
| `references/05-holders-insiders-officials.md` | Phase 4. Holders, insiders, officials. |
| `references/06-valuation-and-margin.md` | Phase 3. Valuation and scoring methods. |
| `references/07-evidence-grading.md` | Whenever labelling evidence; before delivery. |
| `assets/quality-gate.md` | Phase 6, as the human pre-delivery checklist. |
| `scripts/selftest.py` | After install or after editing any script. |

## Anti-patterns

Each of these was an observed failure, not a hypothetical.

- **Trusting the top-line P/E.** If net income contains investment gains, the GAAP P/E is meaningless. Always compute core EPS.
- **Letting a subagent's inference stand as fact.** Verify every load-bearing claim against the primary source.
- **Reporting a headline that contradicts the filing.** "Buffett sells Alphabet" was a subsidiary's separate filing, not the parent's position. Read the filing, not the headline.
- **Summing share classes.** Multi-class issuers report each class separately; never add A + B + C to compute ownership percentage.
- **Treating 13F market value as cost.** 13F reports quarter-end value, not purchase price. Derive cost only from disclosed transaction prices, and label it `【推算】`.
- **Quoting a period-average price as a transaction price.** Use quarter-end or disclosed prices, and say which.
- **Filling a missing year by interpolation.** Write `未能核实`.
- **Presenting a rumour as a deal.** Speculative supply agreements stay labelled as rumour.
- **Delivering without running `verify_report.py`.** It catches structural omissions that are invisible while writing.
