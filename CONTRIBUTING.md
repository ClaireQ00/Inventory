# CONTRIBUTING

欢迎参与本项目！这是一个面向外贸出口企业的进销存 + 报关 + 应收收款系统，业务范围覆盖采购 → 入库 → 库存 → 销售 → 发货 → 报关 → 收款的完整闭环。

## 1. 贡献流程

1. 先阅读 `docs/README.md` 和 `docs/BUSINESS_FLOW.md`（业务流程全景图）。
2. 协作规范请参考 `docs/AGENT_GUIDE.md`（Part 1 现状 / Part 2 蓝图）。
3. 使用 `issue` 记录需求或问题，优先选择合适的模板（Feature request / Bug report）。
4. 创建 feature 分支，格式建议：
   - `feature/<模块>-<简短说明>`
   - `fix/<问题>-<简短说明>`
5. 开发时，优先使用 Claude Code 自带的 `general-purpose`、`task`、`explore`、`code-review` 等内置 agent（详见 AGENT_GUIDE.md Part 1）。
6. 变更完成后，提交 PR 并附上变更说明。
7. PR 通过后，再使用 `commit` / `create-pr` / `update-pr` 进行交付。

## 2. Agent / Skill 使用建议

### 2.1 开发阶段

- `general-purpose`
  - 负责整体设计、数据建模、功能实现、文档改写。
- `task`
  - 负责运行脚本、检查语法、验证现有 SQL 和示例。
- `explore`
  - 负责调研现有业务、分析外部流程、理解模块关系。
- `research`
  - 负责行业规则、外贸合规、标准化流程调研。

### 2.2 审查阶段

- `code-review`
  - 审查 SQL 结构、业务模型、代码风格、文档描述。
- `security-review`
  - 审查权限、数据安全、接口安全、SQL 注入、敏感字段。
- `troubleshoot`
  - 定位执行失败、环境问题、命令异常。

### 2.3 交付阶段

- `commit`
  - 规范提交信息。
- `create-pr` / `update-pr`
  - 生成或更新 PR。
- `customize-cloud-agent`
  - 安装依赖、配置运行环境。

## 3. 敏感数据处理原则

真实客户数据、供应商信息、合同明细等敏感信息不应直接提交到仓库。请遵循以下做法：

- 使用 `data/` 或 `private/` 目录保存本地测试数据，这些目录已被加入 `.gitignore`。
- 真实数据只在本地分析和验证，不要将真实文件加入 git 版本控制。
- 推送前务必运行 `git status --short`，确认没有敏感文件出现在暂存区。
- 若需要共享测试数据，使用脱敏后数据或安全渠道，避免通过 GitHub 传输原始敏感信息。

更多细则请参见 `docs/PRIVATE_DATA_GUIDELINES.md`。

在提交和推送前，可以使用以下脚本检查是否存在敏感配置文件：

```bash
bash scripts/check-sensitive-data.sh
```

## 4. Git Hooks 建议

本项目推荐使用以下钩子：

- `pre-commit`
  - SQL/DDL 语法检查
  - Python 语法检查
  - 文档格式检查
- `pre-push`
  - 运行关键验证脚本
  - 运行业务一致性检查
- `commit-msg`
  - 规范 commit 信息格式

如果你希望，可以使用 `scripts/setup-git-hooks.sh` 来安装示例钩子。

## 5. CI / GitHub 流程

本仓库含有 GitHub Actions CI，可自动执行 `scripts/ci.sh`。

- CI 流程文件：`.github/workflows/ci.yml`
- PR 模板：`.github/pull_request_template.md`
- Issue 模板：`.github/ISSUE_TEMPLATE/feature_request.md`、`.github/ISSUE_TEMPLATE/bug_report.md`

建议在提交 PR 前运行：

```bash
bash scripts/ci.sh
```

## 6. 脚本入口

仓库中提供了一组 helper 脚本，用于规范化工作流：

- `scripts/launch-module-workflow.sh <module>`
  - 启动一个业务模块的工作流程。
- `scripts/run-review.sh [module]`
  - 针对模块或全局运行审查检查。
- `scripts/setup-git-hooks.sh`
  - 安装仓库内的 Git 钩子示例。
- `bash scripts/check-sensitive-data.sh`
  - 检查是否存在常见敏感文件或配置。

## 7. 工作建议

### 7.1 新增模块

1. 先进行 `explore` / `research`，梳理业务边界。
2. 设计主数据、字典、接口、公用流程。
3. 编写文档、补齐 `docs/` 说明。
4. 实现 schema 和示例数据。
5. 在 PR 中明确说明与现有模块的对接点。

### 7.2 修改数据模型

1. 明确变更影响范围。
2. 先更新文档，再改 schema。
3. 运行 `scripts/run-review.sh` 进行检查。
4. 确认现有示例和 seed 数据仍可执行。

## 6. 参考文档

- `docs/README.md`
- `docs/AGENT_GUIDE.md`
