# 功能需求规格说明书 (Software Requirements Specification)

> 本文件是**功能规格视角的统一叙述层**,回答"系统能干什么"。
> **不重复造文档**——业务流程细节见 `docs/BUSINESS_FLOW.md`,业务规则事实源见 `docs/BUSINESS_RULES.md`,数据怎么落表见 `docs/DATA_MODEL.md`,14 步校验怎么跑见 `docs/VALIDATION_GUIDE.md`。本文件大量引用以上文档,只补一层"用户故事 + 输入输出 + 可测验收标准"的叙述。
>
> 本文档**只描述系统真实已有的能力**,不臆造未来功能。涉及阶段二规划的功能会明确标注"阶段二,本阶段不做"(规划清单见 `.claude/skills/payment-receivable/SKILL.md §7`)。

---

## 0. 阅读约定

### 0.1 文档定位

| 你想找什么 | 看哪份文档 |
| --- | --- |
| 业务怎么走(9 个节点、3 个角色) | `docs/BUSINESS_FLOW.md` |
| 业务硬性规则 R1~R10(事实源) | `docs/BUSINESS_RULES.md` |
| 每张表的字段、外键、派生规则 | `docs/DATA_MODEL.md` |
| 14 步校验怎么跑、错误怎么排查 | `docs/VALIDATION_GUIDE.md` |
| **每个功能点要满足什么才算做完(本文)** | `docs/SPECS.md` |
| 单个领域的深度规则(密度/外径/单据/汇率) | `.claude/skills/*/SKILL.md` |

### 0.2 验收标准的可测写法

每个功能点的"验收标准"都满足:
- **可测**:能被 `scripts/run_local_validation.sh` 14 步校验之一覆盖,或能在 `data/db/validation.db` 里用 SQL 验证
- **可引用**:引用 `VALIDATION_GUIDE.md` 的步骤号(如"见 VALIDATION_GUIDE 第 9 步"),不复制内容
- **真实**:涉及的表名/字段名源自 `sql/01_schema.sql`,不臆造

### 0.3 角色与名词约定

继承 `docs/BUSINESS_FLOW.md §1`:三个真实角色——外贸业务经理 / 仓库保管员 / 财务经理。术语含义见 `docs/GLOSSARY.md` 和各 skill 的"名词词典"章节,本文不重复。

### 0.4 全局约束(贯穿所有模块)

| 约束 | 出处 | 影响 |
| --- | --- | --- |
| **金额四件套铁律** | `BUSINESS_RULES.md R1` | 外币金额必须 `amount + currency + exchange_rate + amount_cny` 齐全,影响 `sales_contracts` / `shipping_records` / `credit_notes` / `receipts` / `quotations` 五张表 |
| **汇率月固定** | `BUSINESS_RULES.md R2` | 每月 1 日录一次 `exchange_rates`,跨月交易用各自月份的汇率 |
| **报价 KG×系数定价** | `BUSINESS_RULES.md R10` | 报价单价 = 单卷重量 × 报价系数,影响 `quotation_params` / `quotations` / `quotation_items`(见 §9) |
| **数据即数据,不硬编码** | `BUSINESS_RULES.md R6` | 客户/币种/口岸/产品品类都是数据,不是代码分支 |
| **Schema 三处同步** | `BUSINESS_RULES.md R7` | 改 schema 同步 `01_schema.sql` + `SQLITE_SCHEMA` + `DERIVED_RULES` |
| **真实数据不进仓库** | `BUSINESS_RULES.md R8` | 真实业务数据只放 `data/` / `private/` |

---

## 1. 基础资料模块

### 1.1 模块概述

**一句话职责**:物料、仓库、供应商、客户这四类"目录数据",被其他所有模块引用,本身不带价格。

**涉及表**:`products` / `warehouses` / `suppliers` / `customers`(共 4 张)。表结构详见 `docs/DATA_MODEL.md §4.1`。

**核心校验**:见 VALIDATION_GUIDE 第 1 步(基础资料完整性)。

### 1.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F1.1 | 产品录入(密度/厚度反推) | 物料管理员 | `products` |
| F1.2 | 行内派生字段自动计算(外径/体积/id_x_od) | 系统(自动) | `products` |
| F1.3 | 跨字段一致性提醒(米重 × 长度 vs 单重) | 系统(自动) | `products` |
| F1.4 | 仓库目录维护 | 物料管理员 | `warehouses` |
| F1.5 | 供应商名录维护 | 业务经理 | `suppliers` |
| F1.6 | 客户名录维护 | 业务经理 | `customers` |

---

### F1.1 产品录入(密度/厚度反推)

**用户故事**:作为物料管理员,我想只录入客户提供的 3~4 个参数(必有内径),让系统按产品类别(线管/钢丝管/...)的密度公式自动反推出厚度、米重、单件重量,以便快速建立准确的物料档案,不用手工套公式算错。

**输入(CSV 字段)**:
- 必填:`material_id`(企业内部唯一)、`inner_diameter`(内径 mm)、`length`(长度 m)、`product_category`(决定密度)
- 任选 1~3 个:`thickness` / `weight_per_meter` / `weight`
- 外观(算体积用,可选):`appearance_outer`(cm)、`appearance_height`(cm)
- 虚标(可选,业务约定):`virtual_weight` 虚重、`virtual_length` 虚米

**输出**:
- `tools/csv_to_sql.py::apply_derived_rules()` 按优先级反推缺失字段(详见 `product-params/SKILL.md §3`):
  - 厚度反推三路径(优先级 A > B > C):A `外径→(外径-内径)/2` / B `内径+米重+密度 解方程` / C `内径+单重+长度`
  - 米重 / 单件重量按密度公式正算
- 密度公式按 `product_category` 查 `tools/csv_to_sql.py::DENSITY_RULES`(线管 1.35;钢丝管 `内径×0.003+1.46`;塑筋管/水带 TODO 待客户补充)

**验收标准**:
- AC1:客户给的参数在公式 5% 容差内,按**客户给定值**保存,不被覆盖(规则 `BUSINESS_RULES.md R4`;校验代码 `check_cross_field_consistency`)
- AC2:客户手填值跟公式值偏差 > 5% → **报 ERROR 阻止生成 SQL**(`product-params/SKILL.md §5.1`)
- AC3:米重 × 长度 / 1000 vs 单件重量 偏差 > 5% → **报 WARN 不阻止生成**(`product-params/SKILL.md §5.2`,因为客户可单独虚标米重或单重)
- AC4:`virtual_weight` / `virtual_length` **不进** `DERIVED_RULES`,不参与反向校验(`derived-fields/SKILL.md §2`)
- AC5:产品类别 `product_category` 在 `DENSITY_RULES` 找不到公式时,跳过重量校验返回 None(不报错),不阻止生成 SQL(`BUSINESS_RULES.md R4` + `product-params/SKILL.md §1`)

**涉及数据表**:`products`(见 `DATA_MODEL.md §4.1`)。规则出处 `BUSINESS_RULES.md R4`。

---

### F1.2 行内派生字段自动计算

**用户故事**:作为物料管理员,我想外径、内径外径串、单件体积这些"能从同行其他字段算出来"的字段自动算,不用我手填,以便避免录入笔误。

**输入**:`inner_diameter`、`thickness`、`appearance_outer`、`appearance_height`(详见 `derived-fields/SKILL.md §1.1`)

**输出**(由 `apply_derived_rules()` 自动加算):
- `outer_diameter` = `inner_diameter + thickness × 2`(mm,容差 0.05)
- `id_x_od` = `"{inner}x{outer}"` 字符串(如 `32x40.36`)
- `volume` = `appearance_outer² × appearance_height × 0.93 / 1e6`(CBM,容差 0.001;0.93 是圆盘装箱系数)
- `volume_subtotal`(products 表内与 `volume` 语义等价,兼容字段)

**验收标准**:
- AC1:CSV 里派生列为空 → 按公式自动填入(`derived-fields/SKILL.md §5`)
- AC2:CSV 里派生列**手填了** → 跟公式值对比,超容差报 ERROR 阻止生成(`derived-fields/SKILL.md §6`)
- AC3:字符串派生列(`id_x_od`)不做反向校验(`derived-fields/SKILL.md §6`)
- AC4:派生字段默认走应用层(Python 算);**唯一例外** `delivery_order_items.short_qty` 走 MySQL 生成列(见 F5.3)

**涉及数据表**:`products`。规则出处 `BUSINESS_RULES.md R5`。

---

### F1.3 跨字段一致性提醒(米重 × 长度 vs 单重)

