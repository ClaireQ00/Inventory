# 任务分解清单 (Task Breakdown)

> **本文件取代 `docs/CLAUDE_BRIEF.md`** —— CLAUDE_BRIEF 是 2026-07-26 写的"待办愿望清单"，里面列的三件事（CSV→SQL 自动化脚本、本地导入执行脚本、验证流程设计）**现在都已经做完**了（见 §4 现状盘点）。
>
> 这份 TASKS.md 把后续工作**拆细成可勾选、可执行**的任务，供 `scripts/claude-driver.sh` 每轮挑一件没勾的推进。任务来源：① CLAUDE_BRIEF 残留项、② 对照 `SPECS.md` 16 步校验覆盖度找出的补强项、③ `SPECS.md §10` 阶段二规划。
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
| **T1.2** | 编写"一键本地导入 + 跑 16 步校验"执行脚本 | P0 | T1.1 | 已完成 | `scripts/run_local_validation.sh`；`tools/local_validator.py::run_validation` |
| **T1.3** | 设计真实数据验证流程（目录约定、模板→CSV→报告链路） | P0 | T1.1+T1.2 | 已完成 | `docs/VALIDATION_GUIDE.md`（§1 目录约定 / §2 快速开始 / §8 流程图） |
| **T1.4** | 生成 demo 演示数据脚本（假但完整，开箱即跑） | P0 | T1.2 | 已完成 | `tools/make_demo_data.py`；写入沙箱 `data/csv/demo_runtime/`（见 `make_demo_data.py` 安全守卫） |
| **T1.5** | 在校验脚本里补齐阶段一 8 大模块的业务校验 | P0 | T1.2 | 已完成 | `tools/local_validator.py`（`check_*` 共 16 个函数，见 `SPECS.md §F10.3` 对照表） |
| **T1.6** | 把 `--demo` 模式接到 `run_local_validation.sh`（独立沙箱不覆盖真实数据） | P0 | T1.4 | 已完成 | `scripts/run_local_validation.sh:53-67`（`USE_DEMO` 分支 + `--csv-dir data/csv/demo_runtime`） |

> 第一组全部已完成，无 `待办` 项。残留可勾项移到第二组（补强）。

---

### 第二组：补强项（对照 16 步校验覆盖度 + SPECS 找出的差距）

> 怎么找出来的：拿 `SPECS.md` 的功能点清单（F1.1~F9.3）逐一对照 `tools/local_validator.py` 的 `check_*` 函数，发现"功能点描述了但校验没覆盖 / 校验有但文档没写 / 有 demo 数据但没场景化验证"的，列在这里。

| ID | 任务 | 优先级 | 依赖 | 状态 | 关联文档/代码 |
| --- | --- | --- | --- | --- | --- |
| **T2.X** | **tests/ 独立测试套件**（合并原 T2.1 / T2.2 / T2.4 / T2.5）：用 pytest 或简单断言脚本，为以下 4 个场景各写一个**故意触发错误**的测试用例，**不污染 demo**。原因：让校验代码被真实验证 ≠ 让 demo 报错，demo 必须 0 错误是铁律。覆盖场景：① T2.1 跨字段不一致（米重×长度 vs 单重）触发 WARN；② T2.2 手填派生列超容差触发 ERROR；③ T2.4 短装超 UCP600 容差触发 ERROR + credit_note 闭环；④ T2.5 跨月汇率缺失触发 ERROR | P1 | T1.4 | 已完成 | `tests/run_tests.py` + `tests/README.md`；用例数据运行期生成到 `tests/fixtures/`（已 gitignore），跟 `data/csv/demo/` 隔离 |
| **T2.3** | `SPECS.md F5.4 AC2` 描述"超发报 ERROR/WARN（具体阈值以代码为准）"——核实 `check_delivery_vs_contract` 的实际判定：超发一律 ERROR，没有 WARN。修正 SPECS 表述模糊处 | P1 | — | 已完成 | `docs/SPECS.md:525`（AC2 改为"一律 ERROR，无 WARN 分级，无容差阈值"）；代码依据 `tools/local_validator.py::check_delivery_vs_contract`（delivered > contracted → report.error） |
| ~~**T2.6**~~ | ~~`audit_logs` 最小写入点~~ | ~~P1~~ | — | **砍掉** | 提前做生产功能无意义：项目当前形态是 SDD 文档+校验工具，不是生产系统；audit 完整方案在 T3.6（阶段二），需要时再做 |
| **T2.7** | `scripts/check-sensitive-data.sh` 只检查文件名/扩展名，不检查 CSV 内容里是否混入真实手机号/身份证。补一个内容侧正则扫描（11 位手机号、18 位身份证） | P1 | — | 已完成 | `scripts/check-sensitive-data.sh`；`docs/PRIVATE_DATA_GUIDELINES.md` |
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

