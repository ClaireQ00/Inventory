# 端到端验收场景 (End-to-End Acceptance Scenarios)

> 每个**场景**对应 14 步校验里的一步或几步，给出**可复现的输入 + 明确的预期结果**（ERROR / WARN / 通过）。所有数据基于 `tools/make_demo_data.py` 真实生成的 demo 数据（物料号 `DEMO-*`、客户"客户A/B"、汇率 7.15），不臆造。
>
> 验收口径：跑完每个场景的"操作步骤"后，执行 `bash scripts/run_local_validation.sh --demo`，对照"预期结果"列逐条核对。14 步含义见 `docs/VALIDATION_GUIDE.md §3`，校验代码逻辑见 `tools/local_validator.py`。

---

## 0. 阅读约定

### 0.1 三态标记

| 标记 | 含义 | 对应代码 |
| --- | --- | --- |
| **通过** | 该步无 ERROR 也无 WARN | `ValidationReport.ok == True` 且无相关条目 |
| **WARN** | 黄灯，提醒但不阻断流程 | `report.warn(...)`；最终 `exit 0`（除非同时有别的 ERROR） |
| **ERROR** | 红灯，必须修；最终 `exit 1` | `report.error(...)`；`ValidationReport.ok == False` |

### 0.2 14 步速查（详细见 VALIDATION_GUIDE §3）

| 步 | 校验函数 | 一句话 |
| --- | --- | --- |
| 1 | `check_master_data` | 基础资料完整性 |
| 2 | `check_purchase_orders` | 采购金额 = 明细之和 |
| 3 | `check_stock_in_vs_purchase` | 入库 ≤ 采购 |
| 4 | `check_sales_contracts` | 合同金额 = 明细之和 |
| 5 | `check_delivery_vs_contract` | 发货 ≤ 合同 |
| 6 | `check_stock_out_vs_inventory` | 累计出 vs 累计入（WARN 级负库存） |
| 7 | `check_reconciliation` | 库存表 = 流水累加 |
| 8 | `check_volume_subtotals` | 体积小计跨表 |
| 9 | `check_shipping_vs_delivery` | UCP600 ±5% 容差 |
| 10 | `check_credit_notes_balance` | credit_note 闭环（>30天 WARN，>90天 ERROR） |
| 11 | `check_exchange_rates` | 汇率完整性（每月每币种至少一条） |
| 12 | `check_receipts_vs_contract` | 收款 vs 合同金额 |
| 13 | `check_transfer_pairs` | 调拨配对 |
| 14 | `check_quotations` | 报价金额 + 派生关系 + subtotal 公式 |

### 0.3 数据来源

所有场景的"前置条件"数据都来自 `tools/make_demo_data.py`（一次生成全套，写入沙箱 `data/csv/demo_runtime/`）。场景 C/D/E 的"操作步骤"是在这套 demo 数据基础上**改动某一个字段**触发特定校验，**改动值会明确写出**，不依赖任何真实客户数据（`BUSINESS_RULES.md R8`）。

---

## 场景 A：Q025 印尼 PVC 线管订单端到端

### A.1 业务背景

一笔完整的外贸订单从询盘到收款的全流程（`BUSINESS_FLOW.md §2` 的 9 个节点）。demo 用"客户A / SC20260720001 / 4500 USD / T/T 全款"作为样本，覆盖 14 步全流程。

> **类比**：这是体检的"全项套餐"，从头到脚扫一遍，任何一步亮红灯都说明流程断了。

### A.2 前置条件

直接用 `tools/make_demo_data.py` 生成的全套数据（无需改动）：

