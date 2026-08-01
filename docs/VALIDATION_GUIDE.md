# 真实数据验证流程指南

> 目标：用真实数据把整套进销存流程跑通，但**真实数据只留在本地**，绝不进仓库。

---

## 一句话理解整个流程

```
你的 Excel/Numbers ──(另存CSV)──> data/csv/*.csv ──(一键脚本)──> 业务校验报告
                                       ↑                              ↓
                              只放在本地，被 .gitignore 忽略     16 步端到端检查
```

类比：你拿一张空白订单模板（`sample/templates/`），照着真实客户/合同/订单填好（变成 `data/csv/`），然后丢进一台自动质检机（`scripts/run_local_validation.sh`），它告诉你哪里填错了。

---

## 1. 目录约定

| 路径 | 作用 | 是否进仓库 |
| --- | --- | --- |
| `sample/templates/*_template.csv` | 空白模板（表头+1行示例） | ✅ 进仓库 |
| `data/csv/` | 真实数据 CSV | ❌ 不进仓库（已 .gitignore） |
| `data/sql/` | 由 CSV 转换出的 INSERT 语句 | ❌ 不进仓库 |
| `data/db/` | 本地 SQLite 验证库 | ❌ 不进仓库 |
| `data/logs/` | 每次验证的报告 | ❌ 不进仓库 |
| `private/` | 更机密的资料（如对账单扫描件） | ❌ 不进仓库 |

> 检查方法：`git check-ignore -v data/`，如果显示 `.gitignore:12:data/` 就说明被忽略了，可以放心放真实数据。

---

## 2. 快速开始（3 分钟）

### 第一次跑（没有任何数据）

```bash
bash scripts/run_local_validation.sh --demo
```

脚本会自动生成一套**假的演示数据**（物料号都是 `DEMO-`，客户名都是"客户A"），跑完 16 步校验，告诉你整套流程是怎么连起来的。

### 放入真实数据

1. 把模板拷一份到 `data/csv/` 下，并把后缀去掉：
   ```bash
   mkdir -p data/csv
   cp sample/templates/products_template.csv data/csv/products.csv
   cp sample/templates/suppliers_template.csv data/csv/suppliers.csv
   # ... 其余表同理
   ```
2. 用 Excel/Numbers 打开 `data/csv/*.csv`，按真实情况填数据。
3. 跑验证：
   ```bash
   bash scripts/run_local_validation.sh
   ```
4. 看报告。错误必须修，警告（WARN）根据情况判断。

---

## 3. 十六步业务校验

校验逻辑写在 `tools/local_validator.py` 里，对应进销存 + 报关 + 财务 + 报价的真实业务流程：

| 步骤 | 校验内容 | 类比 |
| --- | --- | --- |
| 1/16 | 基础资料完整性（物料/仓库/供应商/客户） | 把通讯录建好 |
| 2/16 | 采购单总金额 = 明细小计之和；采购单 total_volume = Σ 明细 volume_subtotal | 购物车总价 = 商品单价 × 数量加起来；总体积展示给客户 |
| 3/16 | 入库数 ≤ 采购数 | 不能收超过下单的货 |
| 4/16 | 销售合同总金额 = 明细小计之和；合同 total_volume = Σ 明细 volume_subtotal | 同上，只是方向相反 |
| 5/16 | 发货数 ≤ 合同数 | 不能发超过合同约定的货 |
| 6/16 | 累计出库 vs 累计入库（同一仓库同一物料，**负库存报警**） | 银行卡透支,允许但要提醒补钱 |
| 7/16 | 库存表 = 流水累加（对账） | 账户余额 = 流水累加 |
| 8/16 | 明细表体积小计（外观外径²×外观高度×0.93/1e6） | 货柜装多少货要算清楚 |
| 9/16 | **发货单总体积 total_volume = Σ 明细 volume_subtotal（展示统计，WARN 容差 0.01 CBM）** | 给客户看"这张单总共多少立方"，跟报关实际 CBM 是两个概念 |
| 10/16 | 报关实际数 vs 发货单计划数（UCP600 ±5% 容差） | 海关账跟合同账允许 5% 误差 |
| 11/16 | 贷记单闭环（pending 不能挂超过 30 天） | 短装赔偿必须收尾 |
| 12/16 | 汇率表完整性（每月每币种至少一条） | 每月 1 号录汇率,整月用这条 |
| 13/16 | 收款 vs 合同金额（按原币种聚合） | 客户付的款要跟合同对得上 |
| 14/16 | 调拨配对（同 `transfer_ref` 出入库数量必须相等） | 转账流水号两边必须平 |
| 15/16 | 报价金额一致 + 派生关系完整性（主表=Σ明细小计、**主表 total_volume=Σ 明细 total_volume**、formal 必须从 brief 派生、converted 回填合同、subtotal=重量×系数×数量、**快照重量与主数据偏差>5% 提示新增物料/更新主数据(WARN)**） | 报价单是合同的"前身",数字必须自洽 |
| 16/16 | **Packing Plan 公斤价反算**（报价系数×单重 = 应等于的合同单价(原币/件)，差 ≤ 0.01 正常，超差 warn；2026-07-31 修正单位；2026-08-01 单重/系数改为**快照优先**：converted 来源报价快照 → 最新报价快照 → products 主数据兜底，报价谈过新重量不再误报） | 标准成本差异分析：报价是基准,合同是实际,允许微小四舍五入差 |

