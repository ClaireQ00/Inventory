# 进销存管理系统（Inventory System）

一个面向**外贸出口企业**的进销存 + 报关单据 + 应收收款系统。从 Excel 物料台账起步，逐步搭建起完整的 **采购 → 入库 → 库存 → 销售 → 发货 → 报关 → 收款** 业务闭环。

> **一句话定位**：管"物"的流转（进货 / 存货 / 出货）+ 管"单据"的流转（报关 / 短装 / 贷记单）+ 管"钱"的流转（外币收款 / 汇率折算 / 对账）。

> **想快速理解一笔订单怎么走？看 [BUSINESS_FLOW.md](BUSINESS_FLOW.md)** — 业务流程全景图。

---

## 📁 目录结构

```
inventory/
├── .github/                    # GitHub 工作流和 PR 模板
│   ├── workflows/
│   │   └── ci.yml
│   └── pull_request_template.md
├── CONTRIBUTING.md            # 贡献指南
├── scripts/                   # 项目工作流辅助脚本
│   ├── ci.sh                        # 一键 CI (含端到端业务校验)
│   ├── check-sensitive-data.sh      # 敏感数据扫描
│   ├── run_local_validation.sh      # 本地真实数据一键验证
│   ├── launch-module-workflow.sh
│   ├── run-review.sh
│   └── setup-git-hooks.sh
├── tools/                     # 数据导入与校验工具链
│   ├── csv_to_sql.py                # CSV → SQL 通用转换
│   ├── local_validator.py           # SQLite 本地业务校验引擎
│   └── make_demo_data.py            # 生成演示数据
├── sql/                       # SQL 脚本（按顺序执行）
│   ├── 01_schema.sql          # 1. 建库建表（20 张表，含报关+财务+审计模块）
│   ├── 02_seed_data.sql       # 2. 物料数据（来自 Excel，6 条）
│   └── 03_master_data.sql     # 3. 基础资料（仓库/供应商/客户/初始库存）
├── data/                      # 本地真实数据 (已 gitignore, 不进仓库)
│   ├── csv/                         # 真实 CSV 数据
│   ├── sql/                         # 由 CSV 生成的 INSERT
│   ├── db/                          # SQLite 验证库
│   └── logs/                        # 校验报告
├── private/                   # 更机密的资料 (已 gitignore)
├── db/                        # 数据库连接配置（预留）
├── docs/                      # 项目文档
│   ├── README.md              # 本文档（系统架构）
│   ├── BUSINESS_FLOW.md       # 业务流程全景图（一笔订单从询盘到收款）⭐ 新人必看
│   ├── AGENT_GUIDE.md         # Agent/Skill/Hook 协作指南（现状+蓝图）
│   ├── VALIDATION_GUIDE.md    # 真实数据验证流程指南（12 步校验）
│   ├── IMPORT_TEMPLATES.md    # 导入模板说明
│   └── PRIVATE_DATA_GUIDELINES.md  # 真实数据与敏感信息处理指南
└── sample/                    # 示例代码与导入模板
```

---

## 🗄️ 数据库架构

### 整体设计原则

1. **物料字典不带价格**：`products` 只描述"物料长什么样"，价格跟业务单据走
2. **主表 + 明细表**：业务单据（采购单/合同/发货单/报关单）都拆成"单据头 + 商品行"
3. **状态字段**：`draft → confirmed → completed/cancelled`（部分表有中间态如 `partial_received` / `shipped`）
4. **金额用 DECIMAL**：避免浮点精度问题
5. **库存是结果，流水是原因**：`inventory` 表是"现在剩多少"，`stock_logs` 是"为什么剩这么多"
6. **金额四件套铁律**：凡是外币金额必须同时有 `amount + currency + exchange_rate + amount_cny` 四个字段（详见 `CLAUDE.md`）

### 20 张表的关系（按 8 个模块分组）

