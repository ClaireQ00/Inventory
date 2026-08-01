# 0005. 报价快照重量分阶段管控 + R11 反算快照优先取数 + delivered_qty 校验回写

## 状态 (Status)

**已接受** — 2026-08-01

## 上下文 (Context)

`quotation_items.weight_per_unit` 的设计语义是「单卷重量，从 `products.weight` 带出、**可覆盖**」的快照（sql/01_schema.sql:847）。客户谈价时把重量谈成新值，只改这一行报价明细上的快照，`products.weight` 一动不动——别的报价、别的合同不受影响。这个「快照隔离」设计本身是对的，但 2026-08-01 链路复查暴露出三个连带问题：

1. **快照长期偏离主数据，正式单据失去依据。** 真实数据里发现一份 brief 报价有两行明细的快照重量与主数据偏差达 233%（短版规格错填长版重量）。brief 阶段谈价改重量是常态、可以容忍；但 formal QT 和销售合同是客户**返单的长期依据**——如果带着偏离主数据的快照转合同，下次返单、再报价又从旧主数据带错值，错误会沿链路放大。
2. **R11 反算拿旧主数据对合同单价，每次做发货单都误报 WARN。** `check_packing_coefficient` 原来只从 `products.weight` 取单重。报价谈成新重量（只写在快照上）而主数据没更新时，反算公式 `expected_unit_price = 报价系数 × 单重` 永远对不上合同单价 → 每张发货单都 WARN，真问题反而被噪音淹没。
3. **`delivered_qty` 字段从不回写，不可信。** 该字段建表时注释就写「由发货单回写」（sql/01_schema.sql:306），但第 5 步校验只读不写，实测全为 0。`clone_material.py --update-contract` 判定「合同行是否已发货」时若信这个字段，会把已发货行当未发货处理。

触发本次决策的直接原因：用户提出「报价改重量可能是临时的，但合同确定后返单大概率延续这个重量和型号」，要求把「快照何时可以偏离、何时必须归位、反算跟谁对」定成规则。

## 决策 (Decision)

**四件事一起定，构成「快照重量全生命周期」规则：**

1. **快照重量分阶段管控（`check_quotations` 子校验 5，容差 5%）**
   - `brief` / `draft` 阶段：快照可偏离主数据，只 WARN 提醒（临时谈判自由）；
   - `formal` / `converted` 阶段：快照**应当归位**到物料编码——WARN 升级为 `[正式报价须归位]` 强提醒，文案直接给出归位路径（改回主数据值，或用克隆工具新建物料并换码）和工具命令行（local_validator.py:1345-1379）。不阻断流程，但 formal/合同是返单长期依据，带偏离快照转正式单据的行为在校验报告里无处遁形。
2. **R11 反算取数改快照优先**（local_validator.py:1382-1560）
   - 单重/系数取数优先级：**该合同 converted 来源报价的快照 > 同客户最新有效报价快照（非 draft 优先）> 主数据**（local_validator.py:1443-1449）；
   - fallback 子查询必须带 `q.customer_code = sc.customer_code` 同客户过滤（local_validator.py:1419-1429），防止张冠李戴；
   - **两遍查询**：已发货行（delivery_order_items）照常反算并回写 `expected_unit_price/coeff_diff/coeff_check_status`（local_validator.py:1506）；**未发货合同行**也从隐形改为反算，WARN 带 `[合同未发货]` 前缀、不回写（local_validator.py:1536-1544）。
3. **`delivered_qty` 由第 5 步校验现算回写，恢复字段可信**（local_validator.py:753-800）
   - 校验时从 `delivery_order_items` 现算实发数（`actual_quantity>0` 优先，否则 `quantity`），回写 `sales_contract_items.delivered_qty`，字段注释语义从此成立。
4. **半自动「克隆建物料」工具 `tools/clone_material.py`**
   - `clone_material()`（clone_material.py:64）：以源物料为模板克隆新物料，被覆盖的几何输入会把对应派生列置空、导入时由 `DERIVED_RULES` 重算；
   - `--update-quote`：把指定报价明细的 `material_id` 换成新码；
   - `--update-contract`（clone_material.py:212）：合同换码，**已发货历史行自动跳过留痕**（发出去的货确实是旧规格，历史真相不改），只换未发部分；是否已发货从发货明细现算，不信 `delivered_qty` 旧值。