| 实体 | demo 数据 | 出处 |
| --- | --- | --- |
| 物料 | DEMO-M-001 / 002 / 003（线管，密度 1.35） | `make_demo_data.py:67-81` |
| 仓库 | WH-01 主仓 / WH-02 外协仓 | `make_demo_data.py:84-91` |
| 供应商 | SUP-001 / SUP-002 | `make_demo_data.py:94-101` |
| 客户 | C-001 客户A | `make_demo_data.py:104-111` |
| 采购单 | PO20260726001，20000 CNY（10×1000 + 10×1000） | `make_demo_data.py:114-134` |
| 销售合同 | SC20260720001，30000 USD × 7.15 = 214500 CNY，FOB Qingdao→Jakarta | `make_demo_data.py:139-164` |
| 入库 | IN20260726001（采购到货 10+10） | `make_demo_data.py:167-188` |
| 发货 | DN20260726001（物料1发5、物料2发10，满发 short_qty=0） | `make_demo_data.py:191-213` |
| 报关 | SH20260726001，4500 USD × 7.15 = 32175 CNY | `make_demo_data.py:219-247` |
| 汇率 | 2026-07 USD 7.15 / EUR 7.85 | `make_demo_data.py:266-273` |
| 收款 | RC20260726001，4500 USD T/T 全款 | `make_demo_data.py:278-289` |
| 库存 | 物料1仓1=2、物料2仓1=0、物料1仓2=3 | `make_demo_data.py:319-327` |

### A.3 操作步骤

```bash
bash scripts/run_local_validation.sh --demo
```

（无任何数据改动，直接跑全套 demo）

### A.4 预期结果（14 步对照）

| 步骤 | 预期 | 依据（代码行号 + 数据） |
| --- | --- | --- |
| 1/14 | **通过** | products/warehouses/suppliers/customers 四表非空（`check_master_data:513-539`） |
| 2/14 | **通过** | PO total_amount=20000 = Σ明细 10000+10000（`check_purchase_orders:555-559`） |
| 3/14 | **通过**（恰好到货，无 WARN） | 入库 10+10 = 采购 10+10，不触发 `received < ordered` 的 WARN（`check_stock_in_vs_purchase:579-587`） |
| 4/14 | **通过** | 合同 total_amount=30000 = Σ明细 16000+14000（`check_sales_contracts:603-607`） |
| 5/14 | **WARN**：「合同 SC20260720001 / 物料 DEMO-M-001: 已发 5 < 合同 8（未发完）」「物料 DEMO-M-002: 已发 10 < 合同 14（未发完）」 | 发货 5/10 < 合同 8/14（`check_delivery_vs_contract:641-644`） |
| 6/14 | **通过** | 物料1仓1：入10 出5+3调拨=8 ≤ 10；物料2仓1：入10 出10 恰好平衡（`check_stock_out_vs_inventory:689-694`） |
| 7/14 | **通过** | 流水累加 = inventory（10-5-3=2；10-10=0；调拨入=3）（`check_reconciliation:776-788`） |
| 8/14 | **通过** | DEMO-M-001 单件体积 40²×30×0.93/1e6=0.04464，PO 填 0.446（10件），偏差 0.0004 ≤ 0.01（`check_volume_subtotals:836-840`） |
| 9/14 | **通过**（不触发任何 WARN/ERROR） | 报关 actual_qty = planned_qty（5/5, 10/10），偏差 0%（`check_shipping_vs_delivery:870-884`，`ratio>0` 才进 WARN 分支） |
| 10/14 | **通过**（跳过） | credit_notes 空表，`SELECT ... WHERE resolution='pending'` 返回 0 行（`check_credit_notes_balance:900-905`） |
| 11/14 | **通过** | MAX(effective_date)=2026-07-01，不早于本月1号 2026-07-01（`check_exchange_rates:973-987`） |
| 12/14 | **通过**（注意：不报"未收齐"WARN） | 收款 4500 USD ≤ 合同 30000 USD；`total_received==0` 才报"未收款"WARN，4500≠0 不触发（`check_receipts_vs_contract:1016-1036`） |
| 13/14 | **通过** | TR20260729001 出库3/物料1 = 入库3/物料1（`check_transfer_pairs:1080-1088`） |
| 14/14 | **通过** | 报价 QT001 total_amount=1167.60 = Σ明细 711.68+455.92；QT002 formal 的 parent=1 指向 brief（`check_quotations:1174-1220`，详见场景 F） |

**最终退出码**：`0`（`report.ok == True`，虽然第 5 步有 WARN 但 WARN 不影响 ok 判定，见 `ValidationReport.ok:449-451`）

### A.5 验证命令

```bash
bash scripts/run_local_validation.sh --demo
# 期望末尾输出: ✓ 全部通过
# 期望 data/logs/validation_*.log 里能看到第 5 步的两条 WARN
```

---

