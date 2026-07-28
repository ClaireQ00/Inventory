---
name: derived-fields
description: 进销存项目的派生字段"加算 + 反向校验"完整规则集。当用户处理 products / purchase_order_items / sales_contract_items / delivery_order_items 中的派生字段（外径、内径外径串、单件体积、体积小计、金额小计等），做 CSV 到 SQL 的转换，运行 tools/csv_to_sql.py 或 scripts/run_local_validation.sh，或者问到"外径公式"、"CBM"、"装箱体积"、"虚标"、"虚重"、"虚米"、"appearance_outer"、"Unit Size"时使用此 skill。注意：涉及产品类别(线管/钢丝管)、密度、厚度反推、米重/单重 5% 容差的，请改用 product-params skill。
allowed-tools: Read, Grep, Glob, Bash(python3:*)
---

# 派生字段加算与反向校验 · 完整规则集

## ⏱️ 5 分钟速查卡（没时间就只看这 3 条）

1. **铁律**：派生字段（外径 / 体积 / 金额小计）**不让人手填**；如果人填了，**必须对得上公式**（容差内），否则报错阻止生成 SQL
2. **必看**：客户虚标字段（`virtual_weight` 虚重 / `virtual_length` 虚米）**不算错**，跳过校验——这是业务约定，别去"纠正"
3. **闪人**：如果是密度 / 厚度反推 / 米重 → `product-params`；如果是报关 / 短装 → `trade-documents`

---

## 谁会用这个 skill

| 角色 | 关心什么 | 重点看哪节 |
| --- | --- | --- |
| 数据录入员 | CSV 留空的字段会不会自动算 | §1 全部公式、§2 加算逻辑 |
| QA / 验收 | 手填的派生字段对不对 | §3 反向校验、§4 容差模式 |
| 仓库保管员 | 体积小计 / 装箱体积怎么来的 | §1.4 体积公式、§1.5 体积小计 |
| 外贸业务经理 | 金额小计 / 单价×数量 对不对 | §1 各表的 subtotal |

## 一句话总结

凡是能从其它字段算出来的字段，**不让人手填**；如果人填了，**必须对得上公式**，否则报错。客户虚标字段（虚重/虚米）**例外**，不算错。

> **产品类别相关的参数（密度、厚度反推、米重/单重 5% 容差）已拆分到 `product-params` skill**。本 skill 只管"行内公式"——外径、内径外径串、体积、金额小计、体积小计。

---

## 1. 全部公式一览

### 1.1 products 表（物料主数据）

| # | 字段 | 公式 | 单位 | 容差 | 备注 |
| --- | --- | --- | --- | --- | --- |
| A1 | `outer_diameter` 外径 | `inner_diameter + thickness × 2` | mm | 0.05 mm | 类比：管子外径 = 内径 + 两边壁厚 |
| A2 | `id_x_od` 内径外径串 | `"{inner}x{outer}"` | 字符串 | — | 例：`32x40.36` |
| A4 | `volume` 单件体积 | `appearance_outer² × appearance_height × 0.93 / 1e6` | m³ (CBM) | 0.001 m³ | 外观尺寸(cm)，0.93是装箱系数 |
| A4b | `volume_subtotal` 体积小计 | 同 A4 (products 表里语义等价) | m³ | 0.001 m³ | 兼容字段 |

> **A3 单件重量 / E1 米重 / 厚度反推 / 密度公式** → 见 `product-params` skill（依赖产品类别）

### 1.2 业务单据明细表（共同公式）

适用表：`purchase_order_items` / `sales_contract_items` / `delivery_order_items`

| # | 字段 | 公式 | 单位 | 容差 | 备注 |
| --- | --- | --- | --- | --- | --- |
| C1/C3 | `subtotal` 金额小计 | `quantity × unit_price` | CNY | 0.01 | 数量 × 单价 |
| D1 | `volume_subtotal` 体积小计 | `单件体积 × quantity` | CBM | 0.01 | **跨表**：单件体积从 products 表查 |

### 1.3 业务单据主表（在 local_validator 里校验，不在 csv_to_sql）

| # | 字段 | 公式 | 校验位置 |
| --- | --- | --- | --- |
| C2 | `purchase_orders.total_amount` | `SUM(purchase_order_items.subtotal)` | `check_purchase_orders()` |
| C4 | `sales_contracts.total_amount` | `SUM(sales_contract_items.subtotal)` | `check_sales_contracts()` |
| C5 | `purchase_order_items.received_qty` | `SUM(stock_in_items.quantity where 同po+product)` | `check_stock_in_vs_purchase()` |
| C6 | `sales_contract_items.delivered_qty` | `SUM(delivery_order_items.quantity where contract_item_id)` | `check_delivery_vs_contract()` |

