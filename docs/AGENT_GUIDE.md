# Agent / Skill / Hook 指南

> **沟通铁律（老板 2026-08-14 定）**：不恭维、不客套，直击要害，简单直接说真相。
> 汇报时先结论后细节；有问题说问题，不粉饰。

> 本文档分两部分：
> - **Part 1 现状**：现在**真实存在**、可以马上用的能力（必读）
> - **Part 2 蓝图**：未来规划，**当前未实现**，看到别去调用
>
> 如果你只想知道"今天能做什么"，看 Part 1 就够了。

---

## Part 1 · 现状（可执行，今天就能用）

### 1.1 真实可用的 4 个 Skill

`.claude/skills/` 下有 4 个 skill，每个都是一份**业务规则手册**。Claude 会根据用户问题自动路由到对应 skill。

| Skill | 处理什么 | 涉及表 / 函数 |
| --- | --- | --- |
| `product-params` | 密度 / 厚度反推 / 米重 / 内径 | `products`；`csv_to_sql.py::DENSITY_RULES` |
| `derived-fields` | 外径 / 体积 / 金额小计（行内派生） | 4 张明细表；`DERIVED_RULES` |
| `trade-documents` | 报关 / 短装 / 唛头 / UCP600 / credit_note | `shipping_records` / `credit_notes`；check 10, 11 |
| `payment-receivable` | 收款 / 汇率 / 水单 / T/T / 应收对账 | `exchange_rates` / `receipts`；check 12, 13 |

**路由表见** `CLAUDE.md` 顶部，4 个 skill **互斥**——一个问题只走一个 skill，不要混。

### 1.2 真实可用的 Agent（4 个内置 + 2 个项目专属）

#### A. Claude Code 自带的 4 个顶层 agent（不需要项目配置）

| Agent | 何时用 |
| --- | --- |
| `general-purpose` | 多文件改动 / 数据库建模 / 文档输出 / 接口设计 |
| `task` | 跑命令 / 跑脚本 / 验证结果（如 `bash scripts/ci.sh`） |
| `explore` | 调研、分析现有项目结构、回答"项目里 X 在哪" |
| `code-review` | 改完代码后做正式 review |

#### B. 项目专属的 2 个 subagent（`.claude/agents/` 下，2026-07-29 加）

`.claude/agents/` 下有 2 个**功能性** subagent——它们是"带专属工具权限的子进程"，不是角色扮演。每个的工具权限都做了**最小化**：

| Subagent | 做什么 | 工具权限（故意限制） | 何时用 |
| --- | --- | --- | --- |
| `code-reviewer` | 代码审查 + 跑校验 + 出分级报告 | `Read, Grep, Glob, Bash`（**不给 Edit/Write**——审查员不能自己改代码） | 改完 `sql/`、`tools/`、`scripts/`、`.claude/skills/` 后做正式 review |
| `schema-sync-checker` | 专查 schema 四处同步（含模板表头，第 4 处半自动） + 金额四件套完整性 | `Read, Grep, Glob`（**纯只读，连 Bash 都不给**——避免跟 code-reviewer 重叠） | 改了表结构 / 加新表 / 加派生字段后做同步性检查 |

**怎么调用**：让主 Claude 在适当时机用 Task 工具拉起，或直接说"用 code-reviewer 看一下这次改动"。

**与内置 `code-review` 的区别**：内置的是通用代码审查；项目专属的 `code-reviewer` 内置了项目的 4 条铁律（金额四件套 / schema 四处同步 / skill 路由互斥 / 不硬编码样本数据），不用每次再解释。

### 1.3 真实可用的自检命令

```bash
bash scripts/run_local_validation.sh           # 真实数据模式（16 步全过才算对）
bash scripts/run_local_validation.sh --demo    # demo 假数据模式（联调流程长啥样）
bash scripts/ci.sh                              # CI 一键检查（含敏感数据扫描）
bash scripts/check-sensitive-data.sh           # 单独扫敏感数据
```

### 1.4 真实存在的 Hook

#### A. PostToolUse 自动校验闸机（`.claude/settings.json`，2026-07-29 加）

每次 Claude 用 Edit / Write / MultiEdit 改完文件，自动跑 `scripts/auto-review.sh`：

```
Edit/Write/MultiEdit 触发
        │
        ▼
scripts/auto-review.sh
        │
        ├─ 改动只涉及 *.md / docs/ → 直接放行（不打扰文档活）
        │
        └─ 改动涉及 sql/tools/scripts/.claude → 跑校验
              │
              ├─ 敏感数据扫描挂 → exit 2 反馈给 Claude 自动修
              ├─ run_local_validation.sh --demo 挂 → exit 2 + 错误信息
              └─ 全过 → exit 0 静默放行
```

**关键**：`exit 2` 会让 Claude Code 自动看见 stderr 并尝试修复，不需要人工干预。

#### B. Git Hooks（**未自动安装**，需要时手动 `bash scripts/setup-git-hooks.sh`）

仓库已有脚本：
- `scripts/setup-git-hooks.sh` — 安装 pre-commit / pre-push / commit-msg 示例钩子

CI（GitHub Actions）：
- `.github/workflows/ci.yml` — PR 自动跑 `scripts/ci.sh`
- `.github/pull_request_template.md` — PR 提交模板

### 1.5 推荐工作方式（实操版）

