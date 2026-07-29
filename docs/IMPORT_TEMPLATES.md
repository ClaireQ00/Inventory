# 导入模板说明

本目录已提供一组 CSV 模板文件，用于填充真实数据并验证当前外贸进销存流程。建议将真实数据文件保存在本地 `data/` 或 `private/` 目录中，并确保这些目录被 `.gitignore` 忽略。

## 模板位置

- `sample/templates/`（共 21 个模板）

## 完整模板清单（按业务模块分组）

### 模块 1：基础资料（4 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `products_template.csv` | `products` | 物料主数据（含密度/尺寸/重量属性） |
| `warehouses_template.csv` | `warehouses` | 仓库目录 |
| `suppliers_template.csv` | `suppliers` | 供应商名录 |
| `customers_template.csv` | `customers` | 客户名录 |

### 模块 2：采购（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `purchase_orders_template.csv` | `purchase_orders` | 采购单主表 |
| `purchase_order_items_template.csv` | `purchase_order_items` | 采购明细（subtotal 自动算） |

### 模块 3：销售合同（2 个）

| 模板文件 | 对应表 | 备注 |
| --- | --- | --- |
| `sales_contracts_template.csv` | `sales_contracts` | 合同主表（**含金额四件套 + 贸易术语 FOB/CIF/CFR/EXW**） |
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
| `delivery_orders_template.csv` | `delivery_orders` | 发货单主表 |
| `delivery_order_items_template.csv` | `delivery_order_items` | 发货明细（**含 actual_quantity 实际装柜 / short_qty 短装数**） |

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

### 模块 8：审计（1 个，空壳）

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
   - `exchange_rates` — 否则所有外币业务在校验 step 11 直接 ERROR

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

4. **跑校验**：
   ```bash
   bash scripts/run_local_validation.sh
   ```
   13 步全过才算对。具体每一步校验什么，见 `docs/VALIDATION_GUIDE.md`。

## 注意事项

- 真实客户信息、合同金额、供应商价格等属于敏感数据，请严格隔离
- 如需共享数据，请先脱敏，避免通过 Git 或公共渠道直接传输原始数据
- 真实数据请保存在本地 `data/` 或 `private/` 目录，不要直接提交到仓库
- **金额四件套铁律**：凡是外币金额必须同时有 `amount + currency + exchange_rate + amount_cny` 四个字段（详见 `CLAUDE.md`）

## 参考

- `docs/BUSINESS_FLOW.md` — 一笔订单从询盘到收款的完整流程（每个节点填什么表过什么校验）
- `docs/VALIDATION_GUIDE.md` — 13 步校验详解
- `docs/PRIVATE_DATA_GUIDELINES.md` — 敏感数据隔离规范
