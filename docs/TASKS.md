# 任务分解清单 (Task Breakdown)

> **本文件取代 `docs/CLAUDE_BRIEF.md`** —— CLAUDE_BRIEF 是 2026-07-26 写的"待办愿望清单"，里面列的三件事（CSV→SQL 自动化脚本、本地导入执行脚本、验证流程设计）**现在都已经做完**了（见 §4 现状盘点）。
>
> 这份 TASKS.md 把后续工作**拆细成可勾选、可执行**的任务，供 `scripts/claude-driver.sh` 每轮挑一件没勾的推进。任务来源：① CLAUDE_BRIEF 残留项、② 对照 `SPECS.md` 15 步校验覆盖度找出的补强项、③ `SPECS.md §10` 阶段二规划。
>
> 验收口径：每个任务完成后必须能跑 `bash scripts/run_local_validation.sh --demo` 仍全绿（见 `BUSINESS_RULES.md R9`）。

---

## 1. 怎么用这份清单

### 1.1 勾选规则

- 状态三态：`待办` / `进行中` / `已完成`
- **已完成必须基于真实代码**判断，不能凭印象。判断依据见每行的"关联文档/代码位置"列
- 一个任务做完，立刻把状态列改成 `已完成`，并提交一次（`scripts/claude-driver.sh` 会自动 git commit）
- 任务遇到阻塞，把状态改 `进行中` 不动，并在任务行下方加一行 `> 阻塞原因：xxx`，输出 `BLOCKED`

### 1.2 优先级含义

| 优先级 | 含义 | 类比 |
| --- | --- | --- |
| **P0** | 不做就跑不通主线流程 | 没装发动机的车，再漂亮也开不动 |
| **P1** | 增强项，做了更好用、更稳 | 倒车影像、定速巡航 |
| **P2** | 阶段二规划，本阶段不做 | 自动驾驶（先能开走再说） |

> **claude-driver 挑活顺序**：先扫 P0 里所有 `待办` → 再 P1 → 不碰 P2。同优先级按 ID 升序。

### 1.3 依赖关系

- "依赖"列写前置任务 ID，多个用 `+` 连接（如 `T1.2+T1.3`）
- 没有前置依赖的可以独立做
- 前置任务没完成的，本任务保持 `待办`，不要硬上

---

## 2. 任务总表

### 第一组：CSV 导入与验证流程（CLAUDE_BRIEF 残留 → 大部分已完成）

> 这一组对应 `CLAUDE_BRIEF.md §"需要 Claude Code 做的事情"` 的 3 件事。本组任务绝大多数已完成，下面用 `[x]` 在状态列直接标出来。

| ID | 任务 | 优先级 | 依赖 | 状态 | 关联文档/代码 |
| --- | --- | --- | --- | --- | --- |
| **T1.1** | 编写"CSV → SQL"通用导入脚本（含派生字段加算 + 反向校验） | P0 | — | 已完成 | `tools/csv_to_sql.py`（`DERIVED_RULES` + `apply_derived_rules`）；`docs/VALIDATION_GUIDE.md §4` |
| **T1.2** | 编写"一键本地导入 + 跑 15 步校验"执行脚本 | P0 | T1.1 | 已完成 | `scripts/run_local_validation.sh`；`tools/local_validator.py::run_validation` |
| **T1.3** | 设计真实数据验证流程（目录约定、模板→CSV→报告链路） | P0 | T1.1+T1.2 | 已完成 | `docs/VALIDATION_GUIDE.md`（§1 目录约定 / §2 快速开始 / §8 流程图） |
| **T1.4** | 生成 demo 演示数据脚本（假但完整，开箱即跑） | P0 | T1.2 | 已完成 | `tools/make_demo_data.py`；写入沙箱 `data/csv/demo_runtime/`（见 `make_demo_data.py` 安全守卫） |
| **T1.5** | 在校验脚本里补齐阶段一 8 大模块的业务校验 | P0 | T1.2 | 已完成 | `tools/local_validator.py`（`check_*` 共 15 个函数，见 `SPECS.md §F9.3` 对照表） |
| **T1.6** | 把 `--demo` 模式接到 `run_local_validation.sh`（独立沙箱不覆盖真实数据） | P0 | T1.4 | 已完成 | `scripts/run_local_validation.sh:53-67`（`USE_DEMO` 分支 + `--csv-dir data/csv/demo_runtime`） |

> 第一组全部已完成，无 `待办` 项。残留可勾项移到第二组（补强）。

---

### 第二组：补强项（对照 15 步校验覆盖度 + SPECS 找出的差距）

