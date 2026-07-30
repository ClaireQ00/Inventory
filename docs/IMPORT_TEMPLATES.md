# 导入模板说明

本目录已提供一组 CSV 模板文件，用于填充真实数据并验证当前外贸进销存流程。建议将真实数据文件保存在本地 `data/` 或 `private/` 目录中，并确保这些目录被 `.gitignore` 忽略。

## 模板位置

- `sample/templates/`（共 24 个模板）

## 完整模板清单（按业务模块分组）

### 模块 1：基础资料（4 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `products_template.csv` | `products` | 物料主数据（含密度/尺寸/重量属性） |
| `warehouses_template.csv` | `warehouses` | 仓库目录 |
| `suppliers_template.csv` | `suppliers` | 供应商名录（含本公司 `is_self=1` + 中文开票资料 `company_profiles` + 外币账户资料 `billing_profiles`） |
| `customers_template.csv` | `customers` | 客户名录 |

### 模块 2：采购（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `purchase_orders_template.csv` | `purchase_orders` | 采购单主表（含 `total_volume` 主表体积汇总 = Σ 明细 `volume_subtotal`，录完明细后回填；**展示用统计**，跟报关数不是一回事） |
| `purchase_order_items_template.csv` | `purchase_order_items` | 采购明细（subtotal 自动算） |

### 模块 3：销售合同（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `sales_contracts_template.csv` | `sales_contracts` | 合同主表（**含金额四件套 + 贸易术语 FOB/CIF/CFR/EXW + 付款条件 payment_term + 包装条款 packing + total_volume 主表体积汇总**，后两项从 formal 报价转单时拷贝） |
| `sales_contract_items_template.csv` | `sales_contract_items` | 合同明细 |

### 模块 4：库存（5 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `stock_in_template.csv` | `stock_in` | 入库单主表（**含 `in_type`（purchase/transfer）+ `transfer_ref` 调拨关联号**） |
| `stock_in_items_template.csv` | `stock_in_items` | 入库明细 |
| `stock_out_template.csv` | `stock_out` | 出库单主表（**含 `out_type`（sale/transfer）+ `transfer_ref` 调拨关联号**） |
| `stock_out_items_template.csv` | `stock_out_items` | 出库明细 |
| `inventory_template.csv` | `inventory` | 当前库存 |

> ⚠️ **`stock_logs` 表无 CSV 模板**：出入库流水由校验器 `tools/local_validator.py::rebuild_stock_logs()` 在校验前自动重建，**不需要也不应该手填**。

### 模块 5：发货（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `delivery_orders_template.csv` | `delivery_orders` | 发货单主表（含 `total_volume` 主表体积汇总 = Σ 明细 `volume_subtotal`；**展示用统计**，跟 `shipping_records.total_cbm` 报关实际数是两个概念） |
| `delivery_order_items_template.csv` | `delivery_order_items` | 发货明细（**含 actual_quantity 实际装柜 / short_qty 短装数**；末三列 `expected_unit_price`/`coeff_diff`/`coeff_check_status` 为 R11 公斤价反算派生，**留空由第16步自动回填**） |

### 模块 6：报关（3 个，外贸专用）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `shipping_records_template.csv` | `shipping_records` | 报关单主表（**金额四件套** + 集装箱/船名） |
| `shipping_record_items_template.csv` | `shipping_record_items` | 报关明细（**唛头/毛净重/体积/单价**，缺一不可报关） |
| `credit_notes_template.csv` | `credit_notes` | 贷记单/差异处理（短装/超装，**金额四件套**） |

### 模块 7：应收收款（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `exchange_rates_template.csv` | `exchange_rates` | 汇率表（**每月 1 日录一次，整月用这条**） |
| `receipts_template.csv` | `receipts` | 客户收款单（**金额四件套** + T/T/L/C/D/P/D/A 付款方式） |

### 模块 8：报价（3 个，R10 报价定价铁律）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `quotation_params_template.csv` | `quotation_params` | 报价全局参数（默认汇率/币种/有效期，键值对） |
| `quotations_template.csv` | `quotations` | 报价主表（**金额四件套 + total_volume 主表体积汇总 + brief 简要报价 / formal 正式 QT + parent_quote_id 派生链 + 5 个贸易条款 trade_terms/port_loading/port_discharge/payment_term/packing**，brief 留空、formal 补齐） |
| `quotation_items_template.csv` | `quotation_items` | 报价明细（**R10 系数定价**：unit_price = weight_per_unit × price_coefficient） |

