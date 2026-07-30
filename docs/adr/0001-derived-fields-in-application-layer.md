# 0001. 派生字段走应用层(Python),不使用数据库生成列

## 状态 (Status)

**已接受** — 2026-07-29

## 上下文 (Context)

外贸进销存系统里有大量"派生字段"——也就是**能由其他字段算出来**的字段,不需要人手填。典型例子:

- `amount_cny`(本币金额)= `amount × exchange_rate`
- `volume_subtotal`(体积小计)= `unit_volume × quantity`
- `outer_diameter`(外径)= `inner_diameter + thickness × 2`
- `short_qty`(短装数)= `quantity - actual_quantity`

系统共 8 张表、19 个这类字段(完整清单见 `docs/DATA_MODEL.md §5.1`)。

**要决定的问题**:这些派生字段在哪一层计算?有三个候选位置:

1. **数据库层**——用 MySQL `GENERATED COLUMN`(`GENERATED ALWAYS AS (...) STORED`),让数据库自己算。
2. **应用层**——在 Python 工具(`tools/csv_to_sql.py`)里算好再写进 SQL。
3. **混合**——大部分走应用层,少数走数据库。

这个决策影响所有派生字段的实现方式、可维护性、跨表能力,是个一次定、长期生效的架构选择。详细分析见 `docs/DESIGN.md §2`。

## 决策 (Decision)

**派生字段默认走应用层(Python),在 `tools/csv_to_sql.py::DERIVED_RULES` 里集中定义,不使用 MySQL `GENERATED COLUMN`。**

**唯一例外**:`delivery_order_items.short_qty` 走 DB 生成列(理由见下方"例外的理由")。

- 派生字段集中表:`DERIVED_RULES`(csv_to_sql.py:47),按表名分组的字典。
- 计算入口:`apply_derived_rules`(csv_to_sql.py:547 起)实现"加算 + 反向校验"双行为。
- 反向校验容差:支持 `tolerance_mode: absolute|percent`(csv_to_sql.py:621)。
- 三处同步义务见 `BUSINESS_RULES.md R7`。

## 理由 (Rationale)

### 为什么选应用层,不选 DB 生成列

**1. 跨表派生,DB 生成列做不了。**
`purchase_order_items.volume_subtotal` 依赖 `products.volume`(单件体积),这是**跨表**关系。MySQL `GENERATED COLUMN` 只能引用**本行**其他列,跨表 JOIN 它管不了。所以这种字段只能在 Python 端算完再落库。证据:`local_validator.py::check_volume_subtotals`(步骤 8/15)专门做跨表体积校验,正是因为 DB 约束保证不了。

**2. 反向校验需要容差逻辑,DB 表达不了。**
客户经常"上下浮动"填一个值(比如理论米重 100g,客户填 102g),系统不能强行覆盖,而是要**比对公式值,超容差才报错**。`apply_derived_rules` 做的是"软约束 + 容差":CSV 没填就自动算,填了就跟公式比,超容差报 ERROR。DB 生成列是**硬覆盖**——客户填的值会被直接丢掉,这违背业务需求(R4:按客户给定值保存)。

**3. 密度按品类查表,放 DB 难维护。**
重量计算依赖 `DENSITY_RULES`(csv_to_sql.py:397),不同 `product_category` 用不同公式(线管固定 1.35;钢丝管 `内径×0.003+1.46`)。这种"按业务字典查公式"的逻辑放在 Python 字典里加一行就能扩品类(R6:数据即数据),放 DB 要写一堆 `CASE WHEN`,改起来痛苦。

**4. 厚度反推有三条路径,DB 写不了分支。**
`calc_theoretical_thickness`(csv_to_sql.py:451)按优先级 A > B > C 走(A 几何反推;B 密度方程;C 密度方程另一组)。`depends_on_any`(csv_to_sql.py:574)支持"任一组依赖齐即可"的 OR 关系。这种多路径分支逻辑写进 DB 生成列几乎不可能。

### 例外:`short_qty` 为何走 DB 生成列

