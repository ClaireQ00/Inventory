# 0004. 外键改业务编号引用,弃用 AUTO_INCREMENT id 做关联

## 状态 (Status)

**已接受** — 2026-07-31

## 上下文 (Context)

原设计里所有业务表的外键都用 MySQL `AUTO_INCREMENT id`(INT)做关联,例如:
- `sales_contract_items.contract_id INT REFERENCES sales_contracts(id)`
- `delivery_order_items.contract_id INT REFERENCES sales_contracts(id)`

这套设计在 2026-07-30 用真实数据(Q025 客户 PVC 线管)跑端到端时崩了。根因(`docs/TASKS.md` 坑 3):

**AUTO_INCREMENT 漂移**——多次 `REPLACE INTO` 主表(customers/sales_contracts 等)会把 `id` 不断推高。Q025 客户最初 `id=2`,经几次 REPLACE 后被推到 `id=37`,但所有引用它的子表 `customer_id` 还是写着 `2`。外键瞬间全部指向不存在的记录,数据彻底失联。

短期 workaround 是 `TRUNCATE` 重置 id,但每次重导真实数据都得清库,完全没法用。必须从根上解决。

## 决策 (Decision)

**所有业务表的外键改用业务编号(`VARCHAR(32)`)做关联,不再用 `AUTO_INCREMENT id`。**

具体规则:
- **主表**保留 `id INT AUTO_INCREMENT PRIMARY KEY`(MySQL 要求,且做内部排序/分页用),但**业务编号加 `UNIQUE NOT NULL`**——例如 `customers.code`、`sales_contracts.contract_no`、`products.material_id`。
- **子表**的外键列类型从 `INT *_id` 改成 `VARCHAR(32) *_code` 或 `*_no`——例如 `sales_contract_items.contract_id` → `sales_contract_items.contract_no`。
- **外键约束**`FOREIGN KEY` 全部改写,引用主表的业务编号列——例如 `FOREIGN KEY (contract_no) REFERENCES sales_contracts(contract_no)`。
- **明细行引用**用复合外键——`sales_contract_items` 加 `item_no` 列 + 双唯一键 `(contract_no, item_no)`,子表 `delivery_order_items` 用 `FOREIGN KEY (contract_no, contract_item_no) REFERENCES sales_contract_items(contract_no, item_no)`。理由:用业务行号(item_no="001")定位明细行,不依赖会漂移的明细表 id。
- **多态软关联保留 INT**——`stock_logs.source_id`、`audit_logs.record_id` 这种"一张子表关联多张主表"的场景没法用业务编号(不同主表编号格式不一),保留 INT 但**不建外键约束**,纯应用层维护。

涉及范围:36 个外键列、35 个 FK 约束、22 张表。

## 理由 (Rationale)

### 为什么用业务编号,不用 id

**1. 业务编号人读得懂,排错快。**

`SC20260730001`(合同号) 一眼能看出"2026年7月30号第001单",`customer_id=37` 看不出是哪家客户。报错信息、SQL 日志、CSV 数据对账,业务编号都更直观。

**2. 业务编号在 REPLACE 后不变。**

`REPLACE INTO customers(code, name) VALUES ('Q025', '印尼大雄')` 跑 10 次,`code='Q025'` 永远不变(因为 UNIQUE 约束命中同一行),只有 `id` 会因为 DELETE+INSERT 循环而漂移。子表用 `customer_code` 引用就永远稳。

**3. CSV 数据天然用业务编号做主键。**

CSV 是项目的"事实源"(`docs/PRIVATE_DATA_GUIDELINES.md`)。`sales_contract_items.csv` 里写"属于合同 SC20260730001"是天经地义的,但 CSV 里**根本没有 id 列**(id 是落库时才生成的)。如果外键用 id,从 CSV 导入数据时必须先 INSERT 主表查 id、再写子表,事务复杂;改成业务编号后,直接按编号 REPLACE 即可,顺序无关。

### 备选方案对比(真实讨论,不是走过场)