> 怎么找出来的：拿 `SPECS.md` 的功能点清单（F1.1~F9.3）逐一对照 `tools/local_validator.py` 的 `check_*` 函数，发现"功能点描述了但校验没覆盖 / 校验有但文档没写 / 有 demo 数据但没场景化验证"的，列在这里。

| ID | 任务 | 优先级 | 依赖 | 状态 | 关联文档/代码 |
| --- | --- | --- | --- | --- | --- |
| **T2.X** | **tests/ 独立测试套件**（合并原 T2.1 / T2.2 / T2.4 / T2.5）：用 pytest 或简单断言脚本，为以下 4 个场景各写一个**故意触发错误**的测试用例，**不污染 demo**。原因：让校验代码被真实验证 ≠ 让 demo 报错，demo 必须 0 错误是铁律。覆盖场景：① T2.1 跨字段不一致（米重×长度 vs 单重）触发 WARN；② T2.2 手填派生列超容差触发 ERROR；③ T2.4 短装超 UCP600 容差触发 ERROR + credit_note 闭环；④ T2.5 跨月汇率缺失触发 ERROR | P1 | T1.4 | 待办 | 新建 `tests/` 目录（当前仓库无）；用例数据放 `tests/fixtures/`，跟 `data/csv/demo/` 隔离 |
| **T2.3** | `SPECS.md F5.4 AC2` 描述"超发报 ERROR/WARN（具体阈值以代码为准）"——核实 `check_delivery_vs_contract` 的实际判定：超发一律 ERROR，没有 WARN。修正 SPECS 表述模糊处 | P1 | — | 已完成 | `docs/SPECS.md:525`（AC2 改为"一律 ERROR，无 WARN 分级，无容差阈值"）；代码依据 `tools/local_validator.py::check_delivery_vs_contract`（delivered > contracted → report.error） |
| ~~**T2.6**~~ | ~~`audit_logs` 最小写入点~~ | ~~P1~~ | — | **砍掉** | 提前做生产功能无意义：项目当前形态是 SDD 文档+校验工具，不是生产系统；audit 完整方案在 T3.6（阶段二），需要时再做 |
| **T2.7** | `scripts/check-sensitive-data.sh` 只检查文件名/扩展名，不检查 CSV 内容里是否混入真实手机号/身份证。补一个内容侧正则扫描（11 位手机号、18 位身份证） | P1 | — | 待办 | `scripts/check-sensitive-data.sh`；`docs/PRIVATE_DATA_GUIDELINES.md` |
| **T2.8** | `docs/IMPORT_TEMPLATES.md` 列了模板，但 `sample/templates/` 里**缺** `stock_logs_template.csv`（流水表由系统自动重建，不手填）。要么在 IMPORT_TEMPLATES 里明确说明"此表系统生成，无模板"，要么补一个空模板避免用户找 | P2 | — | 已完成 | `docs/IMPORT_TEMPLATES.md:44`（已写明"`stock_logs` 表无 CSV 模板...不需要也不应该手填"，指向 `tools/local_validator.py::rebuild_stock_logs`） |
| **T2.9** | `local_validator.py` 第 7 步对账报错信息只给了"物料 ID + 仓库 ID"，没给仓库名。把仓库名一起带出来，方便定位 | P1 | — | 已完成 | `tools/local_validator.py::check_reconciliation`（多查一次 warehouses 取 name+code，报错格式 "物料 X 仓库 仓名(代码)"） |
| ~~**T2.10**~~ | ~~反向校验失败写日志~~ | ~~P2~~ | T1.1 | **砍掉** | 锦上添花：当前 `sys.exit(1)` 兜底已足够阻断流程；日志可观测性等真正上生产再加 |

---

### 第三组：阶段二规划（SPECS §10，本阶段不做）

> 直接搬运自 `SPECS.md §10` 和 `payment-receivable/SKILL.md §7`。**列在这里是为了让 claude-driver 知道"这些不是当前要做的"**，遇到不要主动开工。

| ID | 任务 | 优先级 | 依赖 | 状态 | 关联文档/代码 |
| --- | --- | --- | --- | --- | --- |
| **T3.1** | 供应商付款（AP）—— 新建 `supplier_payments` 表 | P2 | — | 待办（阶段二） | `SPECS.md §10`；`payment-receivable/SKILL.md §7` |
| **T3.2** | 多合同合并收款分配 —— `receipts` 加 `receipt_allocations` 子表 | P2 | — | 待办（阶段二） | `SPECS.md §10`；`BUSINESS_FLOW.md §4.3` |
| **T3.3** | 汇兑损益月末结转 —— `forex_settlements` 表 + 月末脚本 | P2 | — | 待办（阶段二） | `SPECS.md §10`；`BUSINESS_FLOW.md §4.2` |
| **T3.4** | 应收账龄（AR Aging）—— 视图 `v_ar_aging` | P2 | — | 待办（阶段二） | `SPECS.md §10` |
| **T3.5** | 信用证单证管理 —— `lc_documents` 表 | P2 | — | 待办（阶段二） | `SPECS.md §10` |
| **T3.6** | 审计日志逻辑触发 —— `audit_logs` 表已建，触发器未做（**注意**：T2.6 是阶段一的"最小写入点"，T3.6 才是完整触发器方案，两者不冲突） | P2 | T2.6 | 待办（阶段二） | `SPECS.md §10` |

