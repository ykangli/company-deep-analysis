# 市场适配器：美股 / A股 / 港股

同一套报告结构，三个市场在**数据源、章节开关、口径**上不同。Phase 1 先读本文件再动手。

---

## 一、章节开关

| 章节 | 美股 | A股 | 港股 |
|------|:----:|:---:|:---:|
| 零 ~ 七（核心） | ✅ | ✅ | ✅ |
| **八、白宫官员投资情况** | ✅ **必写** | ❌ **删除本章** | ❌ **删除本章** |
| 九（检查清单 16 问） | ✅ | ✅ | ✅ |
| 十 ~ 十二 | ✅ | ✅ | ✅ |
| 6.x 名人持仓 | 13F + Form 4 | 十大流通股东 + 龙虎榜 | HKEX 权益披露（CCASS） |
| 6.x 内部人 | Form 4 | 董监高及相关人员持股变动 | HKEX Director's Interests |
| 4.x 股价 | 复权价（含股息） | **必须用前复权** | 复权价 |

**A股/港股不写第八章**，其余章节标题编号顺延（第八章直接是检查清单？不——保持原编号，直接删掉第八章，第九章仍叫"九、买入检查清单"）。

---

## 二、数据源矩阵

### 美股

| 用途 | 首选 | 备选 | 脚本 |
|------|------|------|------|
| 财报一手原文 | **SEC EDGAR 8-K Exhibit 99.1**（财报新闻稿）、10-Q、10-K | 公司 IR 页面 | `fetch_primary_source.py` |
| 财报历史序列 | 东方财富美股财务接口（akshare `stock_financial_us_report_em` / `stock_financial_us_analysis_indicator_em`） | — | `fetch_financials.py` |
| 行情与分红 | **Yahoo Finance chart API**（`query2.finance.yahoo.com`，含 `events=div,splits`） | akshare `stock_us_daily` | `fetch_price_dividends.py` |
| 实时快照 | 东方财富 `push2` 接口（`secid=105.GOOGL`） | — | `fetch_price_dividends.py` |
| 内部人交易 | **SEC EDGAR Form 4 XML**（`ownership.xml`） | 第三方汇总 | 手动/子代理 |
| 机构持仓 | 13F-HR（Pactolio / Valuesider / 各机构申报） | — | 子代理 |
| 官员投资 | OGE 披露、ProPublica 数据库、CREW | 媒体（标 `【二手转述】`） | 子代理 |

**关键字段映射（东方财富 push2 接口）**——易错，务必按此解读：

| 字段 | 含义 |
|------|------|
| `f43` | 最新价 |
| `f44` / `f45` | 当日最高 / 最低 |
| `f46` | 开盘 |
| `f57` / `f58` | 代码 / 名称 |
| `f60` | 昨收 |
| `f116` / `f117` | **总市值 / 流通市值** |
| `f163` | **静态 PE**（用最近年报净利） |
| `f164` | **PE(TTM)** |
| `f167` | **市净率** |

> 校验方法：用 `f116 ÷ f43` 反推总股本，与财报口径比对；用 `f163` 反推净利，与年报净利比对。**能对上才用，对不上说明字段含义变了。**

**SEC EDGAR 的两个必备请求头**（缺一会返回 403 或 JSON 解析失败）：

```python
headers = {'User-Agent': 'Research research@example.com'}           # www.sec.gov
headers = {'User-Agent': 'Research research@example.com', 'Host': 'data.sec.gov'}  # data.sec.gov
```

⚠️ **常见陷阱**：`data.sec.gov` 的接口如果误带 `Host: www.sec.gov`，会返回非 JSON 内容导致 `JSONDecodeError`。两个域名必须在同一个请求里配对自己的 Host。

### A股

| 用途 | 首选 | 备选 |
|------|------|------|
| 财务摘要（多期） | `ak.stock_financial_abstract(symbol='603986')` | — |
| 财务指标（含 ROE、毛利率、净利率） | `ak.stock_financial_analysis_indicator(symbol='603986', start_year='2020')` | — |
| 三大报表 | `ak.stock_financial_report_sina(stock='sh603986', symbol='资产负债表')` | — |
| 行情 | `ak.stock_zh_a_hist(symbol, period='daily', adjust='qfq')` | ✅ **`ak.stock_zh_a_daily(symbol='sh603986')`（新浪，稳定，含流通股本）**；`ak.stock_zh_a_hist_tx`（腾讯） |
| 估值历史 | ✅ `ak.stock_zh_valuation_baidu(symbol, indicator='市盈率(TTM)', period='近五年')` | — |
| 分红 | ✅ `ak.stock_fhps_detail_em(symbol='603986')` | — |
| 股东户数 | ✅ `ak.stock_zh_a_gdhs_detail_em(symbol='603986')` | — |