**用户故事**:作为 QA,我想在物料入库前知道"米重 × 长度 = 单重"这个互校有没有大问题,以便挑出可能录错的物料。

**输入**:同一行的 `weight_per_meter`、`length`、`weight`

**输出**:WARN 级提醒(不阻止生成 SQL)

**验收标准**:
- AC1:`weight_per_meter × length / 1000` vs `weight` 偏差 > 5% → WARN(`product-params/SKILL.md §5.2`)
- AC2:**不阻止生成 SQL**(允许客户单独虚标米重或单重)
- AC3:跟密度公式 5% 校验共存,不冲突(密度公式 5% 是 ERROR,本项 5% 是 WARN)

**涉及数据表**:`products`。代码 `tools/local_validator.py::check_cross_field_consistency` / `csv_to_sql.py::CROSS_FIELD_TOLERANCE = 0.05`。

---

### F1.4 仓库目录维护

**用户故事**:作为物料管理员,我想登记企业有哪些仓库(`code` 唯一,如 WH-01),以便后续入库/出库/调拨单据能引用到正确的仓位。

**输入**:`code`(唯一)、`name`、`address`、`is_active`(默认 1)

**输出**:`warehouses` 表一行记录

**验收标准**:
- AC1:`code` 唯一(`warehouses.code` 有 `UNIQUE`)
- AC2:`is_active=0` 的仓库不参与新业务单据(应用层过滤,本阶段一阶段不做硬约束)

**涉及数据表**:`warehouses`(见 `DATA_MODEL.md §4.1`)。规则出处 `DATA_MODEL.md §4.1`。

---

### F1.5 供应商名录维护(含本公司 is_self=1)

**用户故事**:作为业务经理,我想录入供应商的联系/开票/收款资料,以便采购合同模板能调取这些全文还原成原始格式(含中文开票信息、外币账户等)。同时**把本公司也录进来**(标记 `is_self=1`),这样销售合同/PI 模板调取卖方信息时能直接 `WHERE is_self=1` 查到。

**输入**:`code`(唯一)、`name`、`contact_person`、`phone`、`address`、`bank_account`、`company_profiles`(多行 TEXT)、`billing_profiles`(多行 TEXT)、`is_self`(0=外部供应商,1=本公司)、`is_active`

**输出**:`suppliers` 表一行记录

**验收标准**:
- AC1:`code` 唯一(`suppliers.code` 有 `UNIQUE`)
- AC2:`company_profiles` / `billing_profiles` 支持多行中文,`tools/csv_to_sql.py::sql_escape()` 已处理换行/引号转义(`DATA_MODEL.md §4.1` 备注)
- AC3:`is_self` 完整性 —— 校验步骤 1(`check_master_data`)校验 `is_self=1` **恰好 1 条**:0 条 WARN"合同模板无法调取卖方信息",>1 条 WARN"目前只支持 1 家本公司"
- AC4:`is_self=1` 的那条记录,其 `company_profiles`(中文开票资料) 和 `billing_profiles`(外币账户资料) 是合同/PI 模板的卖方信息源,必填

**涉及数据表**:`suppliers`。

---

### F1.6 客户名录维护

**用户故事**:作为业务经理,我想录入客户的品牌名、开票/收款资料,以便销售合同模板能调取这些全文,以及后续报关单据用客户品牌名做唛头。

**输入**:`code`(唯一)、`name`、`brand_name`(如 PAGODA)、`contact_person`、`phone`、`address`、`bank_account`、`company_profiles`、`billing_profiles`

**输出**:`customers` 表一行记录

**验收标准**:
- AC1:`code` 唯一
- AC2:`brand_name` 字段独立存放(用于产品/包装标识),不被合并到 `name`

**涉及数据表**:`customers`(见 `DATA_MODEL.md §4.1`)。

---

## 2. 采购模块

### 2.1 模块概述

**一句话职责**:向供应商签的进货单(PO),CNY 计价(内购不走外币四件套),对应未来入库。

**涉及表**:`purchase_orders`(主) + `purchase_order_items`(明细)。表结构详见 `DATA_MODEL.md §4.2`。

**核心校验**:见 VALIDATION_GUIDE 第 2 步(采购单金额)。

### 2.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F2.1 | 采购单录入 | 业务经理 | `purchase_orders` + `purchase_order_items` |
| F2.2 | 采购金额一致性校验 | 系统(自动) | 同上 |

---

### F2.1 采购单录入

**用户故事**:作为业务经理,我想给供应商签一份采购单,标明要哪些物料、各多少件、各 CNY 多少,以便供应商按单备货、仓库后续到货入库时能引用。

**输入**:
- 主表 `purchase_orders`:`po_no`(如 PO20260726001)、`supplier_id`、`order_date`、`expected_date`、`total_amount`(CNY)、`status`(`draft`/`confirmed`/`partial_received`/`received`/`cancelled`)
- 明细 `purchase_order_items`:每行 `product_id`、`quantity`、`unit_price`(CNY/件)、`subtotal`(派生 = 数量 × 单价)、`volume_subtotal`(派生 = 单件体积 × 数量)、`received_qty`(由入库回写)

**输出**:1 张采购主表 + N 行明细。**唯一约束 `uk_poi_po_product (po_id, product_id)`**:同一采购单同一物料只能一行。

**验收标准**:
- AC1:`status` 五态机:`draft` → `confirmed` → `partial_received` → `received` / `cancelled`(`DATA_MODEL.md §4.2`)
- AC2:`subtotal` 派生字段为空时自动算,手填了超容差报 ERROR(`derived-fields/SKILL.md §1.2`)
- AC3:`volume_subtotal` 跨表派生(依赖 `products.volume`),校验见 VALIDATION_GUIDE 第 8 步

**涉及数据表**:`purchase_orders` / `purchase_order_items`。规则出处 `BUSINESS_FLOW.md 节点 3`。

---

### F2.2 采购金额一致性校验

**用户故事**:作为 QA,我想确认采购主表的总金额跟明细小计加起来一致,以便发现"录了明细忘了改主表金额"这类笔误。

**输入**:采购主表 `total_amount` + 明细 `subtotal` 之和

**输出**:不一致报 ERROR

**验收标准**:
- AC1:`purchase_orders.total_amount = SUM(purchase_order_items.subtotal)`(见 VALIDATION_GUIDE 第 2 步;代码 `tools/local_validator.py::check_purchase_orders`)
- AC2:采购是 CNY 计价,不涉及外币四件套(`DATA_MODEL.md §4.2`)

**涉及数据表**:`purchase_orders` + `purchase_order_items`。

---

## 3. 库存模块

### 3.1 模块概述

**一句话职责**:当前库存余额(`inventory`,结果)、入库单 / 出库单(`stock_in` / `stock_out`,凭证)、出入库统一流水(`stock_logs`,原因)。

**涉及表**:`inventory` / `stock_in` + `stock_in_items` / `stock_out` + `stock_out_items` / `stock_logs`(共 5 张)。表结构详见 `DATA_MODEL.md §4.4`。

**核心校验**:见 VALIDATION_GUIDE 第 3、6、7、8 步。第 13 步(调拨配对)见 §8。

### 3.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F3.1 | 入库(采购到货 / 调拨接收 / 生产 / 退货) | 仓库保管员 | `stock_in` + `stock_in_items` |
| F3.2 | 出库(销售装柜 / 调拨发出 / 生产 / 报废) | 仓库保管员 | `stock_out` + `stock_out_items` |
| F3.3 | 出入库流水自动重建 | 系统(自动) | `stock_logs` |
| F3.4 | 库存对账(`inventory` = 流水累加) | 系统(自动) | `inventory` + `stock_logs` |
| F3.5 | 负库存容忍(WARN) | 系统(自动) | `stock_out` + `stock_in` |
| F3.6 | 体积小计跨表校验 | 系统(自动) | 各明细表 + `products` |

---

### F3.1 入库

**用户故事**:作为仓库保管员,我想记录货物实际进仓,标明来源(采购到货 / 调拨接收 / 生产 / 退货),以便库存余额自动增加,后续能追溯到源头单据。

**输入**:
- 主表 `stock_in`:`in_no`、`in_type`(ENUM `purchase`/`production`/`transfer`/`return`)、`warehouse_id`、`po_id`(仅 `purchase` 类型填)、`in_date`、`status`(`draft`/`confirmed`/`cancelled`)、`transfer_ref`(仅 `transfer` 类型填,与配对的 `stock_out` 同号)
- 明细 `stock_in_items`:每行 `product_id`、`quantity`

**输出**:库存增加 + 写一条流水到 `stock_logs`(`change_qty` 正数)