---

### 第四组：报价模块 (feature/quotation)

> 报价模块的规划+实现任务（已全部完成，对应 commit 949dac6→33f1c38 + 本次文档同步）。定价逻辑见 `BUSINESS_RULES.md R10`：单价 = 单卷重量(KG) × 报价系数(USD/KG)，不同管径组用不同系数。流程：简要报价(brief) → 正式 QT form(formal) → 销售合同 PI。本组对应 `feature/quotation` 分支。

- [x] Q1.1 [P0] schema 新增 quotation_params/quotations/quotation_items 三表 + 三处同步
- [x] Q1.2 [P0] csv_to_sql.py 加 quotation_items 派生规则(total_weight/unit_price/subtotal/total_volume)
- [x] Q1.3 [P0] local_validator.py 加第14步 check_quotations + 步数 13→14 同步
- [x] Q1.4 [P0] 报价模板(3个CSV) + make_demo_data(Q025真实1.112组数据) + IMPORT_TEMPLATES 更新
- [x] Q1.5 [P1] DATA_MODEL/SPECS/DESIGN/SCENARIOS 文档补报价模块
- [x] Q1.6 [P1] ADR-0003 报价派生关系决策

---

## 3. 任务分组索引（按主题快速跳转）

| 主题 | 任务 ID | 说明 |
| --- | --- | --- |
| CSV 导入链路 | T1.1 / T1.2 / T1.4 / T1.6 | 模板→CSV→SQL→SQLite 全链路 |
| 校验覆盖度补强 | T2.X（合并原 T2.1/T2.2/T2.4/T2.5） | 走 tests/ 独立测试，不污染 demo |
| 文档一致性 | T2.3 / T2.8 | SPECS/IMPORT_TEMPLATES 措辞修正 |
| 安全 | T2.7 / T2.9 | 敏感数据扫描 / 报错可读性 |
| 阶段二 | T3.1 ~ T3.6 | 本阶段不做，仅登记 |
| ~~已砍~~ | ~~T2.6 / T2.10~~ | ~~audit_logs 提前做无意义 / 日志锦上添花~~ |

---

## 4. 现状盘点（已完成的全部打勾）

> 以下判断全部基于仓库内**真实存在的文件/代码**，不是臆测。

### 4.1 基础设施（脚本与工具链）

- [x] `tools/csv_to_sql.py` —— CSV→SQL 通用脚本，含 `DERIVED_RULES`（products/poi/sci/doi/sri/sr/cn/sc/receipts/quotation_items 共 10 张表的派生规则）+ 反向校验 + 跨字段提醒
- [x] `tools/local_validator.py` —— SQLite 本地验证引擎，15 个 `check_*` 函数全部就位（见 `SPECS.md §F9.3` 对照表）
- [x] `tools/make_demo_data.py` —— 演示数据生成器，写入沙箱 `data/csv/demo_runtime/`，有 `PROTECTED_FILES` 安全守卫
- [x] `scripts/run_local_validation.sh` —— 一键脚本，支持 `--demo`，4 步流程（环境检查 → 敏感数据检查 → 准备 CSV → 跑校验）
- [x] `scripts/check-sensitive-data.sh` —— 敏感数据扫描
- [x] `scripts/ci.sh` + `.github/workflows/ci.yml` —— CI 门禁
- [x] `scripts/claude-driver.sh` —— 无人值守驱动（消费本 TASKS.md）

### 4.2 数据层

- [x] `sql/01_schema.sql` —— MySQL 真表（44KB，22 张表）
- [x] `sql/02_seed_data.sql` —— 种子数据
- [x] `sql/03_master_data.sql` —— 基础资料
- [x] `sample/templates/*_template.csv` —— 20 张表的导入模板（缺 stock_logs，见 T2.8）

### 4.3 文档体系（SDD）

- [x] `docs/GLOSSARY.md` —— 术语表
- [x] `docs/BUSINESS_RULES.md` —— R1~R11 业务规则事实源
- [x] `docs/BUSINESS_FLOW.md` —— 9 节点业务流程
- [x] `docs/DATA_MODEL.md` —— 22 表数据模型
- [x] `docs/SPECS.md` —— 功能需求规格（F1.1~F9.3 + §10 阶段二）
- [x] `docs/DESIGN.md` —— 技术设计
- [x] `docs/VALIDATION_GUIDE.md` —— 15 步校验指南
- [x] `docs/TASKS.md` —— 本文件
- [x] `docs/SCENARIOS.md` —— 端到端验收场景（与本文档同步产出）

