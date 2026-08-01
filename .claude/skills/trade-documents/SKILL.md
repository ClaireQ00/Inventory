---
name: trade-documents
description: 进销存项目的外贸单据规则集。当用户处理 PI/CI/PL/B/L/CO/报关单/信用证等单据, 问到"形式发票"、"商业发票"、"装箱单"、"提单"、"唛头"、"HS 编码"、"FOB/CIF/EXW"、"短装"、"Short Shipment"、"超装"、"Over Shipment"、"虚标/虚重"、"L/C 单证相符"、"UCP600 ±5% 容差"、"credit_note"、"贷记单" 时使用此 skill。涉及 tools/local_validator.py 的 check_shipping_vs_delivery / check_credit_notes_balance, 以及 sql/01_schema.sql 的 shipping_records / shipping_record_items / credit_notes 三张表。注意: 涉及产品参数(密度/厚度/米重)请改用 product-params skill; 涉及行内派生字段(外径/体积/金额小计)请改用 derived-fields skill。
allowed-tools: Read, Grep, Glob, Bash(python3:*)
---

# 外贸单据 · 完整规则集

## ⏱️ 5 分钟速查卡（没时间就只看这 3 条）

1. **铁律**：合同账（承诺值）和报关账（实际值）允许 **±5% 差异**（UCP600），**不要试图"统一"两套账**，差异用 `credit_note` 衔接
2. **必看**：报关必填字段 **唛头 / 毛重 / 净重 / 件数 / CBM**，缺一不可报关（`shipping_record_items` 表）
3. **闪人**：如果是收款 / 汇率 / 水单 → `payment-receivable`；如果是密度 / 厚度 → `product-params`

---

## 谁会用这个 skill

| 角色 | 关心什么 | 重点看哪节 |
| --- | --- | --- |
| 外贸业务经理 | 签合同 / 改合同数量 / 跟客户对账 | §3 两套账、§4 UCP600 ±5% 容差 |
| 仓库保管员 | 装柜填 actual_qty / 出库 | §6 报关必备字段、§3 字段对照表 |
| 报关行 | 做 CI / PL / B/L 单据 | §2 名词词典、§6 报关字段、§7 短装场景 |
| 财务经理 | credit_note 闭环、对账 | §5 credit_note 4 种 resolution |

## 一句话总结

外贸订单有 **两套并行的账**：合同账（承诺值，给客户/财务看）和 报关账（实际值，给海关/银行看），两套账允许 **±5% 差异**（UCP600 国际惯例），差异用 `credit_note` 衔接。

---

## 1. 单据流程一览（按时间排序）

| 阶段 | 中文 | 英文缩写 | 触发时机 | 数据性质 | 对应表 |
| --- | --- | --- | --- | --- | --- |
| 询盘 | 形式发票 | PI (Proforma Invoice) | 客户询价 | 承诺（报价） | - |
| 接单 | 销售合同 | SC (Sales Contract) | 双方签字 | 承诺（合同） | `sales_contracts` |
| 排产 | 采购单 | PO (Purchase Order) | 接单后采购 | 承诺（采购） | `purchase_orders` |
| 发货预演 | 装箱计划 | Packing Plan | 装柜前 7-10 天 | 预估 | - |
| 内部指令 | 发货单 | DO / DN (Delivery Order/Note) | 装柜前 1-2 天 | 指令（计划数） | `delivery_orders` |
| 实际装柜 | 出库单 | SO (Stock Out) | 装柜中 | 实际 | `stock_out` |
| 报关出口 | 报关单据 | SH + CI + PL | 装船时 | 实际（报关） | `shipping_records` |
| 差异处理 | 贷记单 | CN (Credit Note) | 对账时 | 差异 | `credit_notes` |

**关键节点**：发货单（合同账）→ 报关单（报关账）之间允许 ±5% 偏差。

---

## 2. 业务名词词典（新手友好版）

