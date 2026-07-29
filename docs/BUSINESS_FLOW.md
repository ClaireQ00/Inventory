# 外贸订单业务流程全景图

> 一句话：一笔外贸订单从**客户询盘**到**收款入账**，要走过 **9 个节点**，涉及 **3 个角色**，填 **20 张表里的 16 张**，过 **13 步业务校验**。
>
> 这份文档是给**新人接手 / Claude 接力**用的——比 `AGENT_GUIDE.md` 更重要，因为这里讲的是**业务怎么走**，不是工具怎么调。

---

## 1. 角色与边界

本项目模拟一个小型外贸出口企业，3 个核心角色（**不是 agent，是真实世界的人**）：

| 角色 | 英文 | 负责什么 | 对应表的"主场" |
| --- | --- | --- | --- |
| 外贸业务经理 | Sales Manager | 接单 / 签合同 / 跟进发货 / 跟客户对账 | `sales_contracts` / `delivery_orders` |
| 仓库保管员 | Warehouse Keeper | 收货 / 装柜 / 实际出入库 / 报关数据 | `stock_in` / `stock_out` / `shipping_records` |
| 财务经理 | Finance Manager | 录汇率 / 确认收款 / 对账 / 月末折算 | `exchange_rates` / `receipts` |

**跨角色交接点**（容易出错的地方）：
- 业务经理 → 仓库：发货单（DO）就是"仓库备货指令"
- 仓库 → 业务经理：报关单（SH）回传 actual_qty，业务跟合同对账
- 业务经理 → 财务：合同签了，财务知道"应收多少"
- 仓库 → 财务：报关单出了，财务知道"实际货值多少"
- 财务 → 业务经理：收款到账，业务经理知道"可以放下一船了"

---

## 2. 完整流程图（9 个节点）

```
   [节点1] 询盘 PI ───────────── 业务经理 ────────── (口头/邮件, 不进表)
       │
       ▼
   [节点2] 接单签 SC ─────────── 业务经理 ────────── sales_contracts + sales_contract_items
       │                                            过 check 4 (合同金额=明细之和)
       │                                            过 check 11 (合同币种当月有汇率)
       ▼
   [节点3] 下采购单 PO ────────── 业务经理 ────────── purchase_orders + purchase_order_items
       │                                            过 check 2 (采购金额=明细之和)
       ▼
   [节点4] 供应商到货 ─────────── 仓库保管员 ─────── stock_in + stock_in_items
       │                                            过 check 3 (入库 ≤ 采购)
       │                                            过 check 6 (累计出 ≤ 累计入)
       │                                            过 check 7 (库存对账)
       ▼
   [节点5] 客户要货, 下 DO ────── 业务经理 ────────── delivery_orders + delivery_order_items
       │                                            过 check 5 (发货 ≤ 合同)
       │                                            过 check 8 (体积小计)
       ▼
   [节点6] 仓库装柜出库 ───────── 仓库保管员 ─────── stock_out + stock_out_items
       │                                            过 check 6 (累计出 ≤ 累计入)
       │                                            过 check 7 (库存对账)
       │
       │  此时 delivery_order_items.actual_quantity 回填实发数
       │  short_qty = quantity - actual_quantity (派生)
       ▼
   [节点7] 报关出口 ───────────── 仓库/报关行 ────── shipping_records + shipping_record_items
       │                                            过 check 9 (UCP600 ±5% 容差)
       │                                            过 check 11 (报关月汇率)
       ▼
   [节点8] 客户付款 ───────────── 财务经理 ────────── receipts
       │                                            过 check 12 (累计收款 ≤ 合同金额)
       │                                            过 check 11 (付款月汇率)
       ▼
   [节点9] 差异处理 ───────────── 业务+财务 ──────── credit_notes (如有短装/超装)
                                                    过 check 10 (pending ≤ 30天)
```

---

## 3. 每个节点详解（谁填什么表，过什么校验，状态怎么变）

### 节点 1：询盘（PI）

| 项 | 说明 |
| --- | --- |
| **角色** | 业务经理 |
| **触发** | 客户邮件/WhatsApp 问价 |
| **填什么表** | ❌ **不进表**（口头或邮件报价，确认了才进下一节点） |
| **业务单据** | 形式发票 PI（Proforma Invoice），类似菜单上的价格 |
| **下一步** | 客户确认 → 节点 2 |

### 节点 2：接单签销售合同（SC）