> **R10 报价定价铁律**：报价不存绝对价，只存"单卷重量 × 报价系数(USD/KG)"。同组管径共用一个系数（如 `A组-1.112`），改一个系数整组价格自动更新。详见 `docs/BUSINESS_RULES.md` R10。

**派生规则**（`tools/csv_to_sql.py::DERIVED_RULES`）：
- `quotation_items.total_weight` = `weight_per_unit × quantity`
- `quotation_items.unit_price` = `weight_per_unit × price_coefficient`
- `quotation_items.subtotal` = `weight_per_unit × price_coefficient × quantity`（直接展开，不走派生的 unit_price）
- `quotation_items.total_volume` = `volume × quantity`
- `quotations.total_amount_cny` = `total_amount × exchange_rate`
- `quotations.total_amount` **不是派生**，是 `Σ quotation_items.subtotal` 的汇总，需在录完明细后手填或由应用层汇总
- `quotations.total_volume` **同模式**：是 `Σ quotation_items.total_volume` 的应用层汇总（**展示用统计**，给客户看这张单总共多少立方；跟 `shipping_records.total_cbm` 报关实际数不是一回事）。同字段也存在于 `sales_contracts` / `purchase_orders` / `delivery_orders` 主表

**导入顺序**（必须按此顺序，否则外键/汇总对不上）：
1. `quotation_params`（参数先行，供默认值引用）
2. `quotations`（主表先建，明细才能挂 quote_id）
3. `quotation_items`（明细后录，录完后回填主表 `total_amount = Σ subtotal`、`total_volume = Σ total_volume`）

### 模块 9：审计（1 个，空壳）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `audit_logs_template.csv` | `audit_logs` | ⚠️ **阶段一空壳，暂不使用**。表已建但无业务逻辑，看到模板也别填。第 2 阶段才接入。 |

---

## 使用说明

1. 复制模板文件到本地 `data/csv/` 目录。
2. 用真实业务数据填充 CSV 文件。
3. 真实数据文件请勿加入版本控制（`data/` 已在 `.gitignore`）。
4. 录入时请注意以下字段：
   - `product_id`、`warehouse_id`、`supplier_id`、`customer_id` 等字段使用数据库内部 ID
   - 若你需要更方便的导入方式，可先将 `products`、`warehouses`、`suppliers`、`customers` 录入数据库，再使用其自增 ID

## 建议的验证流程

1. **先录汇率**（月初做一次）：
   - `exchange_rates` — 否则所有外币业务在校验 step 12 直接 ERROR

2. **再录基础数据**：
   - `products` / `warehouses` / `suppliers` / `customers` / `inventory`

3. **按业务顺序录单据**（一笔订单的完整流转）：
   - `sales_contracts` + `sales_contract_items`（签合同）
   - `purchase_orders` + `purchase_order_items`（下采购）
   - `stock_in` + `stock_in_items`（到货入库）
   - `delivery_orders` + `delivery_order_items`（客户要货）
   - `stock_out` + `stock_out_items`（装柜出库）
   - `shipping_records` + `shipping_record_items`（报关出口）
   - `receipts`（客户付款）
   - `credit_notes`（如有短装/超装）
   - `quotation_params` → `quotations` → `quotation_items`（报价流程：询盘阶段出简要报价，确认后转正式 QT，最终可转销售合同）

4. **跑校验**：
   ```bash
   bash scripts/run_local_validation.sh
   ```
   16 步全过才算对。具体每一步校验什么，见 `docs/VALIDATION_GUIDE.md`。

## 注意事项

- 真实客户信息、合同金额、供应商价格等属于敏感数据，请严格隔离
- 如需共享数据，请先脱敏，避免通过 Git 或公共渠道直接传输原始数据
- 真实数据请保存在本地 `data/` 或 `private/` 目录，不要直接提交到仓库
- **金额四件套铁律**：凡是外币金额必须同时有 `amount + currency + exchange_rate + amount_cny` 四个字段（详见 `CLAUDE.md`）

## 参考

- `docs/BUSINESS_FLOW.md` — 一笔订单从询盘到收款的完整流程（每个节点填什么表过什么校验）
- `docs/VALIDATION_GUIDE.md` — 16 步校验详解
- `docs/PRIVATE_DATA_GUIDELINES.md` — 敏感数据隔离规范