### 第五组：快照重量与反算链路加固（2026-08-01，全部完成）

> 背景：`quotation_items.weight_per_unit` 是「从 products.weight 带出可覆盖」的快照。报价谈价改重量只改行上快照、主数据不动，由此带出三个问题——formal/合同带偏离快照转正式单据失去返单依据、R11 反算拿旧主数据对合同单价每次误报 WARN、`delivered_qty` 从不回写不可信。决策见 `docs/adr/0005-snapshot-weight-staged-and-r11-snapshot-first.md`。

- [x] S5.1 [P0] `check_quotations` 子校验 5：快照重量 vs 主数据偏差 >5% 提醒（commit `afca847`）
- [x] S5.2 [P0] 子校验 5 升级分阶段：brief/draft 允许临时谈判（普通 WARN）/ formal·converted 升级 `[正式报价须归位]` 强提醒 WARN，文案带归位路径和克隆工具命令行（commit `2bcee82`）
- [x] S5.3 [P0] R11 反算单重/系数改快照优先：converted 报价快照 > 同客户最新报价 > 主数据（commit `75b735f`）
- [x] S5.4 [P0] R11 漏洞修复×4：未发货合同行两遍查询覆盖（`[合同未发货]` WARN）、fallback 同客户过滤、非 draft 优先、清 `'accepted'` 死值（commit `f905e3a`）
- [x] S5.5 [P1] `tools/clone_material.py` 半自动克隆建物料，`--update-quote` / `--update-contract`（合同换码，已发货历史行跳过留痕）（commit `43f5626` / `18e610c`）
- [x] S5.6 [P0] 第 5 步 `check_delivery_vs_contract` 现算回写 `delivered_qty`，字段恢复可信；工具已发货判定改从发货明细现算（commit `44a6e3c` / `cca9b9c`）
- [x] S5.7 [P1] 真实数据清理：brief 报价 2 行错配明细（233% 偏差）删除 + 主表金额/体积修正（data/csv，不进 git）
- [x] S5.8 [P1] `clone_material.py` 健壮性修复×2（2026-08-01 链路复查实测发现）：① products.csv 无 `remark` 列时写溯源备注导致 DictWriter 报多余字段 → 跳过并转 reminders 告知；② 带 `id` 列的 CSV 克隆行照抄源行 id → 导入主键撞号、源物料被 REPLACE 顶掉 → 自动取 max+1 新号（真实数据 products.csv 无 id 列，此前未暴露）
- [ ] S5.9 [P2] 跟进：报价换码后旧物料失去报价系数来源，其历史合同/发货行 R11 转「缺反算→pending」WARN——当前按 ADR-0005 后果表缓解（合同侧换码 / 停用旧物料），未来前端阶段考虑「历史行免反算」开关

---

## 3. 任务分组索引（按主题快速跳转）

| 主题 | 任务 ID | 说明 |
| --- | --- | --- |
| CSV 导入链路 | T1.1 / T1.2 / T1.4 / T1.6 | 模板→CSV→SQL→SQLite 全链路 |
| 校验覆盖度补强 | T2.X（合并原 T2.1/T2.2/T2.4/T2.5） | 走 tests/ 独立测试，不污染 demo |
| 文档一致性 | T2.3 / T2.8 | SPECS/IMPORT_TEMPLATES 措辞修正 |
| 安全 | T2.7 / T2.9 | 敏感数据扫描 / 报错可读性 |
| 阶段二 | T3.1 ~ T3.6 | 本阶段不做，仅登记 |
| 快照重量链路 | S5.1 ~ S5.9 | 分阶段管控 + R11 快照优先 + 克隆建物料（ADR-0005） |
| ~~已砍~~ | ~~T2.6 / T2.10~~ | ~~audit_logs 提前做无意义 / 日志锦上添花~~ |

---

## 4. 现状盘点（已完成的全部打勾）

> 以下判断全部基于仓库内**真实存在的文件/代码**，不是臆测。

### 4.1 基础设施（脚本与工具链）