**验收标准**:
- AC1:`in_type='purchase'` 时,入库数 ≤ 采购数(见 VALIDATION_GUIDE 第 3 步;代码 `check_stock_in_vs_purchase`)
- AC2:`in_type='transfer'` 时,必须填 `transfer_ref`,跟配对的 `stock_out.transfer_ref` 同值(见 §8 / VALIDATION_GUIDE 第 13 步)
- AC3:`inventory` 表唯一约束 `uk_product_warehouse (product_id, warehouse_id)` —— 同物料同仓库只有一行(`DATA_MODEL.md §4.4`)

**涉及数据表**:`stock_in` / `stock_in_items` / `inventory` / `stock_logs`。规则出处 `BUSINESS_FLOW.md 节点 4`。

---

### F3.2 出库

**用户故事**:作为仓库保管员,我想记录货物实际出仓,标明去向(销售装柜 / 调拨发出 / 生产 / 报废),以便库存余额自动减少、销售出库衔接发货单回填实发数。

**输入**:
- 主表 `stock_out`:`out_no`、`out_type`(ENUM `sale`/`production`/`transfer`/`scrap`)、`warehouse_id`、`delivery_id`(仅 `sale` 类型填)、`out_date`、`status`、`transfer_ref`(仅 `transfer` 类型填)
- 明细 `stock_out_items`:每行 `product_id`、`quantity`

**输出**:库存减少 + 写一条流水到 `stock_logs`(`change_qty` 负数)。**销售装柜时**:必须回填 `delivery_order_items.actual_quantity`(实发数),否则 `short_qty` 永远是 0,触发后续报关校验报错。

**验收标准**:
- AC1:`out_type='sale'` 时,必须填 `delivery_id`,且装柜后回填 `actual_quantity`(`BUSINESS_FLOW.md 节点 6`)
- AC2:`out_type='transfer'` 时,必须填 `transfer_ref`(见 §8)
- AC3:累计出库 > 累计入库 → **WARN 不报错**(见 F3.5,2026-07-29 由 ERROR 降级)

**涉及数据表**:`stock_out` / `stock_out_items` / `inventory` / `stock_logs` / `delivery_order_items`。规则出处 `BUSINESS_FLOW.md 节点 6`。

---

### F3.3 出入库流水自动重建

**用户故事**:作为 QA,我想流水账(`stock_logs`)跟入库/出库明细始终一致,以便对账时有"原因账本"可查,不用手工维护两套。

**输入**:`stock_in_items` + `stock_out_items`

**输出**:`stock_logs` 表按 `(product_id, warehouse_id, source_type, source_id, source_no)` 自动重建。每次跑校验前 `tools/local_validator.py::rebuild_stock_logs` 重建一次。

**验收标准**:
- AC1:流水 `change_qty` 入库为正、出库为负,`after_qty` 记录变更后余额(`DATA_MODEL.md §4.4`)
- AC2:`source_type` ENUM `stock_in`/`stock_out`/`adjust`,`source_id` 软指向对应主表主键(无硬外键)
- AC3:流水重建后必须跟明细一致(校验前重建)

**涉及数据表**:`stock_logs`。代码 `tools/local_validator.py::rebuild_stock_logs`。

---

### F3.4 库存对账

**用户故事**:作为财务/QA,我想确认"当前库存余额"等于"流水累加",以便发现库存账实不符(如漏录出入库)。

**输入**:`inventory.quantity` vs `SUM(stock_logs.change_qty)`(按 `product_id` + `warehouse_id` 分组)

**输出**:不平报 ERROR,指出具体物料 + 仓库

**验收标准**:
- AC1:`inventory.quantity = Σ stock_logs.change_qty` 必须相等(见 VALIDATION_GUIDE 第 7 步;代码 `check_reconciliation`)
- AC2:错误信息必须指明物料 + 仓库,便于定位

**涉及数据表**:`inventory` + `stock_logs`。错误排查见 `VALIDATION_GUIDE §6 对账不平`。

---

### F3.5 负库存容忍

**用户故事**:作为仓库保管员,我想在做调拨或销售出库时允许暂时透支(源仓先出、目标仓后入),以便外贸"先做后补"业务能跑通,不被系统硬拦。

**输入**:同一仓库同一物料的累计出库 vs 累计入库

**输出**:超支时 WARN(不阻止业务)

**验收标准**:
- AC1:累计出库 > 累计入库 → **WARN**(不是 ERROR,2026-07-29 降级,见 `BUSINESS_RULES.md R3.5` 配套规则)
- AC2:WARN 提示要计划补货,但不阻断流程(`VALIDATION_GUIDE §6`)
- AC3:注意:对账(F3.4)仍是 ERROR 级——库存表跟流水对不上还是硬错

**涉及数据表**:`stock_in` / `stock_out`。代码 `check_stock_out_vs_inventory`。规则出处 `BUSINESS_RULES.md R3.5`。

---

### F3.6 体积小计跨表校验

**用户故事**:作为仓库/财务,我想确认各业务明细表的体积小计(`volume_subtotal`)跟 `products.volume`(单件体积)× 数量 一致,以便报关单 CBM 计算准确。

**输入**:各明细表 `volume_subtotal` vs `products.volume × quantity`(跨表)

**输出**:不一致报错

**验收标准**:
- AC1:校验范围 `purchase_order_items` / `sales_contract_items` / `delivery_order_items` 三张明细表(见 VALIDATION_GUIDE 第 8 步;代码 `check_volume_subtotals`)
- AC2:`products.volume` = `appearance_outer² × appearance_height × 0.93 / 1e6`(单件体积公式,见 F1.2)
- AC3:`delivery_order_items.volume_subtotal` 按 `actual_quantity` 算(实际装柜数)

**涉及数据表**:各明细表 + `products`。

---

## 4. 销售模块

### 4.1 模块概述

**一句话职责**:跟客户签的销售合同(SC),承诺数 + 单价 + 外币金额四件套,触发后续采购、发货、报关、收款全流程。

**涉及表**:`sales_contracts`(主) + `sales_contract_items`(明细)。表结构详见 `DATA_MODEL.md §4.3`。

**核心校验**:见 VALIDATION_GUIDE 第 4 步(合同金额)、第 11 步(汇率)。

### 4.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F4.1 | 销售合同录入(金额四件套) | 业务经理 | `sales_contracts` + `sales_contract_items` |
| F4.2 | 合同金额一致性校验 | 系统(自动) | 同上 |
| F4.3 | 合同币种当月有汇率校验 | 系统(自动) | `sales_contracts` + `exchange_rates` |

---

### F4.1 销售合同录入(金额四件套)

**用户故事**:作为业务经理,我想跟客户签一份销售合同,标明贸易术语(FOB/CIF/CFR/EXW)、装运港/卸货港、合同数量、外币单价、付款条件、包装条款,以便后续发货/报关/收款都能引用这份"承诺值"。

**输入**:
- 主表 `sales_contracts`:`contract_no`(如 SC20260726001)、`customer_id`、`sign_date`、`delivery_deadline`、金额四件套(`total_amount` + `currency`(默认 USD) + `exchange_rate` + `total_amount_cny`(派生))、贸易术语(`trade_terms` / `port_loading` / `port_discharge` / `freight` / `insurance`)、**付款/包装条款**(`payment_term` TEXT、`packing` TEXT,2026-07-29 加,从 formal 报价转单时拷贝)、`status`(`draft`/`confirmed`/`delivering`/`completed`/`cancelled`)
- 明细 `sales_contract_items`:每行 `product_id`、`quantity`(合同数)、`unit_price`、`subtotal`(派生)、`volume_subtotal`(派生)、`delivered_qty`(由发货单回写)
- **卖方信息**:不录在合同表里,合同模板渲染时通过 `WHERE suppliers.is_self=1` 调取本公司的 `company_profiles`/`billing_profiles`(见 F1.5)

**输出**:1 张合同主表 + N 行明细。**唯一约束 `uk_sci_contract_product`**:同一合同同一物料只能一行。

**验收标准**:
- AC1:**金额四件套铁律** —— `total_amount + currency + exchange_rate + total_amount_cny` 必须齐全(规则 `BUSINESS_RULES.md R1`;字段映射见 `DATA_MODEL.md §7.2`)
- AC2:`total_amount_cny` 是派生字段,由 `tools/csv_to_sql.py::DERIVED_RULES` 自动算,**不手填**(`BUSINESS_RULES.md R1`)
- AC3:`exchange_rate` 按 `sign_date`(签约日)所在月查 `exchange_rates`(规则 `BUSINESS_RULES.md R2`)
- AC4:`currency` 默认 USD,记账本位币 CNY(`BUSINESS_RULES.md R1`)
- AC5:`trade_terms` ENUM `FOB`/`CIF`/`CFR`/`EXW`,影响 `freight` / `insurance` 字段含义(`DATA_MODEL.md §4.3`)
- AC6:`payment_term` / `packing` 是自由文本(TEXT),通常从 formal 报价转单时拷贝过来;手填直签合同时也支持(`DATA_MODEL.md §4.3`)