## 场景 B：仓库调拨 WH-01 → WH-02（transfer_ref 配对）

### B.1 业务背景

主仓（WH-01）把 3 件 DEMO-M-001 挪到外协仓（WH-02）。调拨复用 `stock_in` / `stock_out`，靠同一个 `transfer_ref='TR20260729001'` 把两笔单据串起来（`BUSINESS_RULES.md R3.5`、`BUSINESS_FLOW.md §4.4`）。

> **类比**：从 A 银行卡转 100 到 B 银行卡，记账必是两笔（A 卡 -100、B 卡 +100），靠同一个转账流水号串起来对账。中途丢钱或凭空多钱都要立刻发现。

### B.2 前置条件

demo 数据已内置这条调拨（无需改动）：

| 单据 | 类型 | transfer_ref | 物料 | 数量 | 出处 |
| --- | --- | --- | --- | --- | --- |
| `stock_out` id=2 `TR20260729001-OUT` | `out_type='transfer'` | `TR20260729001` | DEMO-M-001 | 3 | `make_demo_data.py:299` |
| `stock_in` id=2 `TR20260729001-IN` | `in_type='transfer'` | `TR20260729001` | DEMO-M-001 | 3 | `make_demo_data.py:174-176` |

### B.3 操作步骤

```bash
bash scripts/run_local_validation.sh --demo
# 关注末尾第 13 步输出
```

### B.4 预期结果

| 步骤 | 预期 | 依据 |
| --- | --- | --- |
| 13/13 | **通过**（无 ERROR 也无 WARN） | 按 `(transfer_ref, product_id)` 聚合：出库总量 3 = 入库总量 3，`out_qty == in_qty` 不进 `if out_qty != in_qty` 分支（`check_transfer_pairs:1080-1088`）；也不是 orphan 单边（`check_transfer_pairs:1091-1100`） |
| 6/13 | **通过** | 调拨发出端 WH-01：物料1 累计入 10（采购），累计出 5（销售）+3（调拨）=8 ≤ 10，未透支；接收端 WH-02：累计入 3，累计出 0，正常（`check_stock_out_vs_inventory`） |
| 7/13 | **通过** | 流水重建时 `out_type='transfer'` 和 `in_type='transfer'` 都被纳入（`rebuild_stock_logs:709-748` 不区分类型），WH-01 物料1 = 10-5-3 = 2，WH-02 物料1 = 3，跟 `inventory.csv` 一致 |

**最终退出码**：`0`

### B.5 异常分支（可选验证）

如果想看第 13 步报 ERROR，把 `data/csv/demo_runtime/stock_in_items.csv` 第 3 行的 `quantity` 从 `3` 改成 `2`，重跑：

```
[ERROR] 调拨 TR20260729001 / 物料 DEMO-M-001: 出库 3 ≠ 入库 2（差额 1，调拨在途或漏录）
```

如果想看 WARN（单边在途），删掉 `stock_in_items.csv` 第 3 行（只保留出库没入库），重跑：

```
[WARN] 调拨 TR20260729001 / 物料 DEMO-M-001: 只有出库没入库（在途或漏录）
```

### B.6 验证命令

```bash
bash scripts/run_local_validation.sh --demo
```

---

## 场景 C：跨月汇率（签约月 ≠ 收款月）

### C.1 业务背景

合同 2026-07 签（汇率 7.15），客户拖到 2026-08 才 T/T 付款。按 `BUSINESS_RULES.md R2`，**收款用 `paid_date` 所在月汇率，不是合同月**。8 月如果没有 USD 汇率，第 11 步直接报 ERROR。

> **类比**：汇率像每月一换的"换汇牌价"。7 月签合同时是 7.15，8 月去银行换汇可能变成 7.18，差额就是汇兑损益——不能强行用 7 月的牌价算 8 月的交易。

### C.2 前置条件

demo 默认数据里收款 `paid_date=2026-07-26`，汇率 7.15 → 第 11 步是通过的。本场景要**故意把收款拖到 8 月**且**不补 8 月汇率**来触发 ERROR。

### C.3 操作步骤

1. 生成 demo 数据：
   ```bash
   python3 tools/make_demo_data.py
   ```