### 4.4 15 步校验当前覆盖度

| 步骤 | 校验函数 | demo 是否触发 | 备注 |
| --- | --- | --- | --- |
| 1/15 | `check_master_data` | 触发（通过） | demo 四张基础表都有数据 |
| 2/15 | `check_purchase_orders` | 触发（通过） | PO 金额 20000 = 明细之和 |
| 3/15 | `check_stock_in_vs_purchase` | 触发（通过） | 入库恰好 = 采购，无 WARN |
| 4/15 | `check_sales_contracts` | 触发（通过） | 合同 30000 = 明细之和 |
| 5/15 | `check_delivery_vs_contract` | 触发（**WARN**：未发完） | demo 发货 5/10 < 合同 8/14 |
| 6/15 | `check_stock_out_vs_inventory` | 触发（通过） | 物料2 仓库1 入出恰好平衡 |
| 7/15 | `check_reconciliation` | 触发（通过） | 流水累加 = inventory |
| 8/15 | `check_volume_subtotals` | 触发（通过） | 体积小计容差内 |
| 9/15 | `check_shipping_vs_delivery` | 未真正触发 | demo 报关 actual=planned，偏差 0%（覆盖度不足，见 T2.4） |
| 10/15 | `check_credit_notes_balance` | 未触发 | demo credit_notes 空表（覆盖度不足，见 T2.4） |
| 11/15 | `check_exchange_rates` | 触发（通过） | 2026-07 汇率齐全；跨月未覆盖（见 T2.5） |
| 12/15 | `check_receipts_vs_contract` | 触发（通过） | 收款 4500 ≤ 合同 30000 |
| 13/15 | `check_transfer_pairs` | 触发（通过） | TR20260729001 出3=入3 |
| 14/15 | `check_quotations` | 触发（通过） | 报价主表=Σ明细小计、formal 从 brief 派生、subtotal=重量×系数×数量 |
| 15/15 | `check_packing_coefficient` | 触发（通过） | R11 公斤价反算，容差 0.001（无 demo 触发 WARN 的样例，可补 T2.x） |

> 结论：15 步全部有代码、能跑通，但第 9/10 步在 demo 模式下"没机会真正报警"，是覆盖度短板（T2.4 / T2.5 要补）。

---

## 5. 给 claude-driver 的消费约定

`scripts/claude-driver.sh` 每轮按以下顺序挑活：

1. 读本文件 §2 任务表
2. 在状态=`待办`、优先级最高的任务里，按依赖关系挑一件**前置已完成**的
3. 开工 → 跑 `bash scripts/run_local_validation.sh --demo` → 通过后把状态改成 `已完成`
4. 全部 P0/P1 完成后，输出 `DONE`（停止驱动）；遇到 P2（阶段二）一律不主动做，保持 `待办（阶段二）`
5. 任何一轮如果跑校验失败 3 次连击，driver 自动熔断退出（见 `scripts/claude-driver.sh:27 MAX_FAIL_STREAK`）

---

## 附录 A：与 `CLAUDE_BRIEF.md` 的对照

| CLAUDE_BRIEF 待办 | 对应本文件任务 | 当前状态 |
| --- | --- | --- |
| 生成"CSV → SQL 导入"的自动化脚本或 SQL 模板 | T1.1 | 已完成 |
| 生成"从本地 CSV 导入数据库并验证"的执行脚本 | T1.2 | 已完成 |
| 设计真实数据验证流程，按顺序验证基础资料/采购/入库/合同/发货/出库/库存对账 | T1.3 + T1.5 | 已完成（且超额：原计划 7 步，实际 15 步覆盖到报关+收款+调拨+报价+packing） |

> 三件事全部已完成。`docs/CLAUDE_BRIEF.md` 可在下次提交时删除（被本文件取代）。

---

## 附录 B：相关文档索引

| 文档 | 作用 |
| --- | --- |
| `docs/SPECS.md` | 功能需求规格（任务来源） |
| `docs/SCENARIOS.md` | 端到端验收场景（任务验收依据） |
| `docs/VALIDATION_GUIDE.md` | 15 步校验流程 |
| `docs/BUSINESS_RULES.md` | R1~R11 业务规则 |
| `docs/CLAUDE_BRIEF.md` | 旧待办清单（**本文件取代**） |
| `scripts/claude-driver.sh` | 消费本文件的无值守驱动 |

DONE
