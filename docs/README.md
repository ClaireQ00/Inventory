# 进销存管理系统（Inventory System）

一个面向**线管/管材制造企业**的进销存管理系统。从 Excel 物料台账起步，逐步搭建起完整的采购 → 入库 → 库存 → 销售 → 发货业务闭环。

> **一句话定位**：管"物"的流转（进货、存货、出货），不管"钱"的谈判（报价、合同金额除外）。

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
│   ├── ci.sh
│   ├── launch-module-workflow.sh
│   ├── run-review.sh
│   └── setup-git-hooks.sh
├── sql/                       # SQL 脚本（按顺序执行）
│   ├── 01_schema.sql          # 1. 建库建表（16 张表）
│   ├── 02_seed_data.sql       # 2. 物料数据（来自 Excel，6 条）
│   └── 03_master_data.sql     # 3. 基础资料（仓库/供应商/客户/初始库存）
├── db/                        # 数据库连接配置（预留）
├── docs/                      # 项目文档
│   ├── README.md              # 本文档
│   └── AGENT_GUIDE.md         # Agent/Skill/Hook 协作指南
└── sample/                    # 示例代码（预留）
```

---

## 🗄️ 数据库架构

### 整体设计原则

1. **物料字典不带价格**：`products` 只描述"物料长什么样"，价格跟业务单据走
2. **主表 + 明细表**：业务单据（采购单/合同/发货单）都拆成"单据头 + 商品行"
3. **状态字段**：`draft → confirmed → completed/cancelled`
4. **金额用 DECIMAL**：避免浮点精度问题
5. **库存是结果，流水是原因**：`inventory` 表是"现在剩多少"，`stock_logs` 是"为什么剩这么多"

### 16 张表的关系

```
                  ┌──────────────────┐
                  │  products        │  物料主数据（字典）
                  │  物料长什么样     │
                  └────────┬─────────┘
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
      ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ suppliers    │    │ warehouses   │    │ customers        │
│ 供应商        │    │ 仓库          │    │ 客户              │
└──────┬───────┘    └──────┬───────┘    └────────┬─────────┘
       │                   │                     │
       ▼                   ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ purchase_    │    │ inventory    │    │ sales_contracts  │
│ orders 采购单│    │ 当前库存      │    │ 销售合同          │
│ + 明细       │    └──────┬───────┘    │ + 明细            │
└──────┬───────┘           │            └────────┬─────────┘
       │                   │                     │
       ▼                   ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│ stock_in     │    │ stock_out    │    │ delivery_orders  │
│ 入库单+明细  │    │ 出库单+明细  │    │ 发货单+明细      │
└──────┬───────┘    └──────┬───────┘    └──────────────────┘
       │                   │                     │
       └───────────────────┼─────────────────────┘
                           ▼
                    ┌──────────────┐
                    │ stock_logs   │  统一流水（对账用）
                    └──────────────┘
```

### 各表职责速查

| 模块 | 表名 | 说明 |
|------|------|------|
| **基础资料** | `products` | 物料主数据（来自 Excel Sheet1，31 个属性字段）|
| | `warehouses` | 仓库目录 |
| | `suppliers` | 供应商名录 |
| | `customers` | 客户名录 |
| **采购** | `purchase_orders` | 采购单主表 |
| | `purchase_order_items` | 采购单明细 |
| **销售** | `sales_contracts` | 销售合同主表 |
| | `sales_contract_items` | 合同明细（含 `delivered_qty` 已发数量）|
| **库存** | `inventory` | 当前库存（物料+仓库 唯一）|
| | `stock_in` / `stock_in_items` | 入库单 + 明细 |
| | `stock_out` / `stock_out_items` | 出库单 + 明细 |
| | `stock_logs` | 出入库流水 |
| **发货** | `delivery_orders` | 发货单主表 |
| | `delivery_order_items` | 发货明细（关联合同明细）|

---

## 🚀 快速开始

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
SHOW TABLES;                         -- 应该看到 16 张表
SELECT COUNT(*) FROM products;       -- 应该是 6
SELECT COUNT(*) FROM inventory;      -- 应该是 6
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
| 金额字段（`unit_price`/`amount` 等）| CNY | 人民币 |

---

## 🔄 业务流程示例

### 完整流程：从采购到发货

```
1. 新建供应商               → INSERT INTO suppliers ...
2. 录入采购单（草稿）       → INSERT INTO purchase_orders ... (status='draft')
3. 确认采购单               → UPDATE purchase_orders SET status='confirmed' ...
4. 收货 → 入库单            → INSERT INTO stock_in ... + stock_in_items ...
5. 确认入库 → 库存增加      → UPDATE inventory + INSERT INTO stock_logs
6. 新建客户                 → INSERT INTO customers ...
7. 签销售合同               → INSERT INTO sales_contracts + sales_contract_items
8. 发货 → 发货单            → INSERT INTO delivery_orders + delivery_order_items
9. 发货回写合同已发数量     → UPDATE sales_contract_items SET delivered_qty += ...
10. 出库 → 库存减少         → INSERT INTO stock_out + UPDATE inventory + stock_logs
```

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