2. 编辑 `data/csv/demo_runtime/receipts.csv`，把第 1 行的 `paid_date` 从 `2026-07-26` 改成 `2026-08-15`（其他字段不动）。
3. **不**在 `exchange_rates.csv` 补 8 月 USD 汇率（保持只有 2026-07-01 一条）。
4. 跑校验：
   ```bash
   bash scripts/run_local_validation.sh --demo
   ```

> ⚠️ 注意：本场景受 `datetime.now()` 影响——`check_exchange_rates:959-960` 用"今天"算 `this_month_start`。如果今天是 2026-07，`this_month_start=2026-07-01`，那 MAX(effective_date)=2026-07-01 仍 ≥ 本月1号，第 11 步**不会报 ERROR**。要稳定复现，请把系统时间调到 2026-08 任意一天再跑（或在 `exchange_rates.csv` 把 7 月那条 `effective_date` 改成更早，比如 2026-06-01）。

### C.4 预期结果（以"今天=2026-08"为前提）

| 步骤 | 预期 | 依据 |
| --- | --- | --- |
| 11/13 | **ERROR**：「币种 USD: 最近一条汇率是 2026-07-01, 早于本月1号(2026-08-01), 本月业务没法折算 CNY, 请补录当月汇率」 | `last_str='2026-07-01' < this_month_str='2026-08-01'`（`check_exchange_rates:981-987`） |
| 12/13 | **通过**（金额侧） | 收款 4500 USD ≤ 合同 30000 USD；币种一致（`check_receipts_vs_contract`） |
| 其他步 | 同场景 A | 改的只是 paid_date，不影响别的步 |

**最终退出码**：`1`（第 11 步 ERROR）

### C.5 修复路径（让场景变绿）

在 `data/csv/demo_runtime/exchange_rates.csv` 追加一行：

```
3,USD,7.18,2026-08-01,manual,2026年8月美元固定汇率
```

重跑后第 11 步通过。此时 `receipts.amount_cny` 应是 4500×7.18=32310 CNY（跟合同 4500×7.15=32175 差 135 CNY，这就是**汇兑损益**，本阶段只记录不结转，见 `BUSINESS_FLOW.md §4.2`）。

### C.6 验证命令

```bash
bash scripts/run_local_validation.sh --demo
```

---

## 场景 D：短装超装（UCP600 ±5% + credit_note 闭环）

### D.1 业务背景

报关实际装柜数比发货计划数少 6%（超过 UCP600 ±5% 容差），必须挂一条 `credit_notes` 走闭环（`BUSINESS_RULES.md R3`、`BUSINESS_FLOW.md §4.1`）。

> **类比**：你点了 100 个饺子，餐厅上了 94 个——少了 6 个，超过 5% 的合理误差，得补差价（credit_note）。如果只少 4 个（≤5%），餐厅说"算正常损耗"，但还是会记一笔。

### D.2 前置条件

demo 默认报关 actual_qty = planned_qty（满发），第 9 步不触发。本场景要**故意把 actual_qty 改少**触发 ERROR，再补 credit_note 走闭环。

### D.3 操作步骤

1. 生成 demo 数据：
   ```bash
   python3 tools/make_demo_data.py
   ```
2. 编辑 `data/csv/demo_runtime/shipping_record_items.csv`，把第 1 行（物料1）的 `actual_qty` 从 `5` 改成 `4`（计划 5，实际 4，偏差 |5-4|/5 = 20% > 5%）。
3. （可选，验证闭环）编辑 `data/csv/demo_runtime/credit_notes.csv`，追加一行：
   ```
   1,CN20260726001,1,1,1,1,USD,500.00,7.15,3575.00,pending,,短装1件挂账
   ```
   （`diff_qty=1` 短装 1 件，`diff_amount=500` USD 按 unit_price_usd=500 算）
4. 跑校验：
   ```bash
   bash scripts/run_local_validation.sh --demo
   ```

### D.4 预期结果

