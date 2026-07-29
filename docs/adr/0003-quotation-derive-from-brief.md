# 0003. 报价 brief 与 formal 共用 quotations 表 + parent_quote_id 软关联派生 + subtotal 直接公式

## 状态 (Status)

**已接受** — 2026-07-29

## 上下文 (Context)

系统要支持外贸报价环节——客户问价时先给一份**简要报价(brief)**快速试探,谈拢后再派生出**正式 QT(formal)** 用于发 PI(形式发票),最后转成销售合同。

**要决定的问题**(三个,都跟"派生关系怎么建模"有关):

1. **简要报价和正式 QT 用一张表还是两张表?**
   - 候选 A:分别建 `brief_quotations` / `formal_quotations` 两张表(字段几乎一样)。
   - 候选 B:共用 `quotations` 表,用 `quote_type` ENUM('brief','formal') 区分。

2. **subtotal(金额小计)的派生公式走哪条依赖链?**
   - 候选 A:`subtotal = unit_price × quantity`(依赖派生出来的 `unit_price`)。
   - 候选 B:`subtotal = weight_per_unit × price_coefficient × quantity`(直接展开原始字段)。

3. **正式 QT 从哪个简要报价派生,怎么记录这层关系?**
   - 候选 A:建独立 `quotation_relations` 关系表(quote_id, parent_quote_id)。
   - 候选 B:在 `quotations` 表加自引用 `parent_quote_id` 软关联字段。

这个决策影响:表数量、派生引擎的实现复杂度、报价版本追溯能力。详细分析见 `docs/DESIGN.md §9`、`docs/DATA_MODEL.md §4.9`、`docs/BUSINESS_RULES.md R10`。

触发本次决策的直接原因:2026-07-29 客户(R10)要求报价按"KG × 系数"定价(不同管径组用不同系数),且外贸谈判常"先简要后正式",需要系统支持从简要报价一键派生正式 QT。

## 决策 (Decision)

**三个问题都选 B:共用 `quotations` 表 + `parent_quote_id` 自引用软关联 + subtotal 直接公式。**

- 简要报价和正式 QT 都进 `quotations` 表,靠 `quote_type` ENUM('brief','formal') 区分(sql/01_schema.sql:750)。
- 正式 QT 填 `parent_quote_id` 指向派生源简要报价,自引用外键 `fk_quo_parent` ON DELETE **SET NULL**(sql/01_schema.sql:769)——跟 ADR-0002 的 `transfer_ref` 同款软关联思路。
- 明细 `quotation_items.subtotal` 用**直接公式** `weight_per_unit × price_coefficient × quantity`,不依赖派生出来的 `unit_price`(csv_to_sql.py:373-384)。
- 派生校验:`tools/local_validator.py::check_quotations`(步骤 14/14,local_validator.py:1174-1220)。

## 理由 (Rationale)

### 问题1:为什么 brief 和 formal 共用一张表

**1. 简要报价和正式 QT 的字段几乎完全一样,只是粗细不同。**
两者都有报价单号、客户、币种、汇率、金额四件套(`total_amount`/`currency`/`exchange_rate`/`total_amount_cny`)、状态、明细行(产品 + 数量 + 单价 + 小计)。建两张表等于把同一份字段定义抄两遍,后续加字段要双改。

**2. 共用表 + ENUM 是项目既有模式。**
`stock_in.in_type` ENUM(purchase/production/transfer/return)、`stock_out.out_type` ENUM(sale/production/transfer/scrap)都是"同业务不同子型共用一张表"的先例(见 ADR-0002)。报价沿用同一模式,模型风格统一。

**3. 表数量零增量。**
建两张表 = +2 张主表 + 配套明细表 = +4 张表;共用表 = `quotations` + `quotation_items` + `quotation_params` 共 3 张表,且 `quotation_params` 是全局参数(报价系数基准、生效日期等),不分 brief/formal。

### 问题2:为什么 subtotal 用直接公式,不走依赖链

**这是被实现机制逼出来的决策,不是审美选择。**