`delivery_order_items.short_qty` 是**唯一**走 MySQL `GENERATED ALWAYS AS (quantity - actual_quantity) STORED` 的字段(sql/01_schema.sql:498)。理由:

- **纯行内计算**——只依赖同一行的 `quantity` 和 `actual_quantity`,**不跨表、不容差、不分路径**。DB 生成列恰好擅长这种场景。
- **强一致性**——`actual_quantity` 一改,`short_qty` 自动重算,不存在"应用层忘算"的风险。

### 备选方案对比(真实讨论,不是走过场)

| 方案 | 优点 | 致命缺点 | 结论 |
| --- | --- | --- | --- |
| **A. 全走 DB 生成列** | 强一致、零应用层代码 | 跨表派生死路一条;容差逻辑表达不了;密度查表难维护 | **否决** |
| **B. 全走应用层** | 灵活、可测试、跨表 OK | `short_qty` 这种纯行内场景也走 Python,白白放弃 DB 的强一致 | 略浪费,但可接受 |
| **C. 混合(默认应用层 + 纯行内走 DB)** | 兼顾灵活和强一致 | 需要在文档里明确"哪个走 DB"的判定标准 | **采用** |

选 C。判定标准:**"纯行内 + 不容差 + 不分路径"三者全满足才走 DB,否则走应用层**。目前只有 `short_qty` 同时满足三条,所以它是唯一例外。

## 后果 (Consequences)

### 正面后果

- **灵活**:跨表派生、容差、多路径反推都能表达,DB 生成列做不到的事这里都能做。
- **可测试**:Python lambda 可以单独写单元测试,DB 生成列只能靠集成测试间接验证。
- **跨品类可扩**:加新品类只需在 `DENSITY_RULES` 加一行(R6),不动 DB schema。

### 负面后果 / 取舍

- **三处同步负担**(`BUSINESS_RULES.md R7`):加新派生字段必须同步改三处——`sql/01_schema.sql`(MySQL 真表)、`tools/local_validator.py::SQLITE_SCHEMA`(SQLite 镜像)、`tools/csv_to_sql.py::DERIVED_RULES`(派生规则)。漏一处就会出现"校验通过但数据算错"。
  - **缓解**:用 `schema-sync-checker` agent 做静态对照 + 13 步自检兜底(`scripts/run_local_validation.sh`)。
- **SQLite 镜像不能完全复刻 DB 生成列**:SQLite 不支持 `STORED` 生成列,`short_qty` 在 SQLite 里是普通 `INTEGER NOT NULL DEFAULT 0`(local_validator.py:277),靠应用层 lambda 兜底(csv_to_sql.py:231-244)算出来再写进 SQLite。这是一处"两套库行为不完全一致"的代价。

## 相关 (Related)

- **关联文档**:
  - `docs/DESIGN.md §2`(派生字段策略设计,含完整理由和代码证据)
  - `docs/DESIGN.md §8`(三处同步设计)
  - `docs/BUSINESS_RULES.md R5`(行内派生字段规则)、`R7`(三处同步)、`R4`(产品参数计算,容差 5%)
  - `docs/DATA_MODEL.md §5.1`(派生字段完整清单:8 表 19 字段)
- **关联代码**:
  - `tools/csv_to_sql.py:47`(`DERIVED_RULES` 定义)
  - `tools/csv_to_sql.py:231-244`(`short_qty` 应用层兜底版)
  - `tools/csv_to_sql.py:397`(`DENSITY_RULES`)
  - `tools/csv_to_sql.py:451`(`calc_theoretical_thickness`)
  - `tools/csv_to_sql.py:574`(`depends_on_any`)、`tools/csv_to_sql.py:621`(`tolerance_mode`)
  - `sql/01_schema.sql:498`(`short_qty` DB 生成列,唯一例外)
  - `tools/local_validator.py:277`(`short_qty` 在 SQLite 镜像里是普通 INT)
  - `tools/local_validator.py::check_volume_subtotals`(步骤 8/15,跨表体积校验)

DONE