---

## 2. 虚标字段（重要业务约定）

外贸业务里，客户有时要求"虚标"——单据上写一个比实际值大的数字。**这不是错**，是客户要求。

| 字段 | 含义 | 例子 | 处理方式 |
| --- | --- | --- | --- |
| `virtual_weight` 虚重 | 客户指定的虚标重量 | 实重35kg，客户要求写38kg → 虚重3kg差 | **不参与加算，不参与反向校验** |
| `virtual_length` 虚米 | 客户指定的虚标长度 | 实长46m，客户要求标50m → 虚米4m差 | 同上 |

**关键：** 不要把 `virtual_weight` 跟 `weight` 混淆；不要用 `virtual_weight` 反推 `weight_per_meter`。

---

## 3. 外观尺寸（appearance_outer / appearance_height）

- 这些字段**手填**（卡尺测量），不参与公式计算
- 单位：cm（不是 mm！）
- 用于计算 `volume`（单件体积）
- 外贸单据上的 **Unit Size（长x宽x高 cm）** = 这两个字段的来源
- 客户可以提供一张"产品外观尺寸对照表"，未来会用一个独立的 skill（`appearance-size-recommender`）从历史数据里推荐合理的外观尺寸

---

## 4. 单位约定速查表

| 字段类别 | 单位 | 说明 |
| --- | --- | --- |
| 内径/外径/厚度 | **mm** | 毫米 |
| 长度 `length` | **m** | 米 |
| 米重 `weight_per_meter` | **g/m** | 克每米 |
| 单件重量 `weight` | **kg** | 千克 |
| 外观外径/高度 | **cm** | 厘米（容易踩坑！） |
| 单件体积 `volume` | **CBM (m³)** | 立方米 |
| 金额 | **CNY** | 人民币元 |
| 数量 `quantity` | 件/卷 | 整数 |

---

## 5. 加算规则（缺列时自动补）

**触发条件：** CSV 里的派生列没出现，或者值为空。

**动作：**
- 如果 CSV 根本没这一列 → `ensure_derived_columns()` 自动把它加进 fields
- 如果 CSV 有这列但值为空 → `apply_derived_rules()` 按公式算后填进去
- 加算成功会在控制台打印 `[INFO] [products 第 N 行] 自动计算 outer_diameter = ...`

**条件：** 依赖字段必须都存在且非空，否则跳过（信息不全无法算）

**底层代码：** `tools/csv_to_sql.py::apply_derived_rules()` 的 `if current is None or current == ""` 分支

---

## 6. 反向校验规则（填错时阻止生成）

**触发条件：** CSV 里手填了派生列的值，且能算出公式值。

**动作：** 比较手填值跟公式值的差距，超过容差就报错。

**关键点：**
- 字符串派生列（`tolerance: None`，如 `id_x_od`）**不做反向校验**
- 虚标字段（`virtual_weight` / `virtual_length`）**不进 DERIVED_RULES**，所以也不会校验
- 一旦发现 1 处不符，**停止写入 SQL 文件**，避免污染数据库
- 控制台输出形如：
  ```
  [ERROR] [products 第 3 行] 字段 outer_diameter 手填值 99.99 与公式计算值 18.5
          相差 81.49 (超过容差 0.05), 请核对公式或数据
  ```

**底层代码：** `tools/csv_to_sql.py::apply_derived_rules()` 的 `else` 分支

---

## 7. 推荐工作流

### 7.1 用户填了 products.csv

```bash
# 1. 转换 (会自动加算 outer_diameter/id_x_od/weight/volume, 反向校验所有公式)
python3 tools/csv_to_sql.py data/csv/products.csv products data/sql/04_products.sql

# 2. 如果上面的命令报错, 修 CSV 后重跑
# 3. 成功后导入 MySQL
mysql -u root -p inventory_db < data/sql/04_products.sql
```

### 7.2 用户填了带明细的单据（如采购单）

```bash
# 主表
python3 tools/csv_to_sql.py data/csv/purchase_orders.csv purchase_orders data/sql/06_po.sql
# 明细表 (会自动算 subtotal 和 volume_subtotal)
python3 tools/csv_to_sql.py data/csv/purchase_order_items.csv purchase_order_items data/sql/07_poi.sql
```

### 7.3 端到端验证（推荐每次都跑）

```bash
bash scripts/run_local_validation.sh
```

这会跑全部 8 步校验，包括跨表体积校验。

---

## 8. 加新公式

### 8.1 行内能算的（只依赖同行字段）