```
模块1 基础资料 (4 表)
  products ── 物料主数据（字典，不带价格）
  warehouses / suppliers / customers
        │
        ▼
模块2 采购 (2 表)               模块3 销售合同 (2 表)
  purchase_orders                  sales_contracts (金额四件套)
  + purchase_order_items           + sales_contract_items
        │                                │
        ▼                                ▼
模块4 库存 (6 表)               模块5 发货 (2 表)
  stock_in + stock_in_items       delivery_orders
  stock_out + stock_out_items     + delivery_order_items
  inventory (结果)                  (含 actual_quantity / short_qty)
  stock_logs (流水, 自动重建)            │
        │                                ▼
        └─────── 互相校验 ──────→ 模块6 报关 (3 表) [外贸专用]
                                       shipping_records (金额四件套)
                                       + shipping_record_items
                                       credit_notes (差异处理, 金额四件套)
                                              │
                                              ▼
                                     模块7 应收收款 (2 表)
                                       exchange_rates (月固定汇率)
                                       receipts (金额四件套)
                                              │
                                              ▼
                                     模块8 审计 (1 表)
                                       audit_logs (阶段一空壳)
```

### 各表职责速查

| 模块 | 表名 | 说明 |
|------|------|------|
| **基础资料** | `products` | 物料主数据（来自 Excel，含尺寸/重量/外观属性） |
| | `warehouses` | 仓库目录 |
| | `suppliers` | 供应商名录 |
| | `customers` | 客户名录 |
| **采购** | `purchase_orders` | 采购单主表（`status`: draft/confirmed/partial_received/completed/cancelled） |
| | `purchase_order_items` | 采购单明细 |
| **销售** | `sales_contracts` | 销售合同主表（含金额四件套 + 贸易术语 FOB/CIF/CFR/EXW） |
| | `sales_contract_items` | 合同明细（含 `delivered_qty` 已发数量） |
| **库存** | `inventory` | 当前库存（物料+仓库 唯一） |
| | `stock_in` / `stock_in_items` | 入库单 + 明细 |
| | `stock_out` / `stock_out_items` | 出库单 + 明细 |
| | `stock_logs` | 出入库流水（**由校验器自动重建，无 CSV 模板**） |
| **发货** | `delivery_orders` | 发货单主表（`status`: draft/confirmed/shipped/delivered/cancelled） |
| | `delivery_order_items` | 发货明细（含 `quantity` 计划 / `actual_quantity` 实际 / `short_qty` 短装） |
| **报关** | `shipping_records` | 报关单主表（金额四件套 + 集装箱/船名） |
| | `shipping_record_items` | 报关明细（唛头/毛净重/体积/单价） |
| | `credit_notes` | 贷记单（短装/超装差异处理，金额四件套） |
| **应收** | `exchange_rates` | 汇率表（每月 1 日录一次，整月用这条） |
| | `receipts` | 收款单（客户付款，金额四件套，含 T/T/L/C 等付款方式） |
| **审计** | `audit_logs` | 审计日志（**阶段一空壳，无业务逻辑**） |

> 想看一笔订单怎么串起这些表？看 [BUSINESS_FLOW.md](BUSINESS_FLOW.md)。

---

## 🚀 快速开始

### 0. 不想装 MySQL 也能跑（推荐先这样试流程）

仓库自带一套**本地端到端业务校验工具**（用 SQLite，免装任何数据库）：

```bash
# 用假数据跑一遍演示
bash scripts/run_local_validation.sh --demo

# 然后把自己的真实数据按模板填到 data/csv 下, 再跑一次
bash scripts/run_local_validation.sh
```

具体怎么填、校验了什么、报错怎么读，详见 **[docs/VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)**。

### 1. 准备工作

- 安装 MySQL 8.0+
- 确保有创建数据库的权限

### 2. 按顺序执行 SQL

在 MySQL 命令行里依次跑：

```bash
# 1. 建库建表
mysql -u root -p < sql/01_schema.sql

# 2. 写入物料数据
mysql -u root -p < sql/02_seed_data.sql

# 3. 写入基础资料 + 初始库存
mysql -u root -p < sql/03_master_data.sql
```

### 2.5. 用 Excel 模板导入物料

如果你更习惯用 Excel 填写物料清单，仓库也提供了模板和导入脚本：

- 模板文件：`sample/products_template.xlsx`
- 导入脚本：`python3 sample/import_products.py sample/products_template.xlsx --output sample/import_products.sql`
- 运行后生成的 SQL 文件可以通过 MySQL 导入：
  ```bash
  mysql -u root -p inventory_db < sample/import_products.sql
  ```