**涉及数据表**:`sales_contracts` / `sales_contract_items`。规则出处 `BUSINESS_FLOW.md 节点 2`。

---

### F4.2 合同金额一致性校验

**用户故事**:作为 QA,我想确认合同主表外币总金额跟明细小计加起来一致,以便发现录入笔误。

**输入**:合同主表 `total_amount` + 明细 `subtotal` 之和

**输出**:不一致报 ERROR

**验收标准**:
- AC1:`sales_contracts.total_amount = SUM(sales_contract_items.subtotal)`(见 VALIDATION_GUIDE 第 4 步;代码 `check_sales_contracts`)
- AC2:明细 `subtotal` 派生(数量 × 单价),手填超容差报 ERROR

**涉及数据表**:`sales_contracts` + `sales_contract_items`。

---

### F4.3 合同币种当月有汇率校验

**用户故事**:作为财务,我想在签合同时确认当月该币种的汇率已经录入,以便 `total_amount_cny` 能正确折算,后续报关/收款对账不扯皮。

**输入**:合同 `currency` + `sign_date` 所在月

**输出**:当月该币种 `exchange_rates` 无记录 → ERROR "缺 X 月 Y 币种汇率,请补录"

**验收标准**:
- AC1:见 VALIDATION_GUIDE 第 11 步(代码 `check_exchange_rates`)
- AC2:汇率字段为 0 或 NULL → ERROR "汇率异常"(`payment-receivable/SKILL.md §2`)
- AC3:跨月场景规则见 `BUSINESS_RULES.md R2`(本模块按 `sign_date` 定月)

**涉及数据表**:`sales_contracts` + `exchange_rates`。

---

## 5. 发货模块

### 5.1 模块概述

**一句话职责**:内部装柜指令(DO),记录计划数 vs 实际装柜数,衔接"合同账"与"报关账"两套账机制。

**涉及表**:`delivery_orders`(主) + `delivery_order_items`(明细)。表结构详见 `DATA_MODEL.md §4.5`。

**核心校验**:见 VALIDATION_GUIDE 第 5 步(发货 vs 合同)、第 8 步(体积小计)。

### 5.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F5.1 | 发货单录入(计划数) | 业务经理 | `delivery_orders` + `delivery_order_items` |
| F5.2 | 装柜回填实际数 | 仓库保管员 | `delivery_order_items.actual_quantity` |
| F5.3 | 短装数自动算(short_qty,DB 生成列) | 系统(自动) | `delivery_order_items.short_qty` |
| F5.4 | 发货 vs 合同校验 | 系统(自动) | `delivery_order_items` + `sales_contract_items` |

---

### F5.1 发货单录入(计划数)

**用户故事**:作为业务经理,我想给客户下一次发货指令,标明计划发哪些物料、各多少件(商务承诺),关联到具体合同明细,以便仓库按单备货、合同"已发数量"能正确回写。

**输入**:
- 主表 `delivery_orders`:`delivery_no`、`customer_id`、`delivery_date`、`receiver`/`receiver_phone`/`receiver_address`、`transport_no`、`status`(`draft`/`confirmed`/`shipped`/`delivered`/`cancelled`)
- 明细 `delivery_order_items`:每行 `contract_item_id`(关联合同明细)、`product_id`、`quantity`(计划发货数,商务承诺,**不改**)、`actual_quantity`(实际装柜数,默认 = `quantity`)、`short_qty`(派生)、`volume_subtotal`(派生)

**输出**:1 张发货主表 + N 行明细。一次发货可对应多个合同明细(同一客户多合同一起发)。

**验收标准**:
- AC1:`quantity` 是商务承诺,**装柜后不改**(改的是 `actual_quantity`)(`trade-documents/SKILL.md §3`)
- AC2:`contract_item_id` 必填,用于回写 `sales_contract_items.delivered_qty`(`DATA_MODEL.md §4.5`)
- AC3:状态机 `draft` → `confirmed` → `shipped` → `delivered` / `cancelled`(`DATA_MODEL.md §4.5`)

**涉及数据表**:`delivery_orders` / `delivery_order_items`。规则出处 `BUSINESS_FLOW.md 节点 5`。

---

### F5.2 装柜回填实际数

**用户故事**:作为仓库保管员,我想装柜后回填实际装了多少(可能少于计划 = 短装,或多于 = 超装),以便报关单据按实际数做 CI/PL,差异走 credit_note 衔接。

**输入**:`delivery_order_items.actual_quantity`

**输出**:`short_qty` 自动重算;`sales_contract_items.delivered_qty` 回写;`stock_out` 出库单据生成。

**验收标准**:
- AC1:`actual_quantity` 默认 = `quantity`,装柜后由仓库回填实际值(`BUSINESS_FLOW.md 节点 6`)
- AC2:销售装柜出库时必须回填,否则 `short_qty` 永远是 0,后续报关校验会报错(`BUSINESS_FLOW.md 节点 6`)
- AC3:销售出库必填 `stock_out.delivery_id` 关联到本发货单(F3.2)

**涉及数据表**:`delivery_order_items` / `stock_out` / `sales_contract_items`。规则出处 `BUSINESS_FLOW.md 节点 6`。

---

### F5.3 短装数自动算

**用户故事**:作为仓库/业务,我想短装/超装数自动算出来,不用我手算,以便报关对账和 credit_note 处理有准确依据。

**输入**:`quantity`(计划) + `actual_quantity`(实际)

**输出**:`short_qty`(派生)

**验收标准**:
- AC1:`short_qty = quantity - actual_quantity`(正=短装,负=超装)
- AC2:**唯一走 DB 生成列的派生字段** —— MySQL `GENERATED ALWAYS AS (quantity - actual_quantity) STORED`(`sql/01_schema.sql` 第 498 行;`DATA_MODEL.md §5.1` 表格 ⚠️ 标注)
- AC3:SQLite 镜像和 `csv_to_sql.py` 走应用层兜底版(`DERIVED_RULES["delivery_order_items"]["short_qty"]`)
- AC4:改 schema 时同步三处(`BUSINESS_RULES.md R7`)

**涉及数据表**:`delivery_order_items`。规则出处 `BUSINESS_RULES.md R5`(唯一例外说明)。

---

### F5.4 发货 vs 合同校验

**用户故事**:作为 QA,我想确认发货数没超过合同数(优先用实际装柜数,没装柜回退计划数),以便发现"发了超过合同约定的货"这类异常。

**输入**:`delivery_order_items` 实际/计划数 vs `sales_contract_items.quantity`

**输出**:超发报错;未发完 WARN

**验收标准**:
- AC1:**优先用 `actual_quantity`**,未装柜(`actual_quantity=0`)回退 `quantity`(见 VALIDATION_GUIDE 第 5 步;代码 `check_delivery_vs_contract`)
- AC2:超发(发货 > 合同)→ **一律 ERROR**,无 WARN 分级(代码 `check_delivery_vs_contract`:任何 `delivered > contracted` 都报 error,不存在容差阈值)
- AC3:未发完(发货 < 合同)→ WARN "未发完"(`trade-documents/SKILL.md §7` 示例)

**涉及数据表**:`delivery_order_items` + `sales_contract_items`。规则出处 `BUSINESS_FLOW.md 节点 5`。

---

## 6. 报关模块

### 6.1 模块概述

**一句话职责**:装船后给海关看的实际数据(SH + CI + PL),含唛头/毛净重/CBM;实际数 vs 计划数超 5% 差异走 `credit_notes` 衔接两套账。

**涉及表**:`shipping_records`(主) + `shipping_record_items`(明细) + `credit_notes`(差异处理)。表结构详见 `DATA_MODEL.md §4.6`。

**核心校验**:见 VALIDATION_GUIDE 第 9 步(UCP600 ±5%)、第 10 步(credit_note 闭环)、第 11 步(报关月汇率)。

### 6.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F6.1 | 报关单据录入(含金额四件套) | 仓库/报关行 | `shipping_records` + `shipping_record_items` |
| F6.2 | 报关必备字段校验(唛头/毛净重/件数/CBM) | 系统(自动) | `shipping_record_items` |
| F6.3 | UCP600 ±5% 容差校验 | 系统(自动) | `shipping_record_items` vs `delivery_order_items` |
| F6.4 | 短装/超装 credit_note 闭环 | 业务+财务 | `credit_notes` |
| F6.5 | credit_note 4 种 resolution 处理 | 业务+财务 | `credit_notes.resolution` |