| 方案 | 优点 | 致命缺点 | 结论 |
| --- | --- | --- | --- |
| **A. 继续 INT id** | 标准做法、占用空间小 | AUTO_INCREMENT 漂移无解,真实数据重导每次塌方 | **否决** |
| **B. 用 id 但加 ON UPDATE CASCADE** | 改 id 时子表自动跟随 | 漂移本身就不该发生;CASCADE 改主键 id 性能差,且 REPLACE 触发 DELETE 不是 UPDATE,CASCADE 也接不住 | **否决** |
| **C. 改业务编号做外键(本次方案)** | 漂移消失、人能读、CSV 友好 | 子表 FK 列从 INT 变 VARCHAR(32),索引/存储成本略增 | **采用** |
| **D. 用 UUID** | 全局唯一、永不漂移 | 完全不可读,CSV 数据没法填,overengineered | **否决** |

选 C。VARCHAR(32) 索引虽然比 INT 慢一点,但本系统数据量小(单表预计 < 10 万行),性能差距可以忽略;换来的是**数据永不失联 + CSV 友好 + 人可读**,绝对划算。

### 为什么明细行用复合外键

业务里"发货单明细第 1 行 对应 合同明细第 1 行"是高频关系。原来用 `delivery_order_items.contract_item_id INT REFERENCES sales_contract_items(id)`,但 `sales_contract_items.id` 一样会漂移。

改成复合外键后:`FOREIGN KEY (contract_no, contract_item_no) REFERENCES sales_contract_items(contract_no, item_no)`——子表写"属于合同 SC20260730001 的第 001 行",跟 id 漂移彻底无关。代价是子表要多一个 `contract_item_no VARCHAR(8)` 列,但这列本来就要存(语义就是行号),不浪费。

## 后果 (Consequences)

### 正面后果

- **AUTO_INCREMENT 漂移彻底根治**——业务编号 REPLACE 多少次都不影响外键。
- **CSV ↔ DB 完全对齐**——CSV 写业务编号,数据库存业务编号,数据流无转换。
- **排错友好**——日志/报错里出现的都是业务编号,人眼直接读。

### 负面后果 / 取舍

- **索引/存储成本略增**——VARCHAR(32) FK 列比 INT 大。缓解:数据量小(< 10 万行),实测可忽略。
- **复合外键写法稍复杂**——子表要同时存 `contract_no` + `contract_item_no` 两列才能引用一行明细。缓解:语义就是行号,本来就要存,不算额外负担。
- **多态软关联仍是 INT**——`stock_logs.source_id` 这种跨表软关联保留 INT,但放弃外键约束。缓解:这类表数量少(2 张),应用层维护一致性。
- **同步义务维持"四处",新增一次性迁移义务**——R7 的四处(schema/SQLite/DERIVED_RULES/模板)照旧,本次另加两件一次性的事:① 老数据迁移脚本 `tools/migrate_id_to_code.py`;② 现有 CSV/示例数据里的 `*_id` 值改业务编号。详见 CLAUDE.md "改 schema 必须 sync 的四个地方"。

## 相关 (Related)

- **关联文档**:
  - `docs/BUSINESS_RULES.md R7`(schema 同步义务。实施本文时 R7 写的还是"三处同步",本次未改 R7 条文,但实务上另需同步"CSV 模板示例值"一处;2026-07-30 起 R7 已升级为"四处同步",以现状为准)
  - `docs/DATA_MODEL.md`(字段清单已按新业务编号字段更新)
  - `docs/IMPORT_TEMPLATES.md` 坑 4(已改写为"已修复(ADR-0004)")
  - `docs/TASKS.md` 坑 3(AUTO_INCREMENT 漂移的根因记录)
- **关联代码**:
  - `sql/01_schema.sql`(36 个 *_id 改 *_code/no,35 个 FK 约束改写)
  - `tools/local_validator.py::SQLITE_SCHEMA`(22 张表同步新字段)
  - `tools/local_validator.py`(16 个 check_* 函数约 30 处 JOIN 改业务编号等值连接)
  - `sample/templates/*_template.csv`(18 个模板表头改名)
  - `tools/migrate_id_to_code.py`(老格式数据迁移脚本,本次新增)
- **关联 ADR**:无(本次是独立决策,未取代旧 ADR)

DONE