| 项 | 说明 |
| --- | --- |
| **角色** | 业务经理 |
| **填什么表** | `sales_contracts`（合同主表） + `sales_contract_items`（明细） |
| **关键字段** | `contract_no`、`customer_id`、`currency`（默认 USD）、`exchange_rate`（当期月汇率）、`total_amount`、`trade_terms`（FOB/CIF/CFR/EXW）、`port_loading`、`port_discharge` |
| **金额四件套** | `total_amount` + `currency` + `exchange_rate` + `total_amount_cny`（派生） |
| **过哪个校验** | **check 4**（合同金额 = Σ 明细小计）、**check 11**（合同币种当月有汇率） |
| **状态机** | `draft` → `confirmed` → `delivering` → `completed` / `cancelled` |
| **派生字段** | `sales_contract_items.subtotal` = 数量 × 单价（csv_to_sql 自动算） |
| **下一步** | 触发节点 3（采购） |

### 节点 3：下采购单（PO）

| 项 | 说明 |
| --- | --- |
| **角色** | 业务经理（给供应商下单） |
| **填什么表** | `purchase_orders` + `purchase_order_items` |
| **关键字段** | `po_no`、`supplier_id`、`expected_date`、`total_amount` |
| **过哪个校验** | **check 2**（采购总额 = Σ 明细小计） |
| **状态机** | `draft` → `confirmed` → `partial_received` → `completed` / `cancelled` |
| **下一步** | 供应商备货 → 节点 4（到货） |

### 节点 4：供应商到货入库

| 项 | 说明 |
| --- | --- |
| **角色** | 仓库保管员 |
| **填什么表** | `stock_in` + `stock_in_items` |
| **关键字段** | `in_no`、`in_type`（`purchase`=采购到货 / `transfer`=调拨接收，默认 `purchase`）、`warehouse_id`、`po_id`（采购到货时填）、`in_date`、`status='confirmed'`、`transfer_ref`（仅调拨接收时填，跟配对的 stock_out 同一个号） |
| **过哪个校验** | **check 3**（入库数 ≤ 采购数，仅 `purchase` 类型）、**check 6**（累计出库 vs 累计入库，**负库存允许但报警**）、**check 7**（库存对账：`inventory.quantity` = Σ stock_logs）、**check 13**（调拨配对，仅 `transfer` 类型） |
| **状态机** | `draft` → `confirmed` / `cancelled` |
| **库存影响** | 入库确认后，`inventory.quantity` 增加 |
| **下一步** | 等客户要货 → 节点 5；或接到调拨单 → 异常分支 4.4 |

### 节点 5：客户要货，下发货单（DO）

| 项 | 说明 |
| --- | --- |
| **角色** | 业务经理 |
| **填什么表** | `delivery_orders` + `delivery_order_items` |
| **关键字段** | `delivery_no`、`customer_id`、`delivery_date`、`contract_item_id`（关联合同明细）、`quantity`（计划数）、`actual_quantity`（装柜后回填） |
| **过哪个校验** | **check 5**（发货 ≤ 合同，优先用 `actual_quantity`，没装柜回退 `quantity`）、**check 8**（体积小计） |
| **状态机** | `draft` → `confirmed` → `shipped` → `delivered` / `cancelled` |
| **派生字段** | `delivery_order_items.short_qty` = `quantity - actual_quantity`（默认 0） |
| **下一步** | 仓库按 DO 备货 → 节点 6 |

### 节点 6：仓库装柜 + 出库

| 项 | 说明 |
| --- | --- |
| **角色** | 仓库保管员 |
| **填什么表** | `stock_out` + `stock_out_items`（出库）+ 回填 `delivery_order_items.actual_quantity`（销售装柜实发数） |
| **关键字段** | `out_no`、`out_type`（`sale`=销售出库 / `transfer`=调拨发出，默认 `sale`）、`warehouse_id`、`delivery_id`（销售时填）、`out_date`、`status='confirmed'`、`transfer_ref`（仅调拨发出时填，跟配对的 stock_in 同一个号） |
| **过哪个校验** | **check 6**（累计出库 vs 累计入库，**允许负库存但报警**，类比银行卡透支）、**check 7**（库存对账）、**check 13**（调拨配对，仅 `transfer` 类型） |
| **状态机** | `draft` → `confirmed` / `cancelled` |
| **库存影响** | 出库确认后，`inventory.quantity` 减少 |
| **关键动作** | 装柜后**必须**回填 `actual_quantity`，否则 `short_qty` 永远是 0，节点 7 会报错（调拨出库无此动作） |
| **下一步** | 装船报关 → 节点 7（仅销售出库走报关，调拨出库到此结束） |

### 节点 7：报关出口（SH + CI + PL）

