# 0002. 仓库调拨复用 stock_in/stock_out + transfer_ref 软关联,不建独立 transfer 表

## 状态 (Status)

**已接受** — 2026-07-29

## 上下文 (Context)

系统需要支持**仓库间调拨**——把货从 A 仓搬到 B 仓。这在业务上是常见操作:总仓发到分仓、本地仓调拨到港口仓备装柜等。

**要决定的问题**:调拨这个业务,在数据库里怎么建模?有两个候选:

1. **建独立的 `transfers` 表**(主表 + 明细表)——把调拨当成跟"采购入库""销售出库"平级的独立单据类型。
2. **复用现有的 `stock_in` / `stock_out` 表**,加一个 `transfer_ref` 字段把配对的出入库串起来。

这个决策影响:表数量、流水/对账逻辑要不要重写、调拨跟报关/收款流程的隔离性。详细分析见 `docs/DESIGN.md §5`、`docs/DATA_MODEL.md §6`、`BUSINESS_RULES.md R3.5`。

触发本次决策的直接原因:2026-07-29 客户确认外贸调拨常"先做后补"(源仓先出库、目标仓后入库,货物在途),需要系统支持这种时序。

## 决策 (Decision)

**复用 `stock_in` / `stock_out` 表,加 `transfer_ref` 软关联字段 + `in_type='transfer'` / `out_type='transfer'` 标识,不建独立 `transfers` 表。**

- 调拨 = 一对配对的出入库单,两边填同一个 `transfer_ref` 号(如 `TR20260729001`)。
- `stock_in.in_type` ENUM 已含 `'transfer'`(sql/01_schema.sql:358);`stock_out.out_type` ENUM 已含 `'transfer'`(sql/01_schema.sql:408)。
- 两边都有 `transfer_ref VARCHAR(32)`(sql/01_schema.sql:366 / 416),各建索引 `idx_si_transfer` / `idx_so_transfer`(sql/01_schema.sql:379 / 429)加速按号聚合。
- 配对校验:`tools/local_validator.py::check_transfer_pairs`(步骤 14/16)。

## 理由 (Rationale)

### 为什么选软关联,不建独立表

**1. 调拨在业务上是"特殊出入库",不是独立单据类型。**
证据:`in_type` / `out_type` 的 ENUM 从建模之初就**包含 `'transfer'`**(`stock_in.in_type` ENUM: `purchase`/`production`/`transfer`/`return`;`stock_out.out_type` ENUM: `sale`/`production`/`transfer`/`scrap`)。这说明调拨被设计成出入库的**子类型**,而不是平行的新单据。建独立表等于把一个子类型硬拔成主类型,跟现有模型冲突。

**2. 复用现有流水和对账,零额外代码。**
`rebuild_stock_logs`(local_validator.py:839-895)重建流水时**不区分** `in_type`/`out_type`,所有 `confirmed` 状态的出入库都进流水。`check_reconciliation`(步骤 7/16)按 `(product_id, warehouse_id)` 聚合流水对比库存表,**自动覆盖调拨**——源仓减、目标仓加,天然平衡。如果建独立 `transfers` 表,这套流水/对账逻辑要单独维护一份,且调拨数据不进主流水会出现"库存对不上"。

**3. 配对完整性靠应用层兜底,够用。**
`check_transfer_pairs`(local_validator.py:1208-1270)按 `(transfer_ref, product_id)` 聚合两边数量:
- 出库总量 ≠ 入库总量 → **ERROR**(差额、漏录或在途异常)
- 只有一边(只出库没入库,或反之)→ **WARN**(在途或方向录错)

`idx_si_transfer` / `idx_so_transfer` 两个索引就是为这种"按 `transfer_ref` 聚合"的查询加速而建的。

**4. 表数量零增量。**
独立 `transfers` 表方案要 +1 主表 +1 明细(共 2 张新表),还要写它跟 `stock_in`/`stock_out` 的同步逻辑(调拨确认时要不要自动生成出入库单?)。软关联方案 0 张新表、0 同步逻辑。`docs/DATA_MODEL.md §6.4` 给出完整对比表。

### 备选方案对比(真实讨论)