| 中文 | 英文/缩写 | 含义 | 类比 |
| --- | --- | --- | --- |
| 形式发票 | PI | 报价单 | 菜单上的价格 |
| 商业发票 | CI (Commercial Invoice) | 报关发票 | 结账小票 |
| 装箱单 | PL (Packing List) | 货物清单 | 快递里的物品清单 |
| 提单 | B/L (Bill of Lading) | 物权凭证 | 房产证 |
| 原产地证 | CO (Certificate of Origin) | 产地证明 | 身份证 |
| 短装 | Short Shipment | 实际装 < 计划 | 点 100 个饺子只上了 95 个 |
| 超装 | Over Shipment | 实际装 > 计划 | 给多了 |
| 唛头 | Shipping Mark | 包装外字 | 快递面单上的姓名 |
| 毛重 | Gross Weight | 含包装重量 | 戴盒子的体重 |
| 净重 | Net Weight | 不含包装 | 裸重 |
| 虚标 | Virtual Mark | 单据写比实际大 | 银行流水夸大 |
| 信用证 | L/C (Letter of Credit) | 银行担保付款 | 支付宝担保交易 |

---

## 3. "两套账"核心机制

```
   ┌───────────── 合同账 (承诺值, 给客户/财务看) ─────────────┐
   │                                                          │
   │  sales_contracts (合同数量)                              │
   │         │                                                │
   │         ▼                                                │
   │  delivery_orders + delivery_order_items                  │
   │  (quantity = 计划发货数 = 商务承诺)                       │
   │                                                          │
   └────────────────────────┬─────────────────────────────────┘
                            │
                            │ 装柜后实发数 actual_quantity
                            │ 可能 != quantity (短装/超装)
                            ▼
   ┌───────────── 报关账 (实际值, 给海关/银行看) ──────────────┐
   │                                                          │
   │  shipping_records + shipping_record_items                │
   │  (actual_qty = 实际装柜数, 用于做 CI + PL)               │
   │         │                                                │
   │         ▼                                                │
   │  credit_notes (差异处理: 短装/超装 闭环)                 │
   │                                                          │
   └──────────────────────────────────────────────────────────┘
```

**字段对照**：

| 合同账字段 | 报关账字段 | 含义 |
| --- | --- | --- |
| `delivery_order_items.quantity` | `shipping_record_items.planned_qty` | 计划数 |
| `delivery_order_items.actual_quantity` | `shipping_record_items.actual_qty` | 实际装柜数 |
| `delivery_order_items.short_qty` | (派生) | 短装数 = 计划 - 实际 |

---

## 4. ±5% 容差规则（UCP600 第 30 条）

**代码常量**：`tools/local_validator.py::SHORT_SHIPMENT_TOLERANCE = 0.05`

**校验函数**：`check_shipping_vs_delivery()` （步骤 10/16）

```
ratio = |actual - planned| / planned

ratio ≤ 5%  → WARN  (UCP600 允许的合理误差, 但要在 credit_note 里记录)
ratio > 5%  → ERROR (违反 UCP600, 必须补 credit_note 否则海关/银行拒收)
```

**类比**：你点了 100 个饺子，餐厅上了 95~105 个都算正常（±5%）；但只上了 90 个就过分了，得补差价（credit_note）。

**适用范围**：
- 发货单 `quantity` → 报关单 `actual_qty`
- 销售合同 `quantity` → 发货单 `actual_quantity`

---

## 5. credit_note 闭环

`credit_notes.resolution` 有 4 种状态：

| 状态 | 含义 | 何时用 |
| --- | --- | --- |
| `pending` | 待处理 | 刚发现差异，还没决定怎么办 |
| `replenish` | 补发 | 答应下一船补上短装的数 |
| `refund` | 退款 | 不补了，退钱给客户 |
| `writeoff` | 注销 | 差异小或客户不要了，直接销账 |

**闭环校验**：`check_credit_notes_balance()` （步骤 11/16）

```
resolution = 'pending' 且 created_at 距今 > 30 天 → WARN  (催办)
resolution = 'pending' 且 created_at 距今 > 90 天 → ERROR (严重逾期)
```

**闭环流程**：