`apply_derived_rules`(csv_to_sql.py 的派生引擎)是**单轮遍历**——每个字段按 `DERIVED_RULES` 字典顺序算一次,算完就写回,不做多轮迭代。

如果 `subtotal` 的 `depends_on` 写成 `["unit_price", "quantity"]`(候选 A),会发生什么?

- 派生引擎遍历到 `subtotal` 时,会检查 `unit_price` 是不是已经被算出来并填进 row。
- 但 `unit_price` 也是个派生字段(在 `subtotal` 之前定义,字典顺序 `unit_price` < `subtotal`),**字典顺序上 `unit_price` 确实先算**……但万一未来字段重排、或同一表加新派生字段打破顺序,`subtotal` 就会读到还没加算的 `unit_price`(可能是 0 或 None),算出错误的 `subtotal`。
- 引擎**不做第二轮**——它不会发现 `unit_price` 后来变了再回头重算 `subtotal`。

代码注释原文(csv_to_sql.py:343-346):
```
# 注意: subtotal 不依赖派生的 unit_price, 而是直接展开成原始字段
#       乘积 (weight_per_unit × price_coefficient × quantity)。
#       原因: apply_derived_rules 是单轮遍历, 不做多轮依赖链计算,
#       若 subtotal 依赖 unit_price 会在 unit_price 尚未加算前就跳过。
```

**直接公式的好处**:`subtotal` 的 `depends_on` 写成 `["weight_per_unit", "price_coefficient", "quantity"]`——这三个都是**原始字段(CSV 录入的)**,不是派生字段,单轮遍历第一遍就能拿到,结果稳定可预测,不依赖字段顺序。

代价:`subtotal` 和 `unit_price` 公式有部分重叠(`weight_per_unit × price_coefficient`),改一处要记得改两处。靠 `check_quotations` 校验4(local_validator.py:1214-1220)做兜底——它会重算 subtotal,跟明细里的值对不上就 ERROR。

### 问题3:为什么用 parent_quote_id 自引用软关联,不建关系表

**这跟 ADR-0002 的 `transfer_ref` 是同款决策。**

- 正式 QT 派生自哪个简要报价,是**一对一**关系(一条正式 QT 只能从一个简要报价派生),不是多对多。
- 一对一关系用自引用外键 `parent_quote_id` 就够了(sql/01_schema.sql:751),不需要建 `quotation_relations(quote_id, parent_quote_id)` 这种中间表——中间表是为多对多关系设计的。
- `ON DELETE SET NULL` 而不是 `CASCADE`:简要报价被删,派生出来的正式 QT **不跟着删**(它可能已经发给客户了),只是断了派生源指向。

校验靠 `check_quotations` 校验2(local_validator.py:1192 附近):`formal` 类型的报价 `parent_quote_id` 必须指向一条存在的 `brief` 报价,否则 ERROR。

### 备选方案对比(真实讨论)

| 维度 | 候选 A:两张表 / 依赖链 / 关系表 | 候选 B:共用 + 直接公式 / 自引用(采用) |
| --- | --- | --- |
| 表数量 | +4(brief 主表+明细 + formal 主表+明细)+ 1 关系表 | +3(quotations + quotation_items + quotation_params) |
| 派生引擎 | 需多轮迭代,否则 subtotal 依赖 unit_price 可能算错 | 单轮遍历稳定,subtotal 直接公式 |
| 版本追溯 | 关系表可记多对多(同一 brief 派生多个 formal) | 自引用只记一对一(够用,业务上正式 QT 一对一派生) |
| 字段同步 | 两张表加字段要双改 | 共用表加字段一次到位 |
| 跟既有模式 | 跟 `stock_in`/`stock_out` 的 ENUM 子型模式不一致 | 完全沿用 ENUM 子型 + 自引用软关联(ADR-0002)模式 |
| 简要报价被删 | 关系表行被删,formal 还在但失去派生记录 | `ON DELETE SET NULL`,formal 还在,`parent_quote_id` 变 NULL |

**结论**:候选 A 的"多对多关系表"优势,在本业务里用不上——正式 QT 是一对一派生的。为了用不上的多对多能力多背 4 张表 + 双改字段 + 多轮派生引擎,不划算。选 B。