| 维度 | 方案 A:独立 `transfers` 表 | 方案 B:软关联(采用) |
| --- | --- | --- |
| 表数量 | +2(主表 + 明细) | +0 |
| 外键约束 | 强(`transfers` ↔ `transfer_items` 有外键) | 弱(`transfer_ref` 无外键,可填错或漏填) |
| 流水/对账复用 | 不能直接复用,要单独写调拨的流水逻辑 | 完全复用,自动覆盖 |
| 报关/收款隔离 | 需额外保证调拨不进外贸流程 | `out_type='transfer'` 天然不被报关/收款流程识别,自动隔离 |
| 配对校验 | DB 外键保证"每条明细属于哪个调拨",但不保证"出=入" | 靠 `check_transfer_pairs` 应用层聚合校验 |
| "先做后补"时序 | 调拨主表要先建,源仓出库时主表已存在,跟"先出后入"的时序别扭 | 出库单和入库单各自独立,时序自由 |
| 维护成本 | 多一套表 + 同步逻辑 + 流水逻辑 | 多一个软关联字段 + 一个 check 函数 |

**结论**:方案 A 的强外键约束优势,在本系统里价值有限——因为"出=入"这个核心约束,**外键根本保证不了**(外键只能保证明细归属,不能保证数量相等),还是要靠应用层聚合校验。既然应用层兜底不可避免,那为了外键多背 2 张表 + 同步逻辑就不划算。选 B。

### 配套决策:负库存校验为何从 ERROR 降为 WARN

本次决策还连带调整了 `check_stock_out_vs_inventory`(步骤 6/16,local_validator.py:790):累计出库 > 累计入库从 ERROR 降级为 **WARN**。

理由:外贸调拨常"先做后补"——源仓先出库(此时源仓透支)、目标仓后入库(货物还在路上)。如果硬拦 ERROR,这种正常的在途业务跑不通。降级 WARN 提醒"请补货",但不阻断流程。

**注意**:这跟对账(`check_reconciliation`,F3.4)不同。**对账仍是 ERROR**——库存表跟流水累加对不上是硬错(可能漏录出入库),不允许。降级的只是"单次出库超当前库存"这一项。

## 后果 (Consequences)

### 正面后果

- **零新表**:不动 schema 主结构,加 2 个字段 + 2 个索引 + 1 个 ENUM 值就支持调拨。
- **复用主流程**:流水重建、库存对账、状态机(`confirmed`/`draft`)全部自动覆盖调拨,不用单独维护。
- **隔离性天然**:`out_type='transfer'` / `in_type='transfer'` 不被报关(`shipping_records`)、收款(`receipts`)、UCP600 流程识别,调拨自动不进外贸单据流程(R3.5 配套规则)。
- **时序灵活**:出库单和入库单各自独立,支持"先出后入"的在途业务。

### 负面后果 / 取舍

| 代价 | 说明 | 缓解措施 |
| --- | --- | --- |
| **无外键约束** | `transfer_ref` 是软关联,可以填错、漏填或两边填不一样的值 | `check_transfer_pairs` 兜底校验:单边 WARN、差额 ERROR |
| **跨仓不强制** | 源仓和目标仓可以填同一个仓(逻辑错误,DB 不拦) | 应用层后续可加"源仓 ≠ 目标仓"校验,本阶段不做 |
| **配对不立即报错** | 单边调拨(只出库没入库)不会在录入时立刻报错 | 单边 → WARN 提醒;差额 → ERROR 拦截 |
| **依赖人工录对号** | 两边必须填**完全相同**的 `transfer_ref` 字符串才能配对 | 业务约定编号格式(如 `TR` + 日期 + 序号),靠校验发现不一致 |

**核心权衡**(引自 `docs/DATA_MODEL.md §6.4`):"这个代价(软关联无外键约束)远小于多维护一张表 + 它的明细 + 它跟流水的同步逻辑。"

## 相关 (Related)

- **关联文档**:
  - `docs/DESIGN.md §5`(调拨软关联设计,含理由 + 代码证据 + 取舍表)
  - `docs/DATA_MODEL.md §6`(调拨建模详述,含 §6.4 对比表)
  - `docs/BUSINESS_RULES.md R3.5`(多仓库调拨配对铁律,2026-07-29 新增)
- **关联代码**:
  - `sql/01_schema.sql:358`(`stock_in.in_type` ENUM 含 `'transfer'`)
  - `sql/01_schema.sql:366`(`stock_in.transfer_ref` 字段)
  - `sql/01_schema.sql:379`(`idx_si_transfer` 索引)
  - `sql/01_schema.sql:408`(`stock_out.out_type` ENUM 含 `'transfer'`)
  - `sql/01_schema.sql:416`(`stock_out.transfer_ref` 字段)
  - `sql/01_schema.sql:429`(`idx_so_transfer` 索引)
  - `tools/local_validator.py:790`(`check_stock_out_vs_inventory`,负库存降 WARN)
  - `tools/local_validator.py:1208-1270`(`check_transfer_pairs`,配对校验)
  - `tools/local_validator.py:839-895`(`rebuild_stock_logs`,流水重建,不区分 in/out_type)

DONE
