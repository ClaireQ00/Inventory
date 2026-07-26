# 私有仓库发布说明

本项目已经完成本地 Git 初始化和基础工作流配置，建议发布到私有 GitHub 仓库以便后续协作和 CI 管理。

## 1. 创建私有仓库

在 GitHub 上创建一个私有仓库，例如：

- 仓库名称：`inventory` 或 `inventory-workflow`
- 可见范围：Private
- README：可选
- 添加 `.gitignore`：已在本地生成

## 2. 将本地仓库关联远程仓库

在本地项目根目录执行：

```bash
cd /Users/guixinqie/inventory

git remote add origin <your-private-repo-url>
git branch -M main
git push -u origin main
```

例如：

```bash
git remote add origin git@github.com:your-org/inventory.git
git push -u origin main
```

## 3. 已配置的发布支持

当前仓库已经包含：

- `scripts/init-git-repo.sh`：本地 Git 初始化脚本
- `.gitignore`：Python、macOS、日志、临时文件排除
- `.github/workflows/ci.yml`：GitHub Actions CI
- `.github/pull_request_template.md`：PR 模板
- `.github/ISSUE_TEMPLATE/feature_request.md`：功能需求 Issue 模板
- `.github/ISSUE_TEMPLATE/bug_report.md`：Bug 报告 Issue 模板
- `.github/ISSUE_TEMPLATE/config.yml`：Issue 模板配置

## 4. 建议发布前检查

建议先运行一次本地 CI 验证：

```bash
bash scripts/ci.sh
```

确认没有错误之后，再执行远程推送。

另外请务必确认仓库中不包含真实客户信息或敏感业务数据：

- 真实数据应放在 `data/` 或 `private/` 目录，并通过 `.gitignore` 忽略。
- 推送前请执行 `git status --short`，确认没有敏感文件处于暂存区。
- 可运行 `bash scripts/check-sensitive-data.sh` 检查是否存在 `.env` 或其他常见敏感文件。
- 如有需要，可阅读 `docs/PRIVATE_DATA_GUIDELINES.md` 了解更详细的处理规范。

## 5. 后续建议

- 私有仓库发布后，可在 GitHub Settings 中启用 `Actions`。
- 可将 `CONTRIBUTING.md` 作为协作规范说明文件。
- 后续可继续补充更完整的 Issue 模板、PR 审查清单、模块工作流文档。