- [x] `tools/csv_to_sql.py` —— CSV→SQL 通用脚本，含 `DERIVED_RULES`（products/poi/sci/doi/sri/sr/cn/sc/receipts/quotation_items 共 10 张表的派生规则）+ 反向校验 + 跨字段提醒（**2026-07-30 修复** `_looks_like_number`：长度 > 10 的纯数字串不再当数字处理，避免电话号/银行账号被加 `.0`）
- [x] `tools/local_validator.py` —— SQLite 本地验证引擎，16 个 `check_*` 函数全部就位（见 `SPECS.md §F10.3` 对照表）
- [x] `tools/make_demo_data.py` —— 演示数据生成器，写入沙箱 `data/csv/demo_runtime/`，有 `PROTECTED_FILES` 安全守卫
- [x] `scripts/run_local_validation.sh` —— 一键脚本，支持 `--demo`，5 步流程（环境检查 → 敏感数据检查 → **模板↔schema 同步检查(2b, 2026-07-30 新增)** → 准备 CSV → 跑校验）
- [x] `scripts/check-sensitive-data.sh` —— 敏感数据扫描
- [x] `scripts/check-template-schema-sync.sh` —— **2026-07-30 新增**：对比 `01_schema.sql` 字段 vs `sample/templates/*_template.csv` 表头，发现不一致立刻报警（R7 第 4 处同步点的自动化兜底）
- [x] `scripts/load-csv-to-db.sh` —— CSV→MySQL 一键导入脚本（**2026-07-30 修复** `set -euo pipefail` 陷阱：单表失败不再终止整批，改用 `set +e` + `PIPESTATUS` 捕获 mysql 退出码）
- [x] `scripts/ci.sh` + `.github/workflows/ci.yml` —— CI 门禁
- [x] `scripts/claude-driver.sh` —— 无人值守驱动（消费本 TASKS.md）
- [x] `tools/clone_material.py` —— **2026-08-01 新增**：半自动克隆建物料（`clone_material()` 纯函数，未来前端按钮可直接复用）；`--update-quote` 报价换码 / `--update-contract` 合同换码（已发货历史行跳过留痕，是否已发货从发货明细现算）

### 4.2 数据层

- [x] `sql/01_schema.sql` —— MySQL 真表（44KB，25 张表）
- [x] `sql/02_seed_data.sql` —— 种子数据
- [x] `sql/03_master_data.sql` —— 基础资料
- [x] `sample/templates/*_template.csv` —— **23 个**导入模板（`stock_logs` 由校验器自动重建、`audit_logs` 阶段一空壳，两张表**故意无模板**）

### 4.3 文档体系（SDD）

- [x] `docs/GLOSSARY.md` —— 术语表
- [x] `docs/BUSINESS_RULES.md` —— R1~R11 业务规则事实源
- [x] `docs/BUSINESS_FLOW.md` —— 9 节点业务流程
- [x] `docs/DATA_MODEL.md` —— 25 表数据模型
- [x] `docs/SPECS.md` —— 功能需求规格（F1.1~F9.3 + §10 阶段二）
- [x] `docs/DESIGN.md` —— 技术设计
- [x] `docs/VALIDATION_GUIDE.md` —— 16 步校验指南
- [x] `docs/TASKS.md` —— 本文件
- [x] `docs/SCENARIOS.md` —— 端到端验收场景（与本文档同步产出）

### 4.4 16 步校验当前覆盖度

| 步骤 | 校验函数 | demo 是否触发 | 备注 |
| --- | --- | --- | --- |
| 1/16 | `check_master_data` | 触发（通过） | demo 四张基础表都有数据 |
| 2/16 | `check_purchase_orders` | 触发（通过） | PO 金额 20000 = 明细之和;total_volume 0.699 一致 |
| 3/16 | `check_stock_in_vs_purchase` | 触发（通过） | 入库恰好 = 采购,无 WARN |
| 4/16 | `check_sales_contracts` | 触发（通过） | 合同 30000 = 明细之和;total_volume 0.711 一致 |
| 5/16 | `check_delivery_vs_contract` | 触发（**WARN**：未发完） | demo 发货 5/10 < 合同 8/14;**2026-08-01 起校验时现算回写 `delivered_qty`**（actual_quantity>0 优先否则 quantity） |
| 6/16 | `check_stock_out_vs_inventory` | 触发（通过） | 物料2 仓库1 入出恰好平衡 |
| 7/16 | `check_reconciliation` | 触发（通过） | 流水累加 = inventory |
| 8/16 | `check_volume_subtotals` | 触发（通过） | 体积小计容差内 |
| 9/16 | `check_delivery_order_volume` | 触发（通过） | 发货单 total_volume 0.476 = Σ 明细 volume_subtotal |
| 10/16 | `check_shipping_vs_delivery` | 未真正触发 | demo 报关 actual=planned,偏差 0%（覆盖度不足,见 T2.4） |
| 11/16 | `check_credit_notes_balance` | 未触发 | demo credit_notes 空表（覆盖度不足,见 T2.4） |
| 12/16 | `check_exchange_rates` | 触发（通过） | 2026-07 汇率齐全;跨月未覆盖（见 T2.5） |
| 13/16 | `check_receipts_vs_contract` | 触发（通过） | 收款 4500 ≤ 合同 30000 |
| 14/16 | `check_transfer_pairs` | 触发（通过） | TR20260729001 出3=入3 |
| 15/16 | `check_quotations` | 触发（通过） | 报价主表=Σ明细小计、total_volume=Σ明细 total_volume、formal 从 brief 派生、subtotal=重量×系数×数量;**子校验 5（2026-08-01）：快照重量 vs 主数据偏差 >5% 分阶段提醒——brief/draft 普通 WARN、formal/converted `[正式报价须归位]` 强提醒（ADR-0005）** |
| 16/16 | `check_packing_coefficient` | 触发（通过） | R11 公斤价反算,容差 0.001（无 demo 触发 WARN 的样例,可补 T2.x）;**2026-08-01：取数改快照优先（converted 报价 > 同客户最新报价 > 主数据）+ 两遍查询（未发货合同行也反算）+ fallback 同客户过滤** |