---

### F6.1 报关单据录入

**用户故事**:作为仓库/报关行,我想装船后记录实际报关数据(集装箱号、唛头、毛净重、CBM、外币金额),以便生成 Commercial Invoice + Packing List 给海关和银行。

**输入**:
- 主表 `shipping_records`:`shipping_no`、`delivery_id`、`shipping_date`、`container_no`、`seal_no`、`vessel`、报关核心(`total_pkgs`/`total_gross_wt`/`total_net_wt`/`total_cbm`)、金额四件套(`total_amount` + `currency` + `exchange_rate` + `total_amount_cny`(派生))、`status`(`draft`/`customs_cleared`/`closed`/`cancelled`)
- 明细 `shipping_record_items`:每行 `product_id`、`planned_qty`(从发货单带过来)、`actual_qty`(实际装柜,必填)、`shipping_mark`(唛头)、`gross_weight_per`、`net_weight_per`、`unit_volume`、`unit_price_usd`、`subtotal_usd`(派生)
- **一张发货单可分多次装船**(partial shipment),每次一条 `shipping_records`(`DATA_MODEL.md §4.6`)

**输出**:CI + PL 数据源

**验收标准**:
- AC1:**金额四件套铁律** —— `total_amount + currency + exchange_rate + total_amount_cny` 齐全(`BUSINESS_RULES.md R1`;字段映射见 `DATA_MODEL.md §7.2`)
- AC2:`total_amount_cny` 派生 = `total_amount × exchange_rate`(自动算,不手填)
- AC3:`exchange_rate` 按 `shipping_date`(装船日)所在月查 `exchange_rates`(`BUSINESS_RULES.md R2`)
- AC4:`subtotal_usd` = `actual_qty × unit_price_usd`(派生,`derived-fields/SKILL.md §1` 未列,代码 `DERIVED_RULES["shipping_record_items"]["subtotal_usd"]`)

**涉及数据表**:`shipping_records` / `shipping_record_items`。规则出处 `BUSINESS_FLOW.md 节点 7`、`trade-documents/SKILL.md §1/§6`。

---

### F6.2 报关必备字段校验

**用户故事**:作为报关行,我想确认报关明细的唛头/毛重/净重/件数/CBM 都填了,以便单据不会被海关/银行退单。

**输入**:`shipping_record_items` 的 5 个必备字段

**输出**:缺一不可(具体校验阈值以代码为准)

**验收标准**:
- AC1:5 个必备字段(`shipping_mark` / `gross_weight_per` / `net_weight_per` / `actual_qty` / `unit_volume`)缺一报错(`trade-documents/SKILL.md §6`)
- AC2:毛重 ≥ 净重(单件毛重含包装,净重是裸重,`trade-documents/SKILL.md §2`)
- AC3:`unit_volume` 来自 `products.volume`(单件体积,见 F1.2),报关行不能自改(`derived-fields/SKILL.md §11` 跨 skill 协作场景)

**涉及数据表**:`shipping_record_items` + `products`。规则出处 `BUSINESS_RULES.md R3`(报关必填字段)。

---

### F6.3 UCP600 ±5% 容差校验

**用户故事**:作为业务/QA,我想确认报关实际数跟发货计划数的差异在 UCP600 允许的 ±5% 内,超出强制走 credit_note,以便单证相符不被海关/银行拒收。

**输入**:`shipping_record_items.actual_qty` vs `delivery_order_items.quantity`(计划数)

**输出**:差异比例 `ratio = |actual - planned| / planned`
- `ratio ≤ 5%` → WARN(允许,但要记录)
- `ratio > 5%` → ERROR(必须补 credit_note)

**验收标准**:
- AC1:容差常量 `SHORT_SHIPMENT_TOLERANCE = 0.05`(代码 `tools/local_validator.py`)
- AC2:见 VALIDATION_GUIDE 第 9 步(代码 `check_shipping_vs_delivery`)
- AC3:**不要试图统一两套账**——合同账是承诺值,报关账是实际值,差异用 credit_note 衔接(`BUSINESS_RULES.md R3` / `trade-documents/SKILL.md §3`)
- AC4:适用范围:发货单 `quantity` → 报关单 `actual_qty`;销售合同 `quantity` → 发货单 `actual_quantity`(`trade-documents/SKILL.md §4`)

**涉及数据表**:`shipping_record_items` + `delivery_order_items`。规则出处 `BUSINESS_RULES.md R3`、UCP600 第 30 条。

---

### F6.4 短装/超装 credit_note 闭环

**用户故事**:作为业务+财务,我想把超 5% 的差异(短装/超装)用 credit_note 记录下来,并强制在 30 天内处理完,以便差异可追溯、不挂账太久。

**输入**:`credit_notes` 表:`cn_no`、`shipping_id`、`contract_item_id`、`product_id`、`diff_qty`(正=短装,负=超装)、金额四件套(`diff_amount` + `currency` + `exchange_rate` + `diff_amount_cny`(派生))、`resolution`、`resolved_at`

**输出**:闭环或逾期报警

**验收标准**:
- AC1:`resolution = 'pending'` 且 `created_at` 距今 > 30 天 → WARN(催办)
- AC2:`resolution = 'pending'` 且 `created_at` 距今 > 90 天 → ERROR(严重逾期)
- AC3:见 VALIDATION_GUIDE 第 10 步(代码 `check_credit_notes_balance`)
- AC4:`diff_amount_cny` 派生 = `diff_amount × exchange_rate`(按报关单 `shipping_date` 所在月定汇率,`DATA_MODEL.md §7.2`)
- AC5:金额四件套铁律适用(`BUSINESS_RULES.md R1`,影响 `credit_notes`)

**涉及数据表**:`credit_notes` + `shipping_records` + `sales_contract_items`。规则出处 `BUSINESS_RULES.md R3`、`trade-documents/SKILL.md §5`。

---

### F6.5 credit_note 4 种 resolution 处理

**用户故事**:作为业务+财务,我想把 pending 状态的差异推进到 replenish / refund / writeoff 之一,以便差异闭环、对应到补发/退款/注销。

**输入**:`credit_notes.resolution`(ENUM `pending`/`replenish`/`refund`/`writeoff`)+ `resolved_at`

**输出**:状态推进,脱离 pending 不再触发 F6.4 逾期报警

**验收标准**:
- AC1:4 种状态含义(`trade-documents/SKILL.md §5`):
  - `pending` 待处理 / `replenish` 补发(下次补上)/ `refund` 退款 / `writeoff` 注销
- AC2:推进到非 pending 必须填 `resolved_at`(`DATA_MODEL.md §4.6`)
- AC3:refund 时 `diff_amount` 折算 CNY(`diff_amount_cny`)需跟 `receipts` 对账(跨 skill:`trade-documents` → `payment-receivable`,`trade-documents/SKILL.md §跨 skill 协作场景 1`)

**涉及数据表**:`credit_notes`。

---

## 7. 收款模块

### 7.1 模块概述

**一句话职责**:客户付款记录 + 月固定汇率折算 CNY,做应收对账。

**涉及表**:`exchange_rates`(月固定汇率表)+ `receipts`(收款单)。表结构详见 `DATA_MODEL.md §4.7`。

**核心校验**:见 VALIDATION_GUIDE 第 11 步(汇率完整性)、第 12 步(收款 vs 合同)。

### 7.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F7.1 | 月固定汇率录入 | 财务经理 | `exchange_rates` |
| F7.2 | 收款单录入(金额四件套) | 财务经理 | `receipts` |
| F7.3 | 跨月交易折算(按 paid_date 定月) | 系统(自动) | `receipts` + `exchange_rates` |
| F7.4 | 收款 vs 合同对账(币种一致 + ±5%) | 系统(自动) | `receipts` + `sales_contracts` |

---

### F7.1 月固定汇率录入

**用户故事**:作为财务经理,我想每月 1 日录入当月固定汇率(同币种同月一条),以便整月所有外币交易都用这一条折算,月底结账不扯皮。

**输入**:`currency`(ISO 4217 三字母)、`rate_to_cny`(1 原币种 = ? CNY)、`effective_date`(每月 1 号)、`source`(`manual`/`boc`/`pboc`)

**输出**:`exchange_rates` 表一行记录