模板仅需填写 `products` 表对应的字段，`material_id` 和 `spec` 为必填字段。
`outer_diameter` 和 `id_x_od` 可以留空，脚本会在 `inner_diameter` 与 `thickness` 均已填写时自动计算。

或者登录 MySQL 后用 `source` 命令：

```sql
mysql> source /Users/guixinqie/inventory/sql/01_schema.sql;
mysql> source /Users/guixinqie/inventory/sql/02_seed_data.sql;
mysql> source /Users/guixinqie/inventory/sql/03_master_data.sql;
```

### 3. 验证

```sql
USE inventory_db;
SHOW TABLES;                         -- 应该看到 20 张表
SELECT COUNT(*) FROM products;       -- 物料主数据行数
SELECT COUNT(*) FROM inventory;      -- 当前库存行数
```

---

## 🔍 常见查询示例

### Q1：查某个客户的所有合同执行情况（合同数/已发/未发）

```sql
SELECT
    sc.contract_no              AS 合同号,
    p.material_id               AS 物料号,
    p.spec                      AS 规格,
    sci.quantity                AS 合同数,
    sci.delivered_qty           AS 已发数,
    sci.quantity - sci.delivered_qty AS 未发数,
    sci.unit_price              AS 单价
FROM sales_contract_items sci
JOIN sales_contracts sc ON sci.contract_id = sc.id
JOIN products p         ON sci.product_id = p.id
JOIN customers c        ON sc.customer_id = c.id
WHERE c.code = 'W158';
```

### Q2：查所有物料的当前库存（按仓库）

```sql
SELECT
    p.material_id   AS 物料号,
    p.spec          AS 规格,
    w.code          AS 仓库编号,
    w.name          AS 仓库名,
    i.quantity      AS 库存数量
FROM inventory i
JOIN products p   ON i.product_id = p.id
JOIN warehouses w ON i.warehouse_id = w.id
ORDER BY p.material_id, w.code;
```

### Q3：查某物料的出入库历史（流水）

```sql
SELECT
    sl.created_at    AS 时间,
    sl.source_no     AS 单号,
    sl.source_type   AS 类型,
    sl.change_qty    AS 变动数量,
    sl.after_qty     AS 变动后库存,
    w.name           AS 仓库,
    sl.remark        AS 备注
FROM stock_logs sl
JOIN products p   ON sl.product_id = p.id
JOIN warehouses w ON sl.warehouse_id = w.id
WHERE p.material_id = 'M-Q025-002'
ORDER BY sl.created_at DESC;
```

### Q4：低库存预警（低于阈值）

```sql
-- 查库存低于 30 卷的物料
SELECT
    p.material_id, p.spec, w.name AS 仓库, i.quantity
FROM inventory i
JOIN products p   ON i.product_id = p.id
JOIN warehouses w ON i.warehouse_id = w.id
WHERE i.quantity < 30
ORDER BY i.quantity ASC;
```

### Q5：合同 + 库存 联合视图（给客户的关键信息）

> "合同签了多少、发了多少、还差多少、现在仓库还有多少"

```sql
SELECT
    c.code              AS 客户编号,
    c.name              AS 客户名称,
    sc.contract_no      AS 合同号,
    p.material_id       AS 物料号,
    p.spec              AS 规格,
    sci.quantity        AS 合同数,
    sci.delivered_qty   AS 已发数,
    sci.quantity - sci.delivered_qty AS 未发数,
    IFNULL(i.quantity, 0) AS 当前库存,
    w.name              AS 所在仓库
FROM sales_contracts sc
JOIN customers c            ON sc.customer_id = c.id
JOIN sales_contract_items sci ON sc.id = sci.contract_id
JOIN products p             ON sci.product_id = p.id
LEFT JOIN inventory i       ON i.product_id = p.id
LEFT JOIN warehouses w      ON i.warehouse_id = w.id
WHERE sc.status IN ('confirmed', 'delivering')
ORDER BY c.code, sc.contract_no;
```

---

## 📐 字段与单位约定