> 💡 **关于 total_volume 字段**：4 张主表（quotations / sales_contracts / purchase_orders / delivery_orders）都有 `total_volume` 字段，是**展示用统计**（给客户看这张单总共多少立方），= Σ 各自明细表的体积。**跟报关单 `shipping_records.total_cbm` 不是一回事**——后者是装柜后的真实 CBM（要提交海关的数据，可能因拼柜/整柜微调过）。total_volume 用 WARN 级校验（容差 0.01），即使对不上也不阻断流程。

### 自动派生字段

`tools/csv_to_sql.py` 会自动算这些字段，你不用手填：
- `products.outer_diameter` = `inner_diameter` + `thickness × 2`
- `products.id_x_od` = `"{inner}x{outer}"`，例如 `32x40.36`

---

## 4. CSV → SQL 单独使用

如果你要把某张 CSV 转成 SQL（比如要导入到真正的 MySQL）：

```bash
python3 tools/csv_to_sql.py data/csv/products.csv products data/sql/04_products.sql
python3 tools/csv_to_sql.py data/csv/customers.csv customers data/sql/05_customers.sql --mode replace
```

`--mode replace`：主键/唯一冲突时覆盖，适合反复重跑。

生成的 SQL 文件可以直接 `mysql -u root -p inventory_db < data/sql/04_products.sql` 灌入 MySQL。

---

## 5. 单独看本地验证库

`data/db/validation.db` 是一个 SQLite 文件，可以用任何 SQLite 客户端打开看数据：

```bash
# 命令行
sqlite3 data/db/validation.db "SELECT * FROM inventory;"
sqlite3 data/db/validation.db "SELECT material_id, spec FROM products;"

# 或者用 GUI: DB Browser for SQLite / DBeaver
```

---

## 6. 错误排查清单

### 错误：UNIQUE constraint failed

**原因**：你导入的 CSV 里有重复的主键/唯一键（比如同一 `material_id` 出现两次）。

**解决**：检查 CSV 里的编号列，确保唯一。

### 错误：FOREIGN KEY constraint failed

**原因**：CSV 引用了不存在的 ID（比如采购单写了 `supplier_id=99`，但 suppliers 表里没有 99）。

**解决**：先按业务依赖顺序填表（基础资料 → 采购 → 入库 → 销售 → 发货 → 出库 → 库存）。

### 错误：对账不平

**原因**：库存表里的数量 跟 入库 - 出库 对不上。

**解决**：按错误信息里指出的物料 + 仓库，重新核对 `stock_in_items`、`stock_out_items` 和 `inventory` 三张表。

### 错误：累计出库 > 累计入库

**原因**：你出了货但没入库。

**注意**：2026-07-29 起本项由 ERROR 降级为 **WARN**——外贸调拨常"先做后补",允许 source 仓暂时透支,后续补货即可。看到 WARN 不必惊慌,但要计划补货。

**解决**：补入库单，或减少出库数。

### 错误：调拨出入库不配对

**原因**：某个 `transfer_ref` 只有 stock_out 没有 stock_in（或反过来），或两边数量不等。

**举例**：调拨 `TR20260729001` 出库 5 件，入库只录了 3 件 → 报 ERROR「出库 5 ≠ 入库 3，差额 2」。

**解决**：找到该 `transfer_ref` 的另一半单据补上，或修正其中一边数量。在途（已出未到）会报 WARN，到货后入库即可消除。

---

## 7. 隐私保护要点

- 真实客户/供应商/合同/订单/价格 = **敏感数据**
- 这些数据只能放在 `data/` 或 `private/` 下
- 永远不要把它们复制到 `sample/`、`docs/` 或仓库根目录
- 提交前必跑：
  ```bash
  bash scripts/check-sensitive-data.sh
  ```
- 如果你不小心把真实数据 `git add` 了，参考 `docs/PRIVATE_DATA_GUIDELINES.md` 的应急流程

---

## 8. 流程图（一图看懂）

```
sample/templates/*.csv  ←─ 空白模板（进仓库）
            │
            │ 复制 + 填真实数据
            ▼
       data/csv/*.csv    ←─ 真实数据（不进仓库）
            │
            │ run_local_validation.sh
            ▼
   ┌──────────────────────────────┐
   │  tools/local_validator.py    │
   │  1) 建库                      │
   │  2) 导入 CSV                  │
   │  3) 16 步业务校验             │
   │  4) 自动重建流水 + 对账        │
   └──────────────────────────────┘
            │
            ▼
       data/logs/*.log   ←─ 校验报告
       data/db/validation.db  ←─ 可用 SQLite 客户端打开查看
```

---

## 9. 切换到 MySQL

当本地 SQLite 流程跑通后，可以无缝切到 MySQL：

1. 装 MySQL（本机或服务器）
2. 执行建库脚本：`mysql -u root -p < sql/01_schema.sql`
3. 把 CSV 转成 SQL：`python3 tools/csv_to_sql.py data/csv/products.csv products data/sql/04_products.sql`
4. 导入：`mysql -u root -p inventory_db < data/sql/04_products.sql`
5. 业务校验逻辑不变（写在 Python 里，跟数据库无关）

---

## 10. 常用命令速查

```bash
# 一键跑全部流程
bash scripts/run_local_validation.sh

# 用演示数据跑一遍
bash scripts/run_local_validation.sh --demo

# 检查是否有敏感文件要被提交
bash scripts/check-sensitive-data.sh

# 把单张 CSV 转 SQL
python3 tools/csv_to_sql.py data/csv/products.csv products data/sql/04_products.sql

# 看本地验证库内容
sqlite3 data/db/validation.db ".tables"
sqlite3 data/db/validation.db "SELECT * FROM inventory;"

# CI 全套检查
bash scripts/ci.sh
```