**验收标准**:
- AC1:**唯一约束** `uk_currency_effective (currency, effective_date)` —— 同币种同月仅一条(`sql/01_schema.sql` 第 649 行;`BUSINESS_RULES.md R2`)
- AC2:`rate_to_cny` 为 0 或 NULL → 业务上数据缺陷(`payment-receivable/SKILL.md §2`)
- AC3:见 VALIDATION_GUIDE 第 11 步(代码 `check_exchange_rates`)

**涉及数据表**:`exchange_rates`。规则出处 `BUSINESS_RULES.md R2`、`payment-receivable/SKILL.md §2`。

---

### F7.2 收款单录入(金额四件套)

**用户故事**:作为财务经理,我想记录客户每次付款(金额、币种、到账日、付款方式、水单号),以便折算 CNY 后跟合同对账。

**输入**:`receipts` 表:
- 标识:`receipt_no`(如 RC20260815001)、`customer_id`
- 关联(均可空):`contract_id` / `shipping_id` / `delivery_id`(预收款时无合同)
- 金额四件套:`amount` + `currency`(默认 USD) + `exchange_rate`(按 `paid_date` 查表) + `amount_cny`(派生)
- 收款信息:`paid_date`、`pay_method`(ENUM `T/T`/`L/C`/`D/P`/`D/A`/`other`,默认 T/T)、`bank_ref`(水单号)
- `status`(`draft`/`confirmed`/`cancelled`)

**输出**:1 行收款记录,参与对账

**验收标准**:
- AC1:**金额四件套铁律** —— `amount + currency + exchange_rate + amount_cny` 齐全(`BUSINESS_RULES.md R1`;字段映射见 `DATA_MODEL.md §7.2`,receipts 用 `amount` 命名,见 §7.4 命名差异说明)
- AC2:`amount_cny` 派生 = `amount × exchange_rate`(自动算,不手填)
- AC3:**只有 `status='confirmed'` 的收款才参与对账**(`draft` 不算,`payment-receivable/SKILL.md §3.2`)
- AC4:`exchange_rate` 不允许留 0 或 NULL(`payment-receivable/SKILL.md §6`)

**涉及数据表**:`receipts`。规则出处 `BUSINESS_FLOW.md 节点 8`、`payment-receivable/SKILL.md §3`。

---

### F7.3 跨月交易折算(按 paid_date 定月)

**用户故事**:作为财务,我想跨月交易用各自月份的汇率折算(合同 7 月签、客户 8 月才付款,8 月就用 8 月汇率),以便准确反映汇兑损益,而不是强行统一成一个汇率。

**输入**:`receipts.paid_date` 所在月 → 查 `exchange_rates`

**输出**:`amount_cny` 按到账月汇率折算

**验收标准**:
- AC1:**跨月交易用 `paid_date` 所在月汇率,不是合同月**(`BUSINESS_RULES.md R2`;`payment-receivable/SKILL.md §3` / §5 示例)
- AC2:跨月产生**汇兑损益**是正常现象,**不"统一"**(`BUSINESS_RULES.md R2` 备注 / `BUSINESS_FLOW.md §4.2`)
- AC3:本阶段只记录汇兑损益,不做月末结转(阶段二规划:`forex_settlements` 表,见 `payment-receivable/SKILL.md §7`)
- AC4:定月字段按表不同(`DATA_MODEL.md §7.2`):`receipts` 用 `paid_date`、`shipping_records` 用 `shipping_date`、`sales_contracts` 用 `sign_date`

**涉及数据表**:`receipts` + `exchange_rates`。规则出处 `BUSINESS_RULES.md R2`。

---

### F7.4 收款 vs 合同对账

**用户故事**:作为财务/QA,我想确认累计收款没超过合同金额(允许 ±5%)、币种一致,以便发现"超收可能录错"或"未收齐要催款"。

**输入**:`SUM(receipts.amount WHERE contract_id=X AND status='confirmed')` vs `sales_contracts.total_amount`

**输出**:
- 累计收款 > 合同 × 1.05 → ERROR "超收"
- 累计收款 < 合同 × 0.95 → WARN "未收齐"
- 币种不一致 → ERROR
- 汇率为 0 → ERROR

**验收标准**:
- AC1:见 VALIDATION_GUIDE 第 12 步(代码 `check_receipts_vs_contract`)
- AC2:**只统计 `confirmed` 收款**,`draft` / `cancelled` 不算(`payment-receivable/SKILL.md §3.2`)
- AC3:**按原币种聚合**(`receipts.currency` 必须跟 `sales_contracts.currency` 一致)
- AC4:±5% 容差跟 UCP600 短装容差对齐(`payment-receivable/SKILL.md §3.3`)
- AC5:当前阶段一个 receipt 只关联一个 `contract_id`;多合同合并付款留阶段二(`receipt_allocations` 子表,见 `BUSINESS_FLOW.md §4.3`、`payment-receivable/SKILL.md §7`)

**涉及数据表**:`receipts` + `sales_contracts`。

---

## 8. 调拨模块

### 8.1 模块概述

**一句话职责**:仓库间挪货,复用 `stock_in` / `stock_out`,通过 `transfer_ref` 软关联配对,**不进报关/收款流程**。

**特殊点**:**调拨没有独立表**——它是一对特殊类型的出入库单据(`in_type='transfer'` / `out_type='transfer'`)。设计理由详见 `DATA_MODEL.md §6`。

**核心校验**:见 VALIDATION_GUIDE 第 13 步(调拨配对)。

### 8.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F8.1 | 跨仓调拨(transfer_ref 软关联) | 仓库保管员 | `stock_out` + `stock_in`(transfer 类型) |
| F8.2 | 调拨配对校验(出库总量 = 入库总量) | 系统(自动) | 同上 |
| F8.3 | 调拨不进外贸单据流程 | 设计约束(系统) | — |

---

### F8.1 跨仓调拨(transfer_ref 软关联)

**用户故事**:作为仓库保管员,我想把主仓的货挪到口岸附近的临时仓(或外协仓),系统通过同一个 `transfer_ref` 号把两笔出入库串起来,以便库存自动加减、不漏单。

**输入**:
- 源仓出库:`stock_out`(`out_type='transfer'`、`warehouse_id`=源仓、`transfer_ref` 如 `TR20260729001`)+ `stock_out_items`
- 目标仓入库:`stock_in`(`in_type='transfer'`、`warehouse_id`=目标仓、**同一个** `transfer_ref`)+ `stock_in_items`

**输出**:两笔出入库单据,自动写 `stock_logs` / 更新 `inventory`。`transfer_ref` 编号建议 `TR + 日期 + 序号`。

**类比**:从 A 银行卡转 100 到 B 银行卡,记账必是两笔(A 卡 -100、B 卡 +100),靠同一个转账流水号串起来对账(见 `DATA_MODEL.md §6.1`)。

**验收标准**:
- AC1:`stock_out.transfer_ref` 与配对的 `stock_in.transfer_ref` **必须同值**(`DATA_MODEL.md §6.2`)
- AC2:两表都加了索引 `idx_si_transfer` / `idx_so_transfer` 加速按 `transfer_ref` 聚合(`sql/01_schema.sql` 第 348/398 行)
- AC3:调拨的两笔单据必须用 ENUM `'transfer'` 类型(`in_type` / `out_type` 已含该枚举值,`BUSINESS_RULES.md R3.5`)
- AC4:库存对账(F3.4)自动覆盖调拨——`stock_logs` 流水自动重建包含 transfer 类型

**涉及数据表**:`stock_out` + `stock_out_items` + `stock_in` + `stock_in_items` + `stock_logs` + `inventory`。规则出处 `BUSINESS_FLOW.md §4.4`、`BUSINESS_RULES.md R3.5`、`DATA_MODEL.md §6`。

---

### F8.2 调拨配对校验

**用户故事**:作为 QA,我想确认每个 `transfer_ref` 的出库总量 = 入库总量(按物料分),以便发现"调拨中途丢货"或"漏录另一半单据"。

**输入**:按 `(transfer_ref, product_id)` 聚合:
- 出库总量 = `SUM(stock_out_items.quantity)` WHERE `stock_out.out_type='transfer'`
- 入库总量 = `SUM(stock_in_items.quantity)` WHERE `stock_in.in_type='transfer'`

**输出**:
- 出库总量 ≠ 入库总量 → **ERROR**(差额、漏录或在途)
- 只有一边(只有出库没入库,或反之)→ **WARN**(在途、漏录或方向录错)

**验收标准**:
- AC1:见 VALIDATION_GUIDE 第 13 步(代码 `check_transfer_pairs`)
- AC2:聚合 key 是 `(transfer_ref, product_id)`,**按物料分组**对账(`DATA_MODEL.md §6.3`)
- AC3:在途(已出未到)报 WARN,到货后入库即可消除(`VALIDATION_GUIDE §6`)

