# 导入模板说明

本目录已提供一组 CSV 模板文件，用于填充真实数据并验证当前外贸进销存流程。建议将真实数据文件保存在本地 `data/` 或 `private/` 目录中，并确保这些目录被 `.gitignore` 忽略。

## ⚠️ 填 CSV 时最容易踩的坑（2026-07-30 真实试用总结）

### 坑 1：手数逗号导致列数对不齐（最高频！）

CSV 每行的**逗号数必须跟表头一致**。空值不能省略逗号——`,,` 是两个空值，不是"少了两列"。

```
表头: code,name,phone,is_active,remark        ← 5 列, 4 个逗号
正确: Q025,印尼大雄,0812,1,客户               ← 4 个逗号, 5 列对齐
错误: Q025,印尼大雄,0812,1                     ← 3 个逗号, remark 丢失
错误: Q025,印尼大雄,0812,,1,客户               ← 5 个逗号, 多了一列
```

**强烈建议**：不要手写 CSV，用 Excel/Numbers 直接打开填，或用 Python `csv.writer` 生成。
配套检查脚本：`bash scripts/check-template-schema-sync.sh`（schema 加字段后自动报警模板没同步）。

### 坑 2：派生字段不要手填，让脚本自动算

外径 / 体积 / 金额小计 / unit_price / subtotal 等**派生字段**，
留空即可——`tools/csv_to_sql.py::DERIVED_RULES` 会按公式自动算后填进去。
手填的话如果跟公式对不上（容差内），会**报错阻止生成 SQL**。

详见 `.claude/skills/derived-fields/SKILL.md` §1 公式一览。

### 坑 3：phone / bank_account 这种"纯数字字符串"会被误判

电话号 / 银行账号 / 单号 即使看起来像数字，本质是字符串。
`csv_to_sql.py::_looks_like_number` 已加保护：**长度 > 10 的纯数字串不当数字处理**。
所以 `081297100933` 不会被转成 `81297100933.0`，但 `1`、`100`、`3.14` 这种短数字仍按数字处理（保留小数点）。

如果遇到奇怪的"数字加 .0"问题，看这个函数。

### 坑 4：业务编号引用要稳（已修复 ✓）

**历史问题（2026-07-30）**：业务表外键原来用 `customer_id` / `product_id` 等 INT 自增 id，
依赖 MySQL AUTO_INCREMENT。反复 TRUNCATE / REPLACE INTO 会让 id 漂移，导致外键失效。

**修复方案（ADR-0004，已完成）**：所有硬外键改用业务编号（`customer_code` / `material_id` 等 VARCHAR）。
现在填 CSV 时**直接填业务编号**，不再需要记数据库内部 id。

新格式字段对应表（老 → 新）：

| 老字段 (已废弃) | 新字段 | 引用目标 |
| --- | --- | --- |
| `customer_id` | `customer_code` | `customers.code` (如 `Q025`) |
| `product_id` | `material_id` | `products.material_id` (如 `M-Q025-001`) |
| `supplier_id` | `supplier_code` | `suppliers.code` (如 `SUP-001`) |
| `warehouse_id` | `warehouse_code` | `warehouses.code` (如 `WH-01`) |
| `po_id` | `po_no` | `purchase_orders.po_no` |
| `contract_id` | `contract_no` | `sales_contracts.contract_no` |
| `quote_id` | `quote_no` | `quotations.quote_no` |

**明细表新增 `item_no` 字段**（如 `sales_contract_items.item_no`）：
同一主表单号内从 `001` 递增，方便稳定引用单条明细行。

### 坑 5：Excel 编辑 CSV 的编码 & 格式坑（已自动兜底 ✓）

**问题表现**：用 Excel（尤其 Windows 中文环境）编辑 CSV 后：
- 文件编码从 UTF-8 变成 GBK，程序读出来是乱码
- 换行符从 LF 变成 CRLF，某些解析器报错
- 多行字段（如 `billing_profiles` 里的地址）会破坏 CSV 结构（一条记录被拆成多行）

**自动兜底**：`tools/normalize_csv.py` 会在跑校验前**自动修复**上述问题。
集成在 `run_local_validation.sh` 步骤 2c，**你完全不用手动处理**。

也可以手动跑：

```bash
python3 tools/normalize_csv.py                     # 修复 data/csv/ 下所有 CSV
python3 tools/normalize_csv.py --check             # 只检查不改
python3 tools/normalize_csv.py data/csv/某个.csv    # 修复指定文件
```

**⚠️ 脚本救不了的问题**（信息已丢，必须在 Excel 填写时避免）：

| Excel 的坑 | 表现 | 避免方法 |
| --- | --- | --- |
| 日期被自动格式化 | `2026-07-29` → `7/29/2026` | 单元格格式设为"文本"，或日期前加单引号 `'2026-07-29` |
| 大数字变科学计数法 | `100000000` → `1E+08` | 同上，设文本格式或加前导单引号 |
| 前导零丢失 | `0812` → `812` | 同上（电话号/银行账号尤其注意） |
| 单元格内回车换行 | 多行字段破坏 CSV 结构 | 用空格分隔，不要按回车 |

**Excel 正确打开姿势**：数据 → 从文本/CSV → 选文件 → 文件原始格式选 `65001: Unicode (UTF-8)` → 加载。
这样能避免 Excel 自动改编码。

---

## 模板位置

- `sample/templates/`（共 23 个模板）
- ⚠️ `audit_logs`（阶段一空壳）和 `stock_logs`（出入库流水由校验器自动重建）这两张表**故意不提供模板**，看到表没模板不是漏

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

### 模块 9：审计（无模板，空壳）

`audit_logs` 表阶段一是空壳（已建表但无业务逻辑），**故意不提供 CSV 模板**。看到这张表没模板不是漏。第 2 阶段才接入。

> 📌 自动检测：`bash scripts/check-template-schema-sync.sh` 会比对 schema 字段 vs 模板表头，发现不一致立刻报警。如果以后给 audit_logs 加业务逻辑并新增模板，这条会自动放行。

---

## 使用说明

1. 复制模板文件到本地 `data/csv/` 目录。
2. 用真实业务数据填充 CSV 文件。
3. 真实数据文件请勿加入版本控制（`data/` 已在 `.gitignore`）。
4. 录入时请注意以下字段：
   - `customer_code`、`material_id`、`supplier_code`、`warehouse_code`、`*_no` 等外键字段**直接填业务编号**（ADR-0004 起，不再用数据库内部 id）
   - 填明细表前，先把主表单号填好（如 `quotations` 先填好 `quote_no=YL260728Q025`，明细表才能引用这个 `quote_no`）

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