| 项 | 说明 |
| --- | --- |
| **角色** | 仓库保管员 / 报关行 |
| **填什么表** | `shipping_records`（报关主表）+ `shipping_record_items`（明细） |
| **关键字段** | `shipping_no`、`delivery_id`、`shipping_date`、`container_no`、`total_pkgs`、`total_cbm`、`total_amount`（外币）、`currency`、`exchange_rate`、`total_amount_cny` |
| **明细必备** | `shipping_mark`（唛头）、`gross_weight_per`（毛重）、`net_weight_per`（净重）、`actual_qty`、`unit_volume` |
| **金额四件套** | `total_amount` + `currency` + `exchange_rate` + `total_amount_cny`（派生） |
| **过哪个校验** | **check 9**（UCP600 ±5% 容差：报关实际数 vs 发货计划数）、**check 11**（报关月汇率） |
| **状态机** | `draft` → `customs_cleared` → `closed` / `cancelled` |
| **派生字段** | `shipping_record_items.subtotal_usd` = `actual_qty × unit_price_usd` |
| **下一步** | 客户付款 → 节点 8；如果短装/超装 → 节点 9 |

### 节点 8：客户付款入账

| 项 | 说明 |
| --- | --- |
| **角色** | 财务经理 |
| **填什么表** | `receipts` |
| **关键字段** | `receipt_no`、`customer_id`、`contract_id`、`amount`（外币）、`currency`、`exchange_rate`（按 `paid_date` 所在月查汇率表）、`amount_cny`、`paid_date`、`pay_method`（T/T 默认）、`bank_ref`（水单号）、`status='confirmed'` |
| **金额四件套** | `amount` + `currency` + `exchange_rate` + `amount_cny`（派生） |
| **过哪个校验** | **check 12**（累计收款 ≤ 合同金额，币种必须一致）、**check 11**（付款月有汇率） |
| **状态机** | `draft` → `confirmed` / `cancelled` |
| **前置条件** | 每月 1 日财务先录 `exchange_rates`（月固定汇率），否则 check 11 直接报 ERROR |
| **下一步** | 收款跟报关对齐 → 订单闭环；如有差异 → 节点 9 |

### 节点 9：差异处理（Credit Note，可选）

| 项 | 说明 |
| --- | --- |
| **角色** | 业务经理 + 财务经理 |
| **触发** | 节点 7 报关数 ≠ 节点 5 发货数（短装 / 超装） |
| **填什么表** | `credit_notes` |
| **关键字段** | `cn_no`、`shipping_id`、`contract_item_id`、`product_id`、`diff_qty`（正=短装 负=超装）、`diff_amount`、`currency`、`exchange_rate`、`diff_amount_cny`、`resolution`、`resolved_at` |
| **金额四件套** | `diff_amount` + `currency` + `exchange_rate` + `diff_amount_cny`（派生） |
| **过哪个校验** | **check 10**（`pending` 状态不能挂账超 30 天，>30 WARN，>90 ERROR） |
| **resolution 四种** | `pending`（待定）/ `replenish`（下次补发）/ `refund`（退款）/ `writeoff`（注销） |
| **闭环** | 必须 把 `pending` 推进到另外 3 种之一，否则超期报警 |

---

## 4. 异常分支（流程没走顺怎么办）

### 4.1 短装 / 超装（节点 7 触发节点 9）

```
节点 6 装柜: 计划 100, 实装 95
    │
    ▼
节点 7 报关: actual_qty = 95
    │
    ├─ check 9 判定: |95-100|/100 = 5% ≤ 5% → WARN (允许, 但要记录)
    │              或 |95-100|/100 > 5%      → ERROR (必须挂 credit_note)
    │
    ▼
节点 9 credit_note: diff_qty = 5 (短装), resolution = 'pending'
    │
    ├─ 决定下次补发 → resolution = 'replenish' + resolved_at = 日期
    ├─ 决定退款    → resolution = 'refund'     + resolved_at = 日期
    └─ 决定注销    → resolution = 'writeoff'   + resolved_at = 日期

    如果挂 30 天没处理 → check 10 WARN
    如果挂 90 天没处理 → check 10 ERROR
```

### 4.2 跨月交易（汇率变动）

```
合同月: 2026-07, USD 汇率 7.15
    │
    ▼
报关月: 2026-07, 用 7.15 折算 → 跟合同对齐 ✓
    │
    ▼
付款月: 2026-08, 用 7.18 折算 → 汇率变了!
    │
    └─ 结果: 收款人民币 ≠ 合同人民币, 差额 = 汇兑损益
       (当前阶段只记录, 不做月末结转; 第 2 阶段在 payment-receivable skill 第 7 节规划)
```