加到 `tools/csv_to_sql.py` 的 `DERIVED_RULES`：

```python
"products": {
    "新字段名": {
        "expr": lambda row: _safe_mul(_to_float(row.get("依赖1")), _to_float(row.get("依赖2"))),
        "depends_on": ["依赖1", "依赖2"],
        "tolerance": 0.01,  # 数值容差, None 表示不校验
        "description": "新字段 = 依赖1 × 依赖2",
    },
}
```

### 8.2 跨表才能算的（如 volume_subtotal 需要 products.volume）

**不能加到 csv_to_sql**（它没有数据库连接）。加到 `tools/local_validator.py`：

```python
def check_xxx(conn, report):
    print("[N/8] 校验 xxx...")
    cur = conn.cursor()
    cur.execute("SELECT ... FROM ...")
    for ...:
        if 实际值 != 期望值:
            report.error(...)
```

然后在 `run_validation()` 里加上 `check_xxx(conn, report)`，并把步骤编号更新。

---

## 9. 给 Claude 自己的提醒（处理此类任务时遵循）

- ❌ 不要建议用户手填 `outer_diameter` / `id_x_od` / `volume` / `subtotal` / `volume_subtotal`
- ❌ 不要用 `virtual_weight` 反推 `weight` 或 `weight_per_meter`
- ✅ 如果用户问"怎么填外径/体积"，告诉他们"不用填，脚本会自动算"
- ✅ 如果转换报错，先看错误信息里的行号，去 CSV 对应行核对依赖字段
- ✅ 加新公式时，必须配套写 `depends_on` 和 `tolerance`，否则反向校验不生效
- ✅ 跨表公式（依赖其它表的数据）要加到 `local_validator.py`，不是 `csv_to_sql.py`
- ✅ 修改公式后，同步更新这份 skill 文档的第 1 节
- ➡️ **涉及重量/米重/厚度/密度/产品类别时，去看 `product-params` skill，不是这里**

---

## 10. 完整校验流程图

```
CSV 输入
  │
  ▼
tools/csv_to_sql.py
  │
  ├─ 行内公式加算 (A1/A2/A3/A4/C1/D1...)
  ├─ 行内反向校验 (手填值 vs 公式值)
  │
  ▼
SQL 文件 (如果反向校验失败则不生成)
  │
  ▼
tools/local_validator.py
  │
  ├─ 导入全部 CSV 到 SQLite
  ├─ 跨表公式校验 (C2/C4/C5/C6/D1 跨表版)
  ├─ 业务规则校验 (入库≤采购, 发货≤合同, 出库≤入库)
  └─ 库存对账 (流水累加 = 库存表)
  │
  ▼
校验报告 (data/logs/*.log)
```

---

## 🔗 跨 skill 协作场景

### 场景：装柜出体积小计（derived-fields ↔ trade-documents）

**触发**：发货装柜，报关单需要每行体积数据

**协作顺序**：
1. 先用 **derived-fields**（本 skill）算出 `products.volume`（单件体积）+ `delivery_order_items.volume_subtotal`（这行体积小计 = 单件体积 × 数量）
2. 再让 **trade-documents** 把体积带到 `shipping_record_items.unit_volume`（报关单的单件体积字段）

**举例**：products.volume = 0.0446 CBM，发货 95 件
- Step 1（derived-fields）：volume_subtotal = 0.0446 × 95 = 4.237 CBM
- Step 2（trade-documents）：shipping_record_items.unit_volume = 0.0446（沿用单件值）

### 场景：录新物料（product-params → derived-fields）

**触发**：新物料入库，需要录 `products` 表

**协作顺序**：
1. 先用 **product-params** 算厚度 / 米重 / 单重（依赖产品类别的密度）
2. 再用 **derived-fields** 算外径 / id_x_od / volume（纯几何/外观尺寸，不依赖类别）

**关键**：本 skill **不算厚度/米重**——那需要产品类别（线管/钢丝管）信息，归 product-params。

---

## 11. 相关文件索引

| 文件 | 作用 |
| --- | --- |
| `tools/csv_to_sql.py` | 行内派生规则定义 + 加算 + 反向校验 |
| `tools/local_validator.py` | 跨表校验 + 业务规则校验 |
| `scripts/run_local_validation.sh` | 一键跑全套校验 |
| `scripts/ci.sh` | CI 跑演示数据验证（任何代码改动后） |
| `docs/VALIDATION_GUIDE.md` | 给人看的校验流程指南 |
| `sql/01_schema.sql` | 字段定义（看这里确认字段类型/单位） |
| `tools/make_demo_data.py` | 生成演示数据（带正确公式值的范例） |
