# company-deep-analysis（plugin）

Claude Code 插件封装：内含 `skills/company-deep-analysis`。

- **skill 本体**：[`skills/company-deep-analysis/SKILL.md`](skills/company-deep-analysis/SKILL.md)
- **完整文档**：[仓库根 README](../../README.md)
- **范例报告**：[`skills/company-deep-analysis/assets/example-report-google-20261008.md`](skills/company-deep-analysis/assets/example-report-google-20261008.md)

## 安装

```
/plugin marketplace add ykangli/company-deep-analysis
/plugin install company-deep-analysis@company-deep-analysis
```

## 这个 skill 做什么

输入一家上市公司（美股 / A股 / 港股），输出固定 12 章结构的中文深度分析报告，并以《买入检查清单》16 问为骨架逐条作答。核心约束：**每个承重数字必须可追溯到一手来源，全文按 `【已核实】/【推算】/【未能核实】` 分级，交付前必须通过阻断式校验器**。

覆盖：近五年财报、估值与反向 DCF、近期股价、分红回购、股东结构与名人持仓（含持仓时间与成本）、内部人交易、近期大事件、高管访谈、白宫官员投资（仅美股）、未来发展三情景、投资安全边际与价格纪律。

## 依赖

```bash
pip install pandas requests akshare beautifulsoup4 lxml
```

首次使用建议先跑：

```bash
python skills/company-deep-analysis/scripts/preflight.py --market us --symbol GOOGL
```

## 免责声明

研究辅助工具。基于公开信息生成报告，不构成任何证券的买卖建议；使用前请对关键数字与发行人正式披露自行复核。