| 步骤 | 预期 | 依据 |
| --- | --- | --- |
| 9/13 | **ERROR**：「报关单 SH20260726001 / 物料 DEMO-M-001: 实际 4 vs 计划 5, 偏差 20.0% > 5% (违反 UCP600 容差)」 | `ratio = |4-5|/5 = 0.2 > SHORT_SHIPMENT_TOLERANCE=0.05`（`check_shipping_vs_delivery:870-879`） |
| 10/13 | **通过**（如果补了 credit_note 且 created_at 是今天） | 新挂的 credit_note `created_at` 默认今天，`age_days=0`，不进 >30 天 WARN 分支（`check_credit_notes_balance:917-926`） |
| 10/13（变体） | **WARN** 「pending 已 N 天 > 30 天」 | 如果把 credit_note 的 `created_at` 改成 35 天前（修改 demo 让 created_at 早于今天 35 天） |
| 10/13（变体） | **ERROR** 「pending 已 N 天 > 90 天」 | 同上，改成 95 天前 |

**最终退出码**：`1`（第 9 步 ERROR 是硬错，补 credit_note 不能消除——credit_note 只是记录差异，UCP600 容差违规本身仍报 ERROR，提示业务注意）

> 说明：第 9 步 ERROR 和第 10 步闭环是**两个独立维度**——9 步告诉你"这次装柜违规了"，10 步告诉你"挂的差异单有没有及时处理"。补 credit_note 让 10 步绿，但 9 步的 ERROR 还在（业务需复盘为什么超 5%）。

### D.5 容差边界（≤5% 走 WARN）

如果把 `actual_qty` 改成 `4.8` 不行（明细是整数），改 `planned_qty=10`、`actual_qty=9` 试物料2 → 偏差 10% 仍 ERROR。要触发 WARN，需要偏差恰好落在 (0%, 5%]：比如 `planned_qty=20, actual_qty=19` → 偏差 5% 恰好等于阈值，代码用 `ratio > SHORT_SHIPMENT_TOLERANCE`（严格大于），5% 走 WARN 分支（`check_shipping_vs_delivery:875`）。

### D.6 验证命令

```bash
bash scripts/run_local_validation.sh --demo
```

---

## 场景 E：负库存容忍（调拨先做后补）

### E.1 业务背景

外贸调拨常"先做后补"——source 仓先发货、目标仓后收货，或采购还没到货就先调拨走了。2026-07-29 起第 6 步从 ERROR 降级为 **WARN**（`BUSINESS_RULES.md R3.5` 配套规则、`SPECS.md F3.5`），允许暂时透支。

> **类比**：银行卡透支——允许你先取钱后存钱，但会发短信提醒你补。不允许的是"账本对不上"（第 7 步对账仍是 ERROR）。

### E.2 前置条件

demo 默认数据第 6 步是通过的（物料2 仓库1 入出恰好平衡）。本场景要**故意制造一笔没有对应入库的出库**触发 WARN。

### E.3 操作步骤

1. 生成 demo 数据：
   ```bash
   python3 tools/make_demo_data.py
   ```
2. 编辑 `data/csv/demo_runtime/stock_out_items.csv`，追加一行（物料2 多发 5 件，没有对应入库）：
   ```
   4,1,2,5,超发测试
   ```
   （`stock_out_id=1` 是销售出库单 OUT20260726001，物料2 原本出 10 件，再加 5 件 = 累计出 15 件）
3. 跑校验：
   ```bash
   bash scripts/run_local_validation.sh --demo
   ```

### E.4 预期结果

| 步骤 | 预期 | 依据 |
| --- | --- | --- |
| 6/13 | **WARN**：「出库单 OUT20260726001 / 物料 DEMO-M-002: 累计出库 15 > 累计入库 10（仓库 1 当前库存为负 -5，请补货）」 | 物料2 仓库1：累计入 10，累计出 10+5=15 > 10（`check_stock_out_vs_inventory:689-694`，`total_out > total_in` 进 WARN 分支） |
| 7/13 | **ERROR**（对账不平） | 流水累加 = 10-15 = -5，但 `inventory.csv` 物料2 仓库1 填的是 0 → 对账不平报 ERROR（`check_reconciliation:776-785`） |

**最终退出码**：`1`

> **关键区分**：
> - 第 6 步 WARN（累计出 > 累计入）= **允许**，业务提醒补货
> - 第 7 步 ERROR（库存表 ≠ 流水累加）= **不允许**，必须改 `inventory.csv` 让它跟流水一致（把物料2仓库1的 quantity 从 0 改成 -5），或补一笔入库

### E.5 修复路径（让场景变绿，保留 WARN）