**涉及数据表**:`stock_out` + `stock_out_items` + `stock_in` + `stock_in_items`。规则出处 `BUSINESS_RULES.md R3.5`。

---

### F8.3 调拨不进外贸单据流程

**用户故事**(设计约束):作为系统设计,我想确保调拨跟销售/报关/收款流程完全隔离,以便调拨不会误触发 UCP600、汇率、credit_note 等外贸逻辑。

**约束**:
- 调拨**不产生** `shipping_records`(不报关)
- 调拨**不触发** UCP600 ±5% 容差(F6.3)
- 调拨**不涉及** `receipts` / 汇率 / `credit_notes`(F7 / F6.4)
- `trade-documents` / `payment-receivable` 两个 skill 不管调拨(`trade-documents/SKILL.md §8` 明确说明)

**验收标准**:
- AC1:调拨类型(`transfer`)的单据不会被报关/收款校验函数扫描(代码层面:`check_shipping_vs_delivery` / `check_receipts_vs_contract` 只扫销售链路单据)
- AC2:调拨校验独立在第 13 步,跟前 12 步逻辑隔离(`BUSINESS_RULES.md R3.5`)
- AC3:source 仓允许暂时负库存(见 F3.5,降级为 WARN),后续补货即可

**涉及数据表**:无新增。规则出处 `BUSINESS_RULES.md R3.5`、`DATA_MODEL.md §6.6`。

---

## 9. 报价模块

### 9.1 模块概述

**一句话职责**:签合同前的报价环节,**KG × 系数定价**(不走绝对价),承载 简要报价(brief)→ 正式 QT(formal)→ 销售合同(PI) 的派生链。

**涉及表**:`quotation_params`(全局参数) + `quotations`(主表,brief/formal 共用) + `quotation_items`(明细)。表结构详见 `DATA_MODEL.md §4.9`。

**核心校验**:见 VALIDATION_GUIDE 第 14 步(`check_quotations`)。

**业务规则**:定价铁律见 `BUSINESS_RULES.md R10`;设计取舍(为何 brief/formal 共用表、subtotal 为何用直接公式)见 `docs/adr/0003-quotation-derive-from-brief.md`。

### 9.2 功能点清单

| # | 功能点 | 主负责角色 | 涉及表 |
| --- | --- | --- | --- |
| F9.1 | 简要报价录入(brief) | 业务经理 | `quotations` + `quotation_items` |
| F9.2 | 正式 QT 生成(formal,从 brief 派生) | 业务经理 | `quotations`(`parent_quote_id` 软关联) |
| F9.3 | 报价转销售合同(converted) | 业务经理 | `quotations.converted_contract_id` + `sales_contracts` |
| F9.4 | 报价金额计算(KG × 系数定价,subtotal 派生) | 系统(自动) | `quotation_items` + `quotations` |

---

### F9.1 简要报价录入(brief)

**用户故事**:作为业务经理,我想在正式签合同前先给客户一份简要报价,只录"每卷重量 × 报价系数 × 数量"就能算出单价和小计,不用手工套公式,以便快速回应客户询盘。

**输入**:
- 主表 `quotations`:`quote_no`(如 `QT20260729001`)、`customer_id`、`quote_type='brief'`、`quote_date`、`valid_until`、金额四件套(`total_amount` + `currency`(默认 USD) + `exchange_rate` + `total_amount_cny`(派生))、`status`(`draft`/`sent`/`confirmed`/`converted`/`cancelled`)
- 明细 `quotation_items`:每行 `product_id`(关联 `products` 带出 `weight`/`volume`)、`group_code`(分组码,如 `A组-1.112`)、`price_coefficient`(报价系数 USD/KG)、`weight_per_unit`(单卷重量 KG,从 `products.weight` 带出可覆盖)、`quantity`(卷数)、派生字段(`total_weight`/`unit_price`/`subtotal`/`total_volume`)
- **不带条款**:brief 阶段 5 个贸易条款字段(`trade_terms`/`port_loading`/`port_discharge`/`payment_term`/`packing`)留空,等 formal 阶段补(见 F9.2)

**输出**:1 张简要报价主表 + N 行明细。主表 `total_amount = Σ quotation_items.subtotal`(应用层汇总,非 `DERIVED_RULES`)。

**验收标准**:
- AC1:**定价铁律 R10** —— `unit_price = weight_per_unit × price_coefficient`,`subtotal = weight_per_unit × price_coefficient × quantity`(直接公式,不依赖派生 `unit_price`,见 `BUSINESS_RULES.md R10` + ADR-0003)
- AC2:派生字段(4 个)走 `tools/csv_to_sql.py::DERIVED_RULES["quotation_items"]`,空则自动算,手填超容差报 ERROR(`derived-fields` 加算+反向校验双行为)
- AC3:**金额四件套铁律** —— 主表 `total_amount + currency + exchange_rate + total_amount_cny` 齐全(`BUSINESS_RULES.md R1`);`total_amount_cny` 派生 = `total_amount × exchange_rate`
- AC4:`quotations.total_amount` 必须等于明细 `subtotal` 之和(见 VALIDATION_GUIDE 第 14 步;代码 `tools/local_validator.py::check_quotations` 子校验 1)
- AC5:同一报价单同一物料只能一行(唯一约束 `uk_qi_quote_product`,见 `DATA_MODEL.md §4.9`)

**涉及数据表**:`quotations` / `quotation_items`。规则出处 `BUSINESS_RULES.md R10`。

---

### F9.2 正式 QT 生成(formal,从 brief 派生)

**用户故事**:作为业务经理,我想在简要报价确认后,基于它派生出一份正式 QT(formal)发给客户,系统通过 `parent_quote_id` 把两者关联起来,以便保留派生追溯链(正式 QT 从哪份简要报价来的一目了然)。

**输入**:`quotations` 新增一行,`quote_type='formal'`、`parent_quote_id` 指向源 brief 的 `id`,其他字段从 brief 复制或细化。**formal 阶段必须补齐 5 个贸易条款**:`trade_terms`(FOB/CIF/CFR/EXW)、`port_loading`、`port_discharge`、`payment_term`(自由文本)、`packing`(自由文本)。

**输出**:1 张 formal 报价(即 PROFORMA INVOICE),`parent_quote_id` 软关联到源 brief。

**验收标准**:
- AC1:`quote_type='formal'` 时,`parent_quote_id` **必须非空**(见 VALIDATION_GUIDE 第 14 步;代码 `check_quotations` 子校验 2)
- AC2:`parent_quote_id` 指向的必须是 `quote_type='brief'` 的报价(不能 formal 派生 formal)
- AC3:`parent_quote_id` 是**自引用软关联**(`ON DELETE SET NULL`),类似调拨 `transfer_ref` 的思路——靠应用层校验,非外键强约束(见 ADR-0003)
- AC4:brief 与 formal **共用 `quotations` 表**,靠 `quote_type` 区分,不建独立表(见 ADR-0003 决策)
- AC5:formal 的 5 个贸易条款字段(`trade_terms`/`port_loading`/`port_discharge`/`payment_term`/`packing`)是 formal → SC 转单时的拷贝源(F9.3 转合同 + F4.1 录合同都会用)

**涉及数据表**:`quotations`(自引用)。规则出处 `BUSINESS_RULES.md R10`。

---

### F9.3 报价转销售合同(converted)

**用户故事**:作为业务经理,我想在正式 QT 被客户确认后,把它转成销售合同(PI),系统回填 `converted_contract_id` 串联起"报价→合同"链路,以便后续发货/报关/收款都能追溯到最初的报价。

**输入**:`quotations.status` 推进到 `'converted'`,`converted_contract_id` 回填对应的 `sales_contracts.id`。

**输出**:`quotations` 状态变 `converted`,`converted_contract_id` 指向新建的销售合同。

**验收标准**:
- AC1:`status='converted'` 时,若 `converted_contract_id` 非空,则该 ID 必须在 `sales_contracts` 存在(见 VALIDATION_GUIDE 第 14 步;代码 `check_quotations` 子校验 3)
- AC2:状态机 `draft` → `sent` → `confirmed` → `converted` / `cancelled`(`DATA_MODEL.md §4.9`)
- AC3:转合同后衔接 `sales_contracts` 的金额四件套 + 后续发货/报关/收款流程(跨模块,见 §4 销售模块)

**涉及数据表**:`quotations` + `sales_contracts`。规则出处 `BUSINESS_RULES.md R10`。

---

### F9.4 报价金额计算(KG × 系数定价,subtotal 派生)