## 后果 (Consequences)

### 正面后果

- **表数量少**:报价模块共 3 张表,跟"采购""销售"模块同量级。
- **派生稳定**:subtotal 直接公式,不依赖字段顺序,单轮遍历第一遍就对。
- **风格统一**:`quote_type` ENUM 子型 + `parent_quote_id` 自引用软关联,完全沿用 `stock_in`/`stock_out` 的 `in_type` ENUM + `transfer_ref` 模式(ADR-0002),学习成本低。
- **追溯可断**:`ON DELETE SET NULL` 让简要报价可删而不影响已发出的正式 QT。

### 负面后果 / 取舍

| 代价 | 说明 | 缓解措施 |
| --- | --- | --- |
| **subtotal 公式重叠** | `subtotal` 和 `unit_price` 都含 `weight_per_unit × price_coefficient`,改公式要改两处 | `check_quotations` 校验4 重算 subtotal 兜底;两处公式写相邻(csv_to_sql.py:361-384)便于同步 |
| **parent_quote_id 无强约束** | 自引用软关联,formal 可以不填 parent 或填错(指向另一条 formal) | `check_quotations` 校验2:formal 必须指向存在的 brief,否则 ERROR |
| **brief/formal 字段语义混** | 同一张表里两种类型的行,部分字段对 brief 无意义(如 formal 的 `parent_quote_id`) | 字段都允许 NULL,靠 `quote_type` + 校验区分;查询时加 `WHERE quote_type=...` 过滤 |
| **不支持多对多派生** | 一条 formal 只能从一个 brief 派生,不能"合并多个 brief" | 业务上一对一够用;若未来要合并,再加关系表(本阶段不做) |
| **converted_contract_id 同款软关联** | 报价转合同后回填的 `converted_contract_id` 也是软关联,无外键到 `sales_contracts` | `check_quotations` 校验3:回填值必须存在于 `sales_contracts`,否则 ERROR |

**核心权衡**(引自 `docs/DESIGN.md §9.2`):"subtotal 直接公式是单轮派生引擎的硬约束逼出来的——引擎不做多轮,公式就不能依赖另一个派生字段。"

## 相关 (Related)

- **关联文档**:
  - `docs/DESIGN.md §9`(报价派生关系设计,含 4 个决策点 + 代码证据)
  - `docs/DATA_MODEL.md §4.9`(报价模块 3 张表详述)
  - `docs/DATA_MODEL.md §5.1`(派生字段表,含报价 5 条派生规则)
  - `docs/BUSINESS_RULES.md R10`(报价定价铁律,2026-07-29 新增)
  - `docs/SPECS.md §9`(报价模块功能点 F9.1~F9.4)
  - `docs/SCENARIOS.md 场景F`(简要报价→正式 QT→PI 转换端到端)
- **关联 ADR**:
  - `docs/adr/0002-transfer-soft-link-no-dedicated-table.md`(同款"ENUM 子型 + 软关联"模式,本 ADR 沿用)
- **关联代码**:
  - `sql/01_schema.sql:750`(`quotations.quote_type` ENUM('brief','formal'))
  - `sql/01_schema.sql:751`(`quotations.parent_quote_id` 自引用字段)
  - `sql/01_schema.sql:762`(`quotations.converted_contract_id` 转合同回填)
  - `sql/01_schema.sql:769`(`fk_quo_parent` 外键 ON DELETE SET NULL)
  - `sql/01_schema.sql:786`(`quotation_items.group_code` 分组码)
  - `sql/01_schema.sql:787`(`quotation_items.price_coefficient` 报价系数)
  - `sql/01_schema.sql:792`(`quotation_items.unit_price` 派生字段)
  - `tools/csv_to_sql.py:343-346`(subtotal 单轮遍历注释,直接公式理由)
  - `tools/csv_to_sql.py:373-384`(subtotal DERIVED_RULES,直接公式实现)
  - `tools/local_validator.py:1174-1220`(`check_quotations`,4 项子校验)

DONE
