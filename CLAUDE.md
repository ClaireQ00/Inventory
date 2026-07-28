# Inventory 项目 - Claude 工作约定

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

## 改 schema 必须 sync 的三个地方（漏一处就校验对不上）

1. `sql/01_schema.sql` — MySQL 真表
2. `tools/local_validator.py::SQLITE_SCHEMA` — SQLite 镜像
3. `tools/csv_to_sql.py::DERIVED_RULES` — 派生字段（仅当字段是派生时）

派生字段默认走应用层（Python 算），不用 MySQL GENERATED COLUMN。目前唯一例外是 `delivery_order_items.short_qty`（纯行内计算）。

## 自检命令

```bash
bash scripts/run_local_validation.sh           # 真实数据
bash scripts/run_local_validation.sh --demo    # demo 假数据
```

12 步全过才算改对了。