## 理由 (Rationale)

### 为什么是「分阶段」而不是一刀切禁止快照偏离

**brief 阶段改重量是正常业务动作，禁掉等于禁掉谈判。** 客户谈价时试重量、试规格是常态，brief 就是用来试探的。一刀切 ERROR 会逼业务员绕开系统私下谈，数据更脏。所以 brief/draft 只 WARN，保留自由度。

**但 formal/converted 是返单的长期依据，必须收敛。** 用户原话：「合同确定了之后，以后很有可能会延续这个重量和型号。」如果允许偏离快照进合同，则：

- 返单再报价时从 `products.weight` 带出的还是旧值 → 每次都要人工想起「这个客户谈的是特殊重量」→ 必错；
- R11 反算永远对不上 → 每张发货单 WARN → 校验噪音化。

所以 formal/converted 要求「归位」：把谈判结果固化成正式物料（克隆新建），快照与主数据重新一致。这跟 ADR-0003 的「软关联 + 校验兜底」思路一致——数据上允许自由，校验上分阶段收口。

### 为什么 R11 要快照优先，而不是坚持只认主数据

R11 的业务问题是「**这单货的合同单价，按谈定的重量和系数折算，对不对得上**」。「谈定的重量」在快照上，不在主数据上。坚持只认主数据等于回答错了问题。

取数优先级的设计：

- **converted 来源报价快照优先**：合同从报价转来，谈判结果就在那张报价的明细行上，是最准确的锚点；
- **同客户最新报价快照兜底**：合同不是从报价转的情况（老客户直接续签），用同客户最近报价近似；**必须同客户**——不同客户的谈判价互不相关，不过滤会拿 A 客户的特殊重量去对 B 客户的合同；
- **非 draft 优先**（`ORDER BY (q.status='draft'), q.id DESC`）：draft 是未发出的草稿，不该成为定价依据；
- **主数据最后兜底**：完全没有报价痕迹时退回 `products.weight`。

### 备选方案对比（真实讨论）

| 方案 | 为什么否决 / 采纳 |
| --- | --- |
| 报价改重量时**直接回写 `products.weight`** | 否决。历史报价、在途合同的快照语义被破坏，且一个物料被多个客户共用时会互相踩踏。快照隔离的初心就是不动主数据。 |
| **合同明细表加快照重量字段** | 本阶段否决。schema 变更 + 派生链 + 模板 + 校验全要改，代价大；当前合同行的 `unit_price` 本身就是定价锚点，R11 反算的目标是验证它，不需要再存一份重量。未来若前端需要直接展示「合同重量」，再评估。 |
| R11 **忽略未发货合同行**（只算已发货） | 否决。未发货行原本完全隐形，定价错了要等发货才暴露。两遍查询让未发货行提前 WARN，代价只是多一次查询。 |
| `delivered_qty` **不回写，工具每次现算** | 否决。现算逻辑散在每个使用点会漂移（工具、校验、未来前端各算各的）；第 5 步集中回写一处口径，字段恢复可信，工具和未来前端都能直接信它。 |
| 克隆做成**全自动**（检测到偏差自动建物料） | 否决。新物料号、命名、参数需要人确认，全自动会造出垃圾物料。半自动工具（人工触发、参数显式、结果可导入校验）既省力又可控；核心函数 `clone_material()` 是纯函数，未来前端按钮直接复用。 |

### 与历史数据的关系

「合同换码后已发货行保留旧码」是**刻意保留的历史真相**——发出去的货确实是旧规格，报关单、 packing plan 都是旧码。第 5 步发货校验按 `(contract_no, item_no)` 关联，不受 material_id 换码影响；后续未发部分用新码出库。历史数据一律不动（用户明确要求「历史数据不要动了，要不就查无依据了」）。

