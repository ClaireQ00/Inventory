# Agent / Skill / Hook 指南

本项目未来要从进销存扩展到外贸标准化流程，建议用一套可复用的 agent/skill/钩子体系来做好协同和规范。

## 1. Agent 建议

### 1.1 顶层 Agent

- `general-purpose`
  - 负责整体开发、架构迭代、业务模块实现。
  - 适用于多文件改动、数据库建模、文档输出、接口设计。
- `task`
  - 负责执行命令、跑脚本、验证结果。
  - 例如运行 SQL、执行 Python 脚本、检查语法、执行自动化校验。
- `explore`
  - 负责调研、领域理解、分析现有项目结构。
  - 例如分析 `/Users/guixinqie/Desktop/开发/标准化外贸工作流` 中的业务模块，查找可复用流程。

### 1.2 业务域级 Agent

按业务模块拆分，便于后续模块扩展和责任分工：

- `inventory-agent`
  - 库存、仓储、物料主数据、出入库逻辑。
- `purchase-agent`
  - 采购、入库、供应商、采购单流程。
- `sales-agent`
  - 销售合同、客户、发货、交付。
- `foreign-trade-agent`
  - 外贸订单、报关、出口单证、贸易条款。
- `logistics-agent`
  - 物流、运输、仓外配送、跟踪。
- `finance-agent`
  - 应收应付、成本核算、发票、结算。
- `quality-agent`
  - 质检、验货、退换货、异常管理。

这些 agent 可以作为“业务专家”，负责单个模块的设计、建模、对接、文档。

### 1.3 横切协同 Subagent

跨模块或平台协同时，增加横切角色：

- `data-governance-agent`
  - 数据规范、主数据管理、字段统一、业务键一致性。
- `integration-agent`
  - 系统集成、接口规范、异步消息、第三方对接。
- `security-agent`
  - 权限、安全、审计、敏感数据保护。
- `review-agent`
  - 代码/设计/文档评审。
- `research-agent`
  - 规则调研、行业标准、外贸合规要求。

这种“业务域 + 横切域”架构，便于逐步把项目从单一系统扩展为协同平台。

## 2. Skill 建议

### 2.1 核心 Skill

- `commit`
  - 规范提交信息，适合每次完成改动后生成 commit message。
- `create-pr` / `update-pr`
  - 负责生成或更新拉取请求，适合协作开发和审查流程。
- `troubleshoot`
  - 用于定位命令失败、环境异常、工具错误。
- `customize-cloud-agent`
  - 用于安装运行时依赖、配置工具链、扩展开发环境。

### 2.2 质量与审查 Skill

- `code-review`
  - 正式审查代码实现、架构设计、SQL 建模、文档准确性。
- `security-review`
  - 审查安全风险、访问控制、SQL 注入、数据敏感性。

### 2.3 运行与自动化 Skill

- `task`
  - 运行验证脚本、执行迁移、生成文档、构建检查。
- `explore`
  - 用于分析外部项目、调研业务流程、寻找可复用内容。

## 3. Hook 建议

### 3.1 Git / CI 钩子

- `pre-commit`
  - 运行 SQL/DDL 语法检查。
  - 运行 Python 脚本静态检查。
  - 校验 Markdown 文档结构。
- `pre-push`
  - 运行关键验证脚本，例如数据库建表/种子脚本是否能执行。
  - 运行业务模块一致性检查。
- `commit-msg`
  - 规范提交信息格式。

### 3.2 CI 规则

- PR 校验：
  - `sql/01_schema.sql` 结构校验。
  - `sql/02_seed_data.sql` / `sql/03_master_data.sql` 数据格式校验。
  - `docs/` 文档完整性检查。
- 业务影响检查：
  - 如果变更涉及表结构或字段，触发“数据规范 review”。
  - 如果变更涉及接口或导入脚本，触发“集成 review”。

### 3.3 项目级流程 Hook

建议建立一套业务触发流程：

- `scripts/launch-module-workflow.sh <module>`
  - 启动对应业务模块的分析、设计和开发流程。
- `scripts/run-review.sh <module>`
  - 执行模块变更的审查检查。
- `CONTRIBUTING.md`
  - 定义使用 agent / skill 的规范。
  - 例如：新增模块先走 `explore`，改数据库先走 `general-purpose+task`，改动完成后走 `code-review`。

## 4. 推荐工作方式

### 4.1 需求拆解

1. `explore` / `research`：调研现有外贸工作流、梳理业务边界。
2. `general-purpose`：设计架构、调整数据库模型、写核心模块。
3. `task`：验证脚本、跑 SQL、检查是否可执行。
4. `review-agent`：进行代码/设计审查。
5. `commit` + `create-pr`：提交并生成 PR。

### 4.2 模块扩展原则

- 先定义“业务边界和数据边界”。
- 先做“主数据和接口规范”，再做“单据流程与具体实现”。
- 业务流程变更要同步更新“文档 + hooks”。
- 设计时留出“外贸模块”和“采购/销售模块”的对接点。

## 5. 对本项目的落地建议

当前项目可以先从这几个方向完善：

- 增加 `docs/AGENT_GUIDE.md`，描述协作规范。
- 在 `docs/README.md` 中链接这份指南。
- 后续可在仓库中补充 `CONTRIBUTING.md`、`scripts/` 目录。
- 为典型业务模块建立 `agent` 责任矩阵，例如库存、采购、销售、外贸、物流、财务。

### 5.1 落地示例文件

仓库已经新增以下文件和脚本，用于支持协作流程：

- `CONTRIBUTING.md`
- `scripts/ci.sh`
- `scripts/launch-module-workflow.sh`
- `scripts/run-review.sh`
- `scripts/setup-git-hooks.sh`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`

这些文件和脚本是一个起点，后续可以根据实际需求补充更多自动化检查和模块工作流。

这样一来，项目不仅是“进销存数据库”，还能逐步演化成“业务协同平台 + 规范化工作流”。