把 `data/csv/demo_runtime/inventory.csv` 第 2 行（物料2 仓库1）的 `quantity` 从 `0` 改成 `-5`，重跑：

- 第 6 步仍是 WARN（累计出 15 > 累计入 10，提醒补货）—— 这正是"负库存容忍"的设计意图
- 第 7 步变通过（流水累加 -5 = inventory -5）
- 最终退出码 `0`（WARN 不影响 ok）

### E.6 验证命令

```bash
bash scripts/run_local_validation.sh --demo
```

---

## 场景 F：简要报价 → 正式 QT → PI 转换（check_quotations 第 14 步）

### F.1 业务背景

签合同前的报价环节：业务员先给客户一份**简要报价（brief）**，确认后派生**正式 QT（formal）**，客户最终确认后转成**销售合同（PI）**。定价走 KG × 系数（R10），不走绝对价。`check_quotations`（步骤 14/14）一次性校验：主表金额 = 明细之和、formal 的 parent 指向 brief、converted 的合同 ID 存在、明细 subtotal 公式正确（`BUSINESS_RULES.md R10`、`BUSINESS_FLOW.md` 节点 1 询盘报价）。

> **类比**：这像买房的"意向金 → 正式报价单 → 购房合同"三步走。每一步都是上一步的细化，靠编号串起来追溯，任何一步算错了（比如总价跟分项加起来对不上）都要立刻发现。

### F.2 前置条件

demo 数据已内置完整报价链（无需改动）：

| 实体 | demo 数据 | 出处 |
| --- | --- | --- |
| 报价参数 | `exchange_rate=7.25` / `default_currency=USD` / `valid_days=7` | `make_demo_data.py:294-302` |
| 简要报价 | QT20260729001，brief，客户A(id=1)，1167.60 USD × 7.25 = 8465.10 CNY | `make_demo_data.py:314-329` |
| 正式 QT | QT20260729002，formal，`parent_quote_id=1`（指向 QT001），暂无明细故 total_amount=0 | `make_demo_data.py:325-327` |
| 报价明细 | QT001 两行：DEMO-M-001(64kg) + DEMO-M-002(41kg)，同组系数 1.112，各 10 卷 | `make_demo_data.py:346-356` |

### F.3 操作步骤

```bash
bash scripts/run_local_validation.sh --demo
# 关注末尾第 14 步输出
```

（无任何数据改动，直接跑全套 demo）

### F.4 预期结果（第 14 步对照）

第 14 步 `check_quotations`（`tools/local_validator.py:1174-1220`）跑 4 个子校验：

| 子校验 | 预期 | 依据 |
| --- | --- | --- |
| ① 主表金额 = Σ 明细 subtotal | **通过** | QT001 `total_amount=1167.60` = 711.68 + 455.92（`check_quotations:1186-1188`，差额 ≤ 0.01）；QT002 无明细，`total_amount=0 = COALESCE(SUM,0)=0` 也通过 |
| ② formal 的 parent 指向 brief | **通过** | QT002 是 formal，`parent_quote_id=1` 非空，且 id=1 的 QT001 是 brief（`check_quotations:1197-1201`） |
| ③ converted 合同 ID 存在 | **跳过**（无 converted 状态报价） | demo 两单都是 `draft`，不进 `WHERE status='converted'` 分支（`check_quotations:1204-1207`） |
| ④ 明细 subtotal 公式正确 | **通过** | 明细1：64 × 1.112 × 10 = 711.68 ✓；明细2：41 × 1.112 × 10 = 455.92 ✓（`check_quotations:1216-1220`，容差 0.01） |

**对账明细**（重点）：
```
明细1 (DEMO-M-001, 64kg, A组-1.112, 10卷):
  total_weight = 64 × 10        = 640
  unit_price   = 64 × 1.112     = 71.168
  subtotal     = 64 × 1.112 × 10 = 711.68
  total_volume = 0.0446 × 10    = 0.446

明细2 (DEMO-M-002, 41kg, A组-1.112, 10卷):
  total_weight = 41 × 10        = 410
  unit_price   = 41 × 1.112     = 45.592
  subtotal     = 41 × 1.112 × 10 = 455.92
  total_volume = 0.0253 × 10    = 0.253

主表 QT001:
  total_amount     = 711.68 + 455.92 = 1167.60  (= Σ subtotal ✓)
  total_amount_cny = 1167.60 × 7.25  = 8465.10  (DERIVED_RULES 派生 ✓)
```