```
发现短装 (5 件)
      │
      ▼
创建 credit_note (resolution='pending')
      │
      ├──→ 决定补发 ──→ resolution='replenish' + resolved_at=日期
      │
      ├──→ 决定退款 ──→ resolution='refund'     + resolved_at=日期
      │
      └──→ 决定注销 ──→ resolution='writeoff'   + resolved_at=日期
```

**类比**：客户少收的 5 件货，你说"回头补"，但拖了 3 个月还没补，财务就要炸了——必须强制 close。

---

## 6. 报关必备字段（缺一不可）

`shipping_record_items` 表里这 5 个字段是报关硬性要求：

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `shipping_mark` | 唛头 | "PAGODA / C-001 / SH20260726001" |
| `gross_weight_per` | 单件毛重 (kg) | 12.80 |
| `net_weight_per` | 单件净重 (kg) | 11.50 |
| `actual_qty` | 实际件数 | 95 |
| `unit_volume` | 单件体积 (CBM) | 0.0446 |

**派生金额**：`subtotal_usd = actual_qty × unit_price_usd`（在 `tools/csv_to_sql.py::DERIVED_RULES["shipping_record_items"]`）

---

## 7. 短装场景实操示例

**场景**：销售合同 100 件，发货单计划 100，实际装柜 95，短装 5 件用 credit_note 处理。

**数据准备**（5 张表）：

```csv
# 1. sales_contract_items (合同 100 件)
id=3, contract_id=1, product_id=1, quantity=100, delivered_qty=0

# 2. delivery_order_items (计划 100, 实际 95, 短装 5)
id=3, delivery_id=2, contract_item_id=3, product_id=1,
quantity=100, actual_quantity=95, short_qty=5

# 3. shipping_records (报关单)
id=2, shipping_no='SH20260727001', delivery_id=2, total_pkgs=95

# 4. shipping_record_items (实际 95, planned 100)
id=3, shipping_id=2, product_id=1, planned_qty=100, actual_qty=95
# → 校验: |95-100|/100 = 5%, 正好等于容差, 报 WARN (不报 ERROR)

# 5. credit_notes (5 件短装 → 补发)
id=1, cn_no='CN20260727001', shipping_id=2, contract_item_id=3,
product_id=1, diff_qty=5, diff_amount=1000, resolution='replenish',
resolved_at='2026-08-15'
```

**校验结果**：
- 步骤 5（发货 vs 合同）：实际 95 < 合同 100 → WARN "未发完"
- 步骤 10（报关 vs 发货）：5% 偏差，正好临界 → WARN
- 步骤 11（credit_note 闭环）：已 `replenish` 不算 pending → 不报

---

## 8. 给 Claude 自己的提醒

- ✅ **短装/超装是常态**，不要试图"统一"两套账，要让差异可追溯
- ✅ **报关必填字段**：唛头 / 毛重 / 净重 / 件数 / CBM，缺一不可
- ✅ 改发货单 `actual_quantity` 时，`short_qty` 自动算（MySQL 用 GENERATED COLUMN，SQLite/csv_to_sql 用应用层算）
- ✅ credit_note 的 `diff_qty` 正数=短装，负数=超装（统一一个字段表达方向）
- ❌ **不要**把发货单 `quantity` 改成实际数，那是商务承诺，要保留原值
- ❌ **不要**用 MySQL GENERATED COLUMN 跨表（本项目风格，所有派生只在行内或应用层）
- ❌ **不要**把"虚标"（虚报重量）当成正常业务，那是违规
- ➡️ 涉及密度/厚度/米重 → `product-params` skill
- ➡️ 涉及外径/体积/金额派生 → `derived-fields` skill
- ➡️ 涉及**仓库间调拨**（`out_type='transfer'` / `in_type='transfer'`，靠 `transfer_ref` 配对）→ **不在本 skill 范围**。调拨是仓库内部挪货，**不走信用证/短装/credit_note 流程**，由 `local_validator.py::check_transfer_pairs` 第 14 步校验。规则见 `docs/BUSINESS_RULES.md §R3.5`

---

## 9. 完整单据流转流程图