**用户故事**:作为 QA,我想确认报价明细的 `subtotal` 跟"重量 × 系数 × 数量"对得上、主表总额跟明细小计之和一致,以便发现"录了明细忘了汇总"或"系数填错"这类笔误。

**输入**:`quotation_items` 的 `weight_per_unit` × `price_coefficient` × `quantity`;`quotations.total_amount` vs `Σ quotation_items.subtotal`

**输出**:不一致报 ERROR

**验收标准**:
- AC1:明细 `subtotal = weight_per_unit × price_coefficient × quantity`(见 VALIDATION_GUIDE 第 14 步;代码 `check_quotations` 子校验 4,容差 0.01)
- AC2:主表 `quotations.total_amount = Σ quotation_items.subtotal`(`check_quotations` 子校验 1)
- AC3:**一张报价单可有多组系数**,用 `group_code` 区分(如 `A组-1.112`),系数放明细不放主表(`BUSINESS_RULES.md R10` + ADR-0003)
- AC4:派生字段(`total_weight`/`unit_price`/`subtotal`/`total_volume`)的加算+反向校验由 `apply_derived_rules` 完成,`subtotal` 用直接公式避免单轮遍历依赖链失效(代码 `tools/csv_to_sql.py:343-396`)

**涉及数据表**:`quotation_items` + `quotations`。规则出处 `BUSINESS_RULES.md R10`。

---

## 10. 跨模块功能点(贯穿多模块)

> 以下功能点不属于单一模块,但贯穿多个模块,单独列出便于追溯。

### F10.1 金额四件套自动折算

**用户故事**:作为财务,我想所有外币金额自动按当期汇率折算 CNY,不用手算,以便任何时候看数据都能精确还原成人民币。

**影响表**:`sales_contracts` / `shipping_records` / `credit_notes` / `receipts`(共 4 张)

**派生公式**(统一):`amount_cny = amount × exchange_rate`(容差 0.01)

**命名差异对照**(语义一致,因表而异)见 `DATA_MODEL.md §7.2`:
| 表 | amount | currency | exchange_rate | amount_cny(派生) | 定月字段 |
| --- | --- | --- | --- | --- | --- |
| `sales_contracts` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` | `sign_date` |
| `shipping_records` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` | `shipping_date` |
| `credit_notes` | `diff_amount` | `currency` | `exchange_rate` | `diff_amount_cny` | 沿用报关单 `shipping_date` |
| `receipts` | `amount` | `currency` | `exchange_rate` | `amount_cny` | `paid_date` |

**验收标准**:
- AC1:四张表的 `*_cny` 字段都是同一公式的变体,代码位置 `tools/csv_to_sql.py::DERIVED_RULES`(`DATA_MODEL.md §5.1` 表格)
- AC2:派生字段永远自动算,不手填(`BUSINESS_RULES.md R1`)
- AC3:校验落点见 VALIDATION_GUIDE 第 11 步(汇率完整性)+ 第 12 步(收款对账)

**规则出处**:`BUSINESS_RULES.md R1`、`payment-receivable/SKILL.md §1`。

---

### F10.2 Schema 三处同步

**用户故事**(开发约束):作为开发者,我想改 schema 时三个地方同步更新,以便校验不"对不上"。

**三处**(`BUSINESS_RULES.md R7`):
1. `sql/01_schema.sql` — MySQL 真表
2. `tools/local_validator.py::SQLITE_SCHEMA` — SQLite 镜像
3. `tools/csv_to_sql.py::DERIVED_RULES` — 派生字段(仅当字段是派生时)

**验收标准**:
- AC1:漏一处校验即对不上(铁律)
- AC2:`delivery_order_items.short_qty` 例外说明:同时走 DB 生成列 + 应用层兜底版(见 F5.3)
- AC3:加新派生字段同步更新 `DATA_MODEL.md §5.1` 表格

---

### F10.3 自检门禁(14 步全过)

**用户故事**:作为开发者,我想任何改动都跑一次 14 步自检,以便确认改动没破坏既有逻辑。

**命令**:
```bash
bash scripts/run_local_validation.sh           # 真实数据
bash scripts/run_local_validation.sh --demo    # demo 假数据
```

**14 步覆盖对照**(本 SPECS 功能点 → 步骤号):
| 步骤 | 校验内容 | 覆盖的功能点 |
| --- | --- | --- |
| 1/14 | 基础资料完整性 | F1.1~F1.6 |
| 2/14 | 采购金额 = 明细之和 | F2.2 |
| 3/14 | 入库 ≤ 采购 | F3.1 |
| 4/14 | 合同金额 = 明细之和 | F4.2 |
| 5/14 | 发货 ≤ 合同 | F5.4 |
| 6/14 | 累计出库 vs 累计入库(WARN) | F3.5 |
| 7/14 | 库存对账 | F3.4 |
| 8/14 | 体积小计跨表 | F3.6 |
| 9/14 | UCP600 ±5% | F6.3 |
| 10/14 | credit_note 闭环 | F6.4 |
| 11/14 | 汇率完整性 | F4.3 / F6.1 / F7.1 |
| 12/14 | 收款 vs 合同 | F7.4 |
| 13/14 | 调拨配对 | F8.2 |
| 14/14 | 报价金额 + 派生关系 + subtotal 公式 | F9.1 / F9.2 / F9.3 / F9.4 |

**验收标准**:
- AC1:14 步全过才算改对(`BUSINESS_RULES.md R9`)
- AC2:CI 同样以此为门禁(`scripts/ci.sh` / `.github/workflows/ci.yml`)
- AC3:错误排查见 `VALIDATION_GUIDE §6`

---

## 11. 阶段二规划功能(本阶段不做)

> 以下功能在当前阶段**不实现**,只留接口位置。规划清单源自 `payment-receivable/SKILL.md §7`。本节列出便于追溯,不代表当前系统能力。

| 功能 | 涉及表 | 何时做 |
| --- | --- | --- |
| 供应商付款(AP) | 新建 `supplier_payments` 表 | 阶段二 |
| 多合同合并收款分配 | `receipts` 加 `allocations` 子表 | 阶段二 |
| 汇兑损益月末结转 | `forex_settlements` 表 + 月末脚本 | 阶段二 |
| 应收账龄(AR Aging) | 视图 `v_ar_aging` | 阶段二 |
| 信用证单证管理 | `lc_documents` 表 | 阶段二 |
| 审计日志逻辑触发 | `audit_logs` 表已建,触发器未做 | 阶段二 |

> 当前 `audit_logs` 表是**空壳**(只建表不写入,见 `DATA_MODEL.md §4.8`),所以本 SPECS 不展开其功能点。

---

## 附录 A:文档维护约定

- **加新功能点**:先确认系统**真实已有**该能力(查 `sql/01_schema.sql` 字段 / `tools/local_validator.py` 校验函数),不臆造未来功能;未来功能放 §11 阶段二规划。
- **改 schema**:同步三处(`BUSINESS_RULES.md R7`),并更新本 SPECS 涉及功能点的"涉及数据表"引用。
- **加新校验步骤**:更新 §F10.3 的 14 步覆盖对照表(校验步骤号映射见 `VALIDATION_GUIDE §3`)。
- **真实数据不进仓库**(`BUSINESS_RULES.md R8`):本 SPECS 不引用任何真实客户/供应商/合同数据,示例编号(如 `SC20260726001` / `TR20260729001`)均为格式示例。

## 附录 B:相关文档索引

| 文档 | 作用 |
| --- | --- |
| `docs/DATA_MODEL.md` | 物理数据模型单一事实源(25 张表字段/外键/派生) |
| `docs/BUSINESS_FLOW.md` | 业务流程全景图(9 节点 / 3 角色) |
| `docs/BUSINESS_RULES.md` | 业务规则事实源(R1~R10) |
| `docs/VALIDATION_GUIDE.md` | 14 步校验流程 + 错误排查 |
| `docs/adr/0003-quotation-derive-from-brief.md` | 报价 brief/formal 共用表 + parent_quote_id 派生 + subtotal 直接公式决策 |
| `docs/GLOSSARY.md` | 业务术语表 |
| `.claude/skills/product-params/SKILL.md` | 密度/厚度反推/米重深度规则 |
| `.claude/skills/derived-fields/SKILL.md` | 外径/体积/金额派生深度规则 |
| `.claude/skills/trade-documents/SKILL.md` | 报关/UCP600/credit_note 深度规则 |
| `.claude/skills/payment-receivable/SKILL.md` | 收款/汇率/对账深度规则 |
| `sql/01_schema.sql` | 字段真实性最终校验依据 |

DONE