⚠️ **A股最重要的现实问题：东方财富 `push2his` / `push2` 域名会间歇性代理阻断**（本 skill 编写时实测 `stock_zh_a_hist`、`stock_individual_info_em`、`stock_zh_a_spot_em` 同时失败，而新浪与腾讯接口正常）。**因此脚本必须实现"东财 → 新浪 → 腾讯"三级回退**，不能只依赖东财。

**A股特有口径**：
- 代码前缀：沪市 `sh`、深市 `sz`（新浪接口需要前缀，东财不需要）。
- 前复权（`qfq`）是历史价格分析的默认口径；写报告时必须注明复权方式。
- "归母净利润"与"扣非归母净利润"**都要给**——后者是 A股版的"核心利润"。
- 涨跌停制度会扭曲短期波动统计，4.6 节需说明。

### 港股

| 用途 | 首选 |
|------|------|
| 财务指标 | ✅ `ak.stock_financial_hk_analysis_indicator_em(symbol='00700', indicator='年度')` |
| 三大报表 | ✅ `ak.stock_financial_hk_report_em(stock='00700', symbol='资产负债表', indicator='年度')` |
| 估值历史 | ✅ `ak.stock_hk_valuation_baidu(symbol='00700', indicator='总市值', period='近五年')` |
| 行情 | `ak.stock_hk_hist(...)`（东财，可能被阻断） | ✅ **`ak.stock_hk_daily(symbol='00700')`（新浪，稳定）** |
| 分红 | ✅ `ak.stock_hk_dividend_payout_em(symbol='00700')` |
| 权益披露 | HKEX 披露易（CCASS / 权益披露） | 子代理 |

**港股特有口径**：
- 财报为**半年报 + 年报**，没有 A股式的季度报表；单季数据需自行从半年报拆分或标 `【推算】`。
- 报告货币可能是港币、人民币或美元，**必须在表头注明**，跨公司比较时不得混用。
- 港股无涨跌停，波动统计可与其他市场横向比较。

---

## 三、货币与单位约定

- 美股统一用**美元**，单位"十亿美元"（表格）与"亿美元"（正文）二选一，全篇一致。
- A股用**人民币**，单位"亿元"。
- 港股按公司报告货币，若与股价货币不同（如报表为美元、股价为港币），**估值章节必须同时给出换算过程**。
- 任何跨市场对比（同业估值表）必须统一到同一货币，并在表头注明汇率与取数日。

---

## 四、市场特定的估值注意事项

| 市场 | 要额外注意的 |
|------|------------|
| 美股 | ①大量公司有大额股权激励（SBC），需评估稀释；②回购是主要的股东回报手段，要算清"回购 − 增发 − SBC"的净效果；③GAAP 与 Non-GAAP 差异常很大 |
| A股 | ①"扣非净利"是主口径；②大股东质押与减持规则影响供给；③高送转会改变股本，历史价格必须复权；④政府补贴与税收优惠可能贡献可观利润，需在盈利质量一节剥离 |
| 港股 | ①老千股/停牌风险，需先确认流动性与审计意见；②AH 两地上市的公司要说明两地价差；③部分公司为同股不同权，需说明投票权结构 |

---

## 五、Preflight 检查清单

对目标市场逐项确认，全部通过才进入 Phase 2：

- [ ] 网络可访问至少一个行情源
- [ ] 至少一个财报源返回 ≥5 个财年的数据
- [ ] 行情序列覆盖 ≥5 年
- [ ] 分红历史可取（若公司从未分红，明确记录该事实）
- [ ] 已确认报告货币与单位
- [ ] 已确认是否存在多类股（若有，后续所有持仓数据必须分类）
- [ ] 美股：SEC EDGAR 可访问且能列出 8-K
- [ ] A股/港股：已确认东财接口失败时的回退源可用