**铁律**：跨月交易用 `paid_date` 所在月的汇率，**不是合同月**。

### 4.3 多合同合并付款

当前阶段：一个 receipt 只关联一个 `contract_id`，不支持合并。
第 2 阶段规划：加 `receipt_allocations` 子表（见 `payment-receivable/SKILL.md` 第 7 节）。

### 4.4 仓库间调拨（平行于主线，可随时发生）

主线讲的是"客户下单 → 出口收钱"流程，调拨是**仓库之间的内部挪货**，跟销售无关，所以可以平行发生于任意时刻（比如把主仓的货挪到外协仓、或挪到口岸附近的临时仓）。

```
仓库 A（源仓）: stock_out  out_type='transfer',  transfer_ref='TR20260729001'
                                                                        ↓ 同一个号串起来
仓库 B（目标仓）: stock_in   in_type='transfer',   transfer_ref='TR20260729001'
                                                                        ↓
                              check 13 聚合两边数量对比
                              出库总量 ≠ 入库总量 → ERROR
                              只有一边              → WARN (在途或漏录)
```

**关键约定**：
- 调拨的两条单据**必须填同一个 `transfer_ref`**（编号建议 `TR + 日期 + 序号`，如 `TR20260729001`）
- 调拨**不走节点 7 报关**（不产生报关单、不涉及 UCP600）
- 调拨**不走节点 8 收款**（不涉及外币、汇率、credit_note）
- source 仓允许暂时负库存（**check 6 是 WARN 不是 ERROR**），后续补货即可
- 业务规则细节见 `docs/BUSINESS_RULES.md` R3.5

---

## 5. 三角色交接矩阵（防扯皮）

| 交接点 | 交接物 | 谁给谁 | 关键字段必须对齐 |
| --- | --- | --- | --- |
| 询盘→接单 | PI 形式发票 | 业务经理 → 客户 | 报价币种 / 交期 |
| 接单→采购 | 销售合同内部同步 | 业务经理 → 自己 | 合同数量 / 物料号 |
| 采购→到货 | 采购单 | 业务经理 → 供应商 + 仓库 | `expected_date` |
| 到货→入库 | 送货单 | 供应商 → 仓库 | 实收数量 |
| 要货→发货 | DO 发货单 | 业务经理 → 仓库 | `quantity` / `contract_item_id` |
| 装柜→报关 | 装柜清单 | 仓库 → 报关行 | `actual_qty` / 毛净重 / 唛头 |
| 报关→收款 | CI + 报关单 | 仓库 → 财务 + 客户 | `total_amount` / 币种 |
| 收款→对账 | 水单 | 客户 → 财务 → 业务经理 | 到账金额 / 币种 / 日期 |
| 差异→处理 | credit_note | 业务+财务 → 客户 | `diff_qty` / `resolution` |

---

## 6. 给新人的"第一天"操作清单

假设你要用本项目跑一笔真实订单，按这个顺序做：

1. **月初录汇率**：财务在 `data/csv/exchange_rates.csv` 加一条本月汇率
2. **确认基础资料**：`data/csv/products.csv` / `warehouses.csv` / `suppliers.csv` / `customers.csv` 齐全
3. **录合同**：业务经理填 `sales_contracts.csv` + `sales_contract_items.csv`（金额四件套别漏）
4. **录采购**：业务经理填 `purchase_orders.csv` + `purchase_order_items.csv`
5. **跑一次校验**：`bash scripts/run_local_validation.sh`（应该 1-4 步过，5-13 步因为没数据跳过）
6. **后续按节点 4→9 顺序补数据，每补一个节点跑一次校验**

**第一次跑必看**：`docs/VALIDATION_GUIDE.md`（生动版校验流程说明）。

---

## 7. 相关文档

| 想了解 | 看哪份文档 |
| --- | --- |
| 系统整体架构 | `docs/README.md` |
| 13 步校验细节 | `docs/VALIDATION_GUIDE.md` |
| Skill / Agent / Hook 体系 | `docs/AGENT_GUIDE.md` |
| 字段派生规则（外径 / 体积 / 金额） | `.claude/skills/derived-fields/SKILL.md` |
| 产品参数（密度 / 厚度反推） | `.claude/skills/product-params/SKILL.md` |
| 外贸单据（报关 / 短装 / UCP600） | `.claude/skills/trade-documents/SKILL.md` |
| 应收收款（汇率 / 水单 / 对账） | `.claude/skills/payment-receivable/SKILL.md` |
| 敏感数据隔离 | `docs/PRIVATE_DATA_GUIDELINES.md` |
| 导入模板清单 | `docs/IMPORT_TEMPLATES.md` |