**最终退出码**：`0`（第 14 步全过，前 13 步同场景 A）

### F.5 异常分支（可选验证）

如果想看第 14 步子校验①报 ERROR，把 `data/csv/demo_runtime/quotation_items.csv` 第 1 行的 `subtotal` 从 `711.68` 改成 `700.00`，重跑：

```
[ERROR] 报价 QT20260729001: total_amount=1167.6 与明细小计之和=1155.92 不一致
[ERROR] 报价明细 id=1: subtotal=700.0 与 算711.68(重量64×系数1.112×数量10) 不一致
```
（主表 1167.6 是按"正确 subtotal 之和"填的，改了一个明细subtotal 后两边都报错——主表对不上、明细公式也对不上）

如果想看子校验②报 ERROR，把 `data/csv/demo_runtime/quotations.csv` 第 3 行（QT002）的 `parent_quote_id` 从 `1` 改成空，重跑：

```
[ERROR] 正式报价 QT20260729002: 缺少 parent_quote_id, 必须从简要报价派生
```

### F.6 验证命令

```bash
bash scripts/run_local_validation.sh --demo
```

---

## 附录 A：场景 × 步骤覆盖矩阵

| 场景 \ 步骤 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A 端到端 | ✓ | ✓ | ✓ | ✓ | **W** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| B 调拨配对 | ✓ | ✓ | ✓ | ✓ | W | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓**（重点） | ✓ |
| C 跨月汇率 | ✓ | ✓ | ✓ | ✓ | W | ✓ | ✓ | ✓ | ✓ | ✓ | **E** | ✓ | ✓ | ✓ |
| D 短装超装 | ✓ | ✓ | ✓ | ✓ | W | ✓ | ✓ | ✓ | **E** | ✓/W | ✓ | ✓ | ✓ | ✓ |
| E 负库存容忍 | ✓ | ✓ | ✓ | ✓ | W | **W** | **E** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| F 报价派生 | ✓ | ✓ | ✓ | ✓ | W | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✓**（重点） |

> 图例：✓=通过 / **W**=WARN / **E**=ERROR / 加粗=本场景重点验证的步骤。
>
> 第 5 步在所有场景都是 WARN（demo 发货 5/10 < 合同 8/14，未发完）—— 这是 demo 数据的固有状态，不是缺陷。如要让第 5 步变通过，把 `delivery_order_items.csv` 的 quantity 改成跟合同一致（8/14）即可。

---

## 附录 B：场景维护约定

- **加新场景**：必须基于 `tools/make_demo_data.py` 的真实数据起步，"操作步骤"里改动的字段值要明确写出（"把 X 从 A 改成 B"），不依赖任何真实客户数据（`BUSINESS_RULES.md R8`）
- **改 demo 数据**：如果改了 `make_demo_data.py`，同步回头检查所有场景的"前置条件"和"预期结果"是否仍然成立
- **ERROR/WARN 判定**：必须引用 `tools/local_validator.py` 的真实代码行号 + 真实分支条件，不能凭业务感觉臆测。改了 validator 代码要回头校准本文件
- **14 步步骤号**：以 `docs/VALIDATION_GUIDE.md §3` 为准，跟 `local_validator.py::run_validation` 的调用顺序一致

---

## 附录 C：相关文档索引

| 文档 | 作用 |
| --- | --- |
| `docs/VALIDATION_GUIDE.md` | 14 步校验流程 + 错误排查（本文件的"教科书"） |
| `docs/TASKS.md` | 任务分解清单（场景驱动的待办） |
| `docs/SPECS.md` | 功能需求规格（验收标准的源头） |
| `docs/BUSINESS_FLOW.md` | 9 节点业务流程（场景的业务依据） |
| `docs/BUSINESS_RULES.md` | R1~R10 业务规则（场景的规则依据，R10 报价） |
| `tools/make_demo_data.py` | demo 数据生成器（所有场景的数据源） |
| `tools/local_validator.py` | 14 步校验引擎（所有预期结果的判定依据） |

DONE