```
   客户询价
       │
       ▼
   ┌───────┐
   │  PI    │  形式发票 (承诺价格)
   └───┬───┘
       │ 双方确认
       ▼
   ┌───────┐
   │  SC    │  销售合同 (承诺数量+金额)  ──→ sales_contracts
   └───┬───┘
       │
       ▼
   ┌───────┐
   │  PO    │  采购单 (给供应商)       ──→ purchase_orders
   └───┬───┘
       │ 到货
       ▼
   ┌───────┐
   │ Stock In │  入库                  ──→ stock_in
   └───┬───┘
       │ 客户要货
       ▼
   ┌───────┐
   │  DO    │  发货单 (计划数)          ──→ delivery_orders
   └───┬───┘
       │ 装柜
       ▼
   ┌───────┐
   │ Stock Out │ 出库 (实际数)         ──→ stock_out
   └───┬───┘
       │ 装船报关
       ▼
   ┌───────┐
   │ SH+CI+PL │ 报关单据 (实际数)      ──→ shipping_records
   └───┬───┘
       │ 发现差异 (短装/超装)
       ▼
   ┌───────┐
   │  CN    │  贷记单 (差异处理)       ──→ credit_notes
   └───────┘
```

---

## 🔗 跨 skill 协作场景

### 场景 1：短装 + 退款（trade-documents → payment-receivable）

**触发**：装柜时短装 5 件，客户要求退款（不补发）

**协作顺序**：
1. 先用 **trade-documents**（本 skill）创建 `credit_notes` 记录差异：`diff_qty=5`、`resolution='refund'`、`diff_amount`（原币种差额）
2. 再用 **payment-receivable** 用 `credit_notes.diff_amount` 折算 CNY（`diff_amount_cny = diff_amount × exchange_rate`），并跟 `receipts` 对账

**举例**：合同 100 件 × USD 200 = USD 20000，实发 95 件，短装 5 件
- Step 1（trade-documents）：credit_note `diff_qty=5, diff_amount=1000 USD, resolution=refund`
- Step 2（payment-receivable）：diff_amount_cny = 1000 × 7.15 = 7150 CNY；后续 receipts 里减掉这笔

### 场景 2：报关后收款对账（trade-documents → payment-receivable）

**触发**：装船报关后，客户付款，财务对账

**协作顺序**：
1. trade-documents 出 `shipping_records`（含 `total_amount` 外币金额四件套）
2. payment-receivable 用 `receipts.amount` 累计跟 `shipping_records.total_amount` 对账，±5% 容差

### 场景 3：装柜时算报关体积（derived-fields → trade-documents）

**触发**：装柜做 CI / PL 单据

**协作顺序**：
1. derived-fields 算出 `products.volume` 和 `delivery_order_items.volume_subtotal`
2. trade-documents 把单件体积带到 `shipping_record_items.unit_volume`（报关必备字段之一）

---

## 10. 相关文件索引

| 文件 | 作用 |
| --- | --- |
| `sql/01_schema.sql` | `shipping_records` / `shipping_record_items` / `credit_notes` 表定义；`delivery_order_items.actual_quantity/short_qty` 字段 |
| `tools/local_validator.py` | `SHORT_SHIPMENT_TOLERANCE = 0.05` 常量；`check_shipping_vs_delivery` (步骤 10)；`check_credit_notes_balance` (步骤 11)；`check_delivery_vs_contract` (步骤 5 已改为优先用 actual_quantity) |
| `tools/csv_to_sql.py` | `DERIVED_RULES["delivery_order_items"]["short_qty"]`；`DERIVED_RULES["shipping_record_items"]["subtotal_usd"]` |
| `sample/templates/shipping_records_template.csv` | 报关单录入模板 |
| `sample/templates/shipping_record_items_template.csv` | 报关明细录入模板 |
| `sample/templates/credit_notes_template.csv` | 贷记单录入模板 |
| `sample/templates/delivery_order_items_template.csv` | 发货明细模板（含 actual_quantity/short_qty） |
| `data/csv/demo/shipping_records.csv` | demo 数据 |
| `data/csv/demo/shipping_record_items.csv` | demo 数据 |
| `data/csv/demo/credit_notes.csv` | demo 数据（默认空，演示正常场景） |