> 结论：16 步全部有代码、能跑通,但第 10/11 步在 demo 模式下"没机会真正报警",是覆盖度短板（T2.4 / T2.5 要补）。第 9 步 `check_delivery_order_volume` 是 2026-07-30 新增,跟 `shipping_records.total_cbm`(报关真实 CBM)是两个概念。

### 4.5 真实数据试用记录（2026-07-30）

首次用真实业务数据（PVC 线管 Q025 客户）跑完整流程踩到的坑，全部已修复（详见 git commit `eb250c7` + 本次文档同步）：

| # | 问题 | 修复 | 影响 |
| --- | --- | --- | --- |
| 1 | 电话号 `081297100933` 被当数字处理，存进 SQL 变成 `81297100933.0` | `csv_to_sql.py::_looks_like_number` 加规则：长度 > 10 的纯数字串不当数字 | `customers.phone` / `suppliers.bank_account` / 任何长数字单号 |
| 2 | `load-csv-to-db.sh` 单表失败终止整批（`set -euo pipefail` 陷阱） | `set +e` 包管道 + `PIPESTATUS[1]` 捕获 mysql 退出码，逐表累加 SUCCESS/FAILED | CSV→MySQL 批量导入稳定性 |
| 3 | `customer_id` AUTO_INCREMENT 漂移（多次 REPLACE INTO 把 Q025 的 id 从 2 推到 37），外键失效 | 短期：TRUNCATE 重置；长期：已改为业务编号外键（B1 + ADR-0004） | 所有业务表外键引用 |
| 4 | customers 表加了 `brand_name`/`company_profiles`/`billing_profiles` 字段，但模板表头没同步，CSV 列错位 | 新建 `check-template-schema-sync.sh` 自动比对，集成进 `run_local_validation.sh` 第 2b 步 | R7 同步规则升级为"四处" |
| 5 | 手写 CSV 逗号数对不齐，列错位 | 在 `docs/IMPORT_TEMPLATES.md` 顶部加"填 CSV 4 大坑"，强烈建议用 Python `csv.writer` | 所有 CSV 录入者必读 |
| 6 | R11 反算公式单位不匹配：`应等于的合同单价 = 报价系数×汇率×单重` 把原币价算成人民币价，再和"原币种/件"的合同单价对比（真实 Q025 数据 11 条 WARN 暴露） | 公式去掉汇率，改为 `报价系数×单重`（原币/件）；容差 0.001→0.01（覆盖 2 位小数报价的舍入）；demo 合同件价同步修正、不再迁就旧公式 | `check_packing_coefficient` + `make_demo_data.py` + R11/GLOSSARY/VALIDATION_GUIDE 文档 |

> 这 5 个修复全部是"真实数据试用"暴露出来的，跟 demo 数据无关。后续每加一类新客户/新品类走一遍真实流程，比跑 demo 更能发现问题。

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
| 设计真实数据验证流程，按顺序验证基础资料/采购/入库/合同/发货/出库/库存对账 | T1.3 + T1.5 | 已完成（且超额：原计划 7 步，实际 16 步覆盖到报关+收款+调拨+报价+packing+主表体积） |

> 三件事全部已完成。`docs/CLAUDE_BRIEF.md` 可在下次提交时删除（被本文件取代）。

---

## 附录 B：相关文档索引

| 文档 | 作用 |
| --- | --- |
| `docs/SPECS.md` | 功能需求规格（任务来源） |
| `docs/SCENARIOS.md` | 端到端验收场景（任务验收依据） |
| `docs/VALIDATION_GUIDE.md` | 16 步校验流程 |
| `docs/BUSINESS_RULES.md` | R1~R11 业务规则 |
| `docs/CLAUDE_BRIEF.md` | 旧待办清单（**本文件取代**） |
| `scripts/claude-driver.sh` | 消费本文件的无值守驱动 |

DONE