1. **接到任务先 `explore`**：搞清楚要改的地方在哪、影响范围多大
2. **设计阶段用 `general-purpose`**：改 schema、改代码、写文档
3. **改完用 `task` 跑校验**：`bash scripts/run_local_validation.sh --demo`
4. **提交前用 `code-review`**：让另一个 agent 看一遍
5. **`commit` + `create-pr`**：交付

---

## Part 2 · 蓝图（未来规划，当前未实现）

> ⚠️ **以下 agent / skill / hook 当前未落配置**。
> 注意：`.claude/agents/` 下现在有 2 个**功能性** subagent（`code-reviewer` / `schema-sync-checker`，见 Part 1.2.B），下面列的是**业务域** agent，跟功能性 agent 不是一回事。
> 业务域 agent **当前都不要去调用**——会失败。

### 2.1 业务域 Agent（蓝图）

未来如果项目扩张到需要并行 / 隔离执行时，可能加的 agent：

| Agent | 计划职责 | 何时考虑加 |
| --- | --- | --- |
| `inventory-agent` | 库存 / 仓储 / 出入库逻辑 | 出入库逻辑变成独立模块时 |
| `purchase-agent` | 采购 / 入库 / 供应商 | 采购流程复杂到需要单独触发器时 |
| `sales-agent` | 销售合同 / 客户 / 发货 | 销售流程独立成子系统时 |
| `foreign-trade-agent` | 报关 / 出口单证 / 贸易条款 | 当前由 `trade-documents` skill 覆盖，**暂不需要** |
| `logistics-agent` | 物流 / 运输 / 跟踪 | 项目接入物流跟踪系统时 |
| `finance-agent` | 应收应付 / 成本 / 结算 | 当前由 `payment-receivable` skill 覆盖，**暂不需要** |
| `quality-agent` | 质检 / 验货 / 退换货 | 项目加入质检模块时 |

### 2.2 横切协同 Agent（蓝图）

| Agent | 计划职责 | 何时考虑加 |
| --- | --- | --- |
| `data-governance-agent` | 数据规范 / 主数据 / 业务键一致性 | 多人同时改基础数据，需要强约束时 |
| `integration-agent` | 系统集成 / 接口 / 第三方对接 | 对接 ERP / 银行 / 报关行 API 时 |
| `security-agent` | 权限 / 审计 / 敏感数据 | `audit_logs` 表开始真正写入时 |
| `review-agent` | 代码 / 设计 / 文档评审 | **✅ 已实现（2026-07-29）**，见 Part 1.2.B `code-reviewer` + `schema-sync-checker` |
| `research-agent` | 行业规则 / 外贸合规调研 | 接入新市场（欧盟 / 北美）需要合规研究时 |

### 2.3 规划中的 Hook（蓝图）

| Hook | 计划职责 | 状态 |
| --- | --- | --- |
| `pre-commit` 钩子 | SQL/DDL 语法检查 + Python 静态检查 | 脚本已备（`scripts/setup-git-hooks.sh`），未默认安装 |
| `pre-push` 钩子 | 关键验证脚本 + 业务一致性检查 | 同上 |
| `commit-msg` 钩子 | 规范 commit 信息格式 | 同上 |

### 2.4 什么时候才该把"蓝图"变成"现状"？

判断标准（**全部满足**才动手）：

1. **项目规模**：表数量 / 代码量翻倍（当前 25 表 / ~3400 行 Python）
2. **真实数据**：四张基础表之外的业务数据真实补齐（采购 / 销售 / 库存 / 报关 / 收款）
3. **使用场景**：出现"需要并行执行"或"需要工具权限隔离"的真实需求
4. **现有 skill 撑不住**：一个问题跨 3+ skill，且 skill 之间的路由开始打架

**当前阶段（2026-07）以上 4 条都不满足**——继续用 4 个 skill + 4 个内置 agent 即可。

---

## Part 3 · 设计原则（不管现状还是蓝图都适用）

### 3.1 Agent ≠ 角色扮演

Claude Code 里的 "agent" 本质是**带专属工具权限和系统提示的子进程**，不是 RolePlay 角色。

- 想让 Claude "用外贸业务经理视角看问题"——**不需要 agent**，在主对话里直接说"站在 X 角度审视"就行
- 真正适合做 agent 的是：**需要并行 / 隔离上下文 / 限制工具权限**的执行型任务

### 3.2 Skill 是"知识手册"，不是"执行单元"

每个 skill 是一份**业务规则文档**，让 Claude 在做相关任务时有据可查。

- skill **不主动执行**任何东西，只提供规则
- skill 之间**路由互斥**——一个问题只走一个 skill
- 改 schema 时，受影响的 skill 也要同步更新

### 3.3 Hook 是"自动护栏"，不是"业务逻辑承载点"

钩子应该只做"防呆"——防止低级错误（语法错 / 敏感数据泄漏 / commit 信息不规范）。

**不要**把业务规则塞进钩子（比如"短装超过 5% 拒绝 commit"）——业务规则归 `local_validator.py`，钩子只负责"跑这个 validator"。

---

## 参考

- `CLAUDE.md` — 4 个 skill 路由表 + 金额四件套铁律 + 改 schema 必须 sync 的四处
- `docs/BUSINESS_FLOW.md` — 一笔订单从询盘到收款的完整流程（**看这个比看 agent 更有用**）
- `docs/VALIDATION_GUIDE.md` — 16 步校验详解
- `CONTRIBUTING.md` — 贡献流程
