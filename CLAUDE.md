# Inventory 项目 - Claude 工作约定

## SDD 文档体系（规格先行,2026-07-29 建立）

开发前先查对应文档,它们是事实源:

| 要找什么 | 看哪个文档 |
| --- | --- |
| 术语定义 | `docs/GLOSSARY.md` |
| 业务规则（铁律） | `docs/BUSINESS_RULES.md` (R1~R11) |
| 数据表/字段/ER/派生 | `docs/DATA_MODEL.md` |
| 功能需求+验收标准 | `docs/SPECS.md` |
| 技术设计+决策理由 | `docs/DESIGN.md` + `docs/adr/` |
| 待办任务（claude-driver 输入） | `docs/TASKS.md` |
| 端到端验收场景 | `docs/SCENARIOS.md` |

> ⚠️ `docs/CLAUDE_BRIEF.md` 已被 `docs/TASKS.md` 取代,仅留作历史,不要再参考。

## 这个项目是什么

外贸出口企业的进销存 + 报关单据 + 应收收款系统。当前用印尼客户 Q025（PVC 线管）当样本跑通端到端流程，后续会接其他地区/品类的客户。

**不要把项目锁死在样本上**：管材/PVC/印尼只是当前联调数据，客户/币种/口岸/产品品类都是数据不是硬编码。加新品类在 `tools/csv_to_sql.py::DENSITY_RULES` 加一条公式即可，不要新建 skill。

## 四个 skill 怎么分（路由互斥）

| 用户问到 | 用哪个 skill |
| --- | --- |
| 密度 / 厚度反推 / 米重 / 内径 | `product-params` |
| 外径 / 体积 / 金额小计（行内派生） | `derived-fields` |
| 报关 / 短装 / 唛头 / UCP600 / credit_note | `trade-documents` |
| 收款 / 汇率 / 水单 / T/T / 应收对账 | `payment-receivable` |

## 金额四件套铁律（2026-07-28 加）

凡是外币金额必须同时有 4 个字段，缺一个就报错：

```
amount + currency + exchange_rate + amount_cny
```

- **币种默认 USD**，记账本位币是 CNY
- **汇率月固定**：每月 1 日录一次 `exchange_rates`，整月用这条
- **跨月交易**：用 `paid_date` 所在月的汇率，不是合同月
- **amount_cny 永远派生**：`tools/csv_to_sql.py::DERIVED_RULES` 自动算，不要手填
- 影响表：`sales_contracts` / `shipping_records` / `credit_notes` / `receipts`

## 改 schema 必须 sync 的四个地方（漏一处就校验对不上）

1. `sql/01_schema.sql` — MySQL 真表
2. `tools/local_validator.py::SQLITE_SCHEMA` — SQLite 镜像
3. `tools/csv_to_sql.py::DERIVED_RULES` — 派生字段（仅当字段是派生时）
4. `sample/templates/<表名>_template.csv` — CSV 模板表头（2026-07-30 真实数据试用踩坑后补，第 4 处由 `scripts/check-template-schema-sync.sh` 自动兜底）

派生字段默认走应用层（Python 算），不用 MySQL GENERATED COLUMN。目前唯一例外是 `delivery_order_items.short_qty`（纯行内计算）。

## 自检命令

## 快照重量链路铁律（2026-08-01 加，详见 ADR-0005）

- 报价明细 `weight_per_unit` 是**快照**（从 `products.weight` 带出可覆盖）：谈价改重量只改行上快照，**永不回写主数据**
- 分阶段提醒：brief/draft 可偏离（普通 WARN）；formal/converted 强提醒归位物料编码（`[正式报价须归位]`）
- R11 反算取数**快照优先**：converted 报价快照 > 同客户最新报价（非 draft 优先）> 主数据；fallback 必须同客户过滤
- 归位用 `tools/clone_material.py`（`--update-quote` / `--update-contract`）；合同已发货历史行不动（历史真相）
- `delivered_qty` 由第 5 步校验回写，只有跑过校验才可信

## 自检命令

```bash
bash scripts/run_local_validation.sh           # 真实数据
bash scripts/run_local_validation.sh --demo    # demo 假数据
```

16 步全过才算改对了。校验前会自动跑 `tools/normalize_csv.py`（步骤 2c），把 Excel 编辑引入的 GBK/CRLF/多行字段问题自动修复，**填完 CSV 直接跑校验即可，不用手动管编码**（详见 `docs/IMPORT_TEMPLATES.md` 坑 5）。

## 多 agent 并行协作约定（2026-08-01 踩坑后加）

- **提交时只 `git add` 明确路径，永远不用 `git add -A` / `git add .`**——别的 agent 可能有半成品在工作区，`-A` 会把别人的活卷进你的 commit
- 同一时间只让一个 agent 改 `tools/` 下的代码，避免互相覆盖
- 工作区不干净时（有别的 agent 的未提交改动），不要跑 `scripts/claude-driver.sh`（它要求干净工作区，且每轮自动 commit）