## 后果 (Consequences)

### 正面后果

- **返单链路闭环**：合同确定新重量 → 克隆建物料 → 换码 → 主数据与快照重新一致 → 下次返单从主数据带出的就是谈定值。
- **R11 零误报**：反算跟快照对，报价谈新重量不再每次 WARN；WARN 重新变得有意义。
- **未发货行提前暴露**：定价错误在做发货单之前就能发现。
- **`delivered_qty` 可信**：第 5 步回写后，工具、报表、未来前端可直接使用。
- **工具可复用**：`clone_material()` 是纯函数，未来前端「克隆建物料」按钮直接调它。

### 负面后果 / 取舍

| 代价 | 说明 | 缓解措施 |
| --- | --- | --- |
| **换码后新旧码并存** | 合同行是新码、已发货行是旧码，查询时要理解这段历史 | 已发货行跳过留痕（工具输出明确列出）；GLOSSARY 收录「归位」「克隆建物料」术语 |
| **fallback 仍是近似** | 合同无 converted 来源时，「同客户最新报价」未必就是谈定的那张 | 只是 WARN 级提醒，不阻断；WARN 文案带工具用法，引导人工归位 |
| **克隆是人工触发** | 依赖业务员看到 WARN 后动手，不自动 | WARN 文案直接给出工具命令行；前端阶段做成按钮 |
| **换码后旧物料失去系数来源** | 报价系数只存在于报价明细上；报价换码后，旧物料的历史合同/发货行 R11 无从反算，转「缺反算数据→pending」WARN（2026-08-01 场景 G 实测确认） | 合同侧也 `--update-contract` 换码并同步单价；旧物料彻底不用就停用（`is_active=0`）；工具输出自带提醒 |
| **库存/贷记单不自动换码** | `--update-contract` 只换合同明细，库存、 credit_note 需人工处理 | 工具输出人工提醒清单 |
| **分阶段规则靠校验执行** | 数据层面 brief/formal 都能写偏离快照，靠子校验 5 收口 | 跟 ADR-0003 同款「软关联 + 校验兜底」模式，16 步校验每次必跑 |

## 相关 (Related)

- **关联文档**：
  - `docs/BUSINESS_RULES.md R10`（报价定价铁律）、`R11`（packing 公斤价反算）
  - `docs/DATA_MODEL.md §4.9`（报价模块）、`§4.3`（合同模块 delivered_qty）
  - `docs/TASKS.md §2 第五组`（本次加固的任务清单与完成记录）
  - `docs/GLOSSARY.md`（「快照重量」「归位」「克隆建物料」术语）
- **关联 ADR**：
  - `docs/adr/0003-quotation-derive-from-brief.md`（报价派生建模；本 ADR 的子校验 5 是同一校验函数的延伸，「软关联 + 校验兜底」模式沿用）
- **关联代码**：
  - `sql/01_schema.sql:847`（`quotation_items.weight_per_unit` 快照字段定义）
  - `sql/01_schema.sql:306`（`sales_contract_items.delivered_qty` 回写字段定义）
  - `tools/local_validator.py:1284`（`check_quotations`，含子校验 1-5）
  - `tools/local_validator.py:1345-1377`（子校验 5：快照重量分阶段管控）
  - `tools/local_validator.py:1382`（`check_packing_coefficient`，R11 反算）
  - `tools/local_validator.py:1419-1429`（fallback 同客户过滤 + 非 draft 优先）
  - `tools/local_validator.py:1443-1449`（取数优先级：converted 快照 > 最新报价 > 主数据）
  - `tools/local_validator.py:1506`（已发货行回写 `expected_unit_price/coeff_diff/coeff_check_status`）
  - `tools/local_validator.py:1536-1544`（`[合同未发货]` WARN，两遍查询第二遍）
  - `tools/local_validator.py:794-797`（第 5 步 `delivered_qty` 现算回写）
  - `tools/clone_material.py:64`（`clone_material()` 克隆建物料核心函数）
  - `tools/clone_material.py:212`（`update_contract_material()` 合同换码，已发货行跳过留痕）