| 字段 | 单位 | 说明 |
|------|------|------|
| `inner_diameter` 内径 | mm | 统一毫米数值 |
| `inner_diameter_inch` 内径(英寸) | inch | 如 `1/4"`、`1-1/4"` |
| `outer_diameter` 外径 | mm | **= inner_diameter + thickness × 2**（Python 计算）|
| `id_x_od` 内径x外径 | — | 字符串，如 `"6.5x10.5"` |
| `thickness` 壁厚 | mm | |
| `length` 长度 | m | 米 |
| `weight_per_meter` 米重 | **g/m** | 已从 Excel 的 kg/m 换算 |
| `weight` 单件重量 | kg | |
| `quantity` 库存数量 | 卷 | 当前按"卷"管理 |
| `total_amount` / `amount` 业务金额 | 原币种 | 外贸合同/报关/收款默认 USD，记账本位币是 CNY |
| `*_cny` 人民币金额 | CNY | 由 `amount × exchange_rate` 派生，详见 `CLAUDE.md` 金额四件套铁律 |

---

## 🔄 业务流程示例

### 完整流程：从询盘到收款（含报关）

```
1. 新建供应商               → INSERT INTO suppliers ...
2. 录入采购单（草稿）       → INSERT INTO purchase_orders ... (status='draft')
3. 确认采购单               → UPDATE purchase_orders SET status='confirmed' ...
4. 收货 → 入库单            → INSERT INTO stock_in ... + stock_in_items ...
5. 确认入库 → 库存增加      → UPDATE inventory + INSERT INTO stock_logs
6. 新建客户                 → INSERT INTO customers ...
7. 签销售合同               → INSERT INTO sales_contracts + sales_contract_items
   (含金额四件套 + 贸易术语 FOB/CIF)
8. 客户要货 → 发货单        → INSERT INTO delivery_orders + delivery_order_items
9. 发货回写合同已发数量     → UPDATE sales_contract_items SET delivered_qty += ...
10. 仓库装柜 → 出库         → INSERT INTO stock_out + 回填 actual_quantity
11. 报关出口                → INSERT INTO shipping_records + shipping_record_items
    (含唛头/毛净重/体积/金额四件套)
12. 客户付款                → INSERT INTO receipts (金额四件套, 按 paid_date 查汇率)
13. 差异处理（如有短装）    → INSERT INTO credit_notes (resolution='pending' → 'replenish'/'refund'/'writeoff')
```

> **详细的"谁填什么表、过什么校验"全景图**：见 [BUSINESS_FLOW.md](BUSINESS_FLOW.md)

---

## 📝 设计决策记录

### 为什么 `products` 表没有价格字段？

价格是"业务事件"的属性，不是"物料"的属性。

- 采购价 → 在每次采购单上（不同批次可能不同价）
- 销售价 → 在每个销售合同上（不同客户/合同可能不同价）

物料字典保持纯净，只描述"物料本身"。

### 为什么有 `inventory` 表还要 `stock_logs` 表？

- `inventory`：**当前状态**（现在某仓某物料剩多少）
- `stock_logs`：**历史原因**（每次变动是怎么发生的）

两者要能对上：把 `stock_logs` 按物料+仓库汇总 `change_qty`，应该等于 `inventory.quantity`。

类比：银行 APP 显示的"余额"是 `inventory`，"交易明细"是 `stock_logs`。

### 为什么用 `material_id` 而不是自增 ID 做物料编号？

- 自增 `id` 是数据库内部用的（关联外键）
- `material_id`（如 `M-W158-001`）是人类可读的，打印在单据上能看懂

---

## ⚠️ 待完善 / 已知问题

- [ ] `db/` 目录预留：放 Python 数据库连接配置（`db_config.py`）
- [ ] `sample/` 目录预留：放 Python 操作数据库的示例代码
- [ ] 单据号生成规则（如 `PO20260726001`）目前手动指定，后续可写函数自动生成
- [ ] 数据库触发器/存储过程：自动同步 `inventory` 和 `stock_logs`（目前需要应用层保证一致性）

---

## 📞 联系/维护

- 数据来源：`物料.xlsx`（位于 iCloud `进销存管理/` 目录）
- 字段调整时，请同步更新本 README 和 `01_schema.sql`
