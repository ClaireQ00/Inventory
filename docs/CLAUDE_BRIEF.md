# Claude Code 继续工作说明

## 项目当前状态

仓库路径：`/Users/guixinqie/inventory`

### 已完成内容

1. 数据库结构与示例数据
   - `sql/01_schema.sql`
   - `sql/02_seed_data.sql`
   - `sql/03_master_data.sql`

2. 协作文档与流程
   - `docs/README.md`
   - `docs/AGENT_GUIDE.md`
   - `docs/IMPORT_TEMPLATES.md`
   - `docs/PRIVATE_DATA_GUIDELINES.md`
   - `CONTRIBUTING.md`
   - `PUBLISHING.md`

3. 自动化检查与脚本
   - `scripts/ci.sh`
   - `scripts/run-review.sh`
   - `scripts/launch-module-workflow.sh`
   - `scripts/setup-git-hooks.sh`
   - `scripts/check-sensitive-data.sh`
   - `scripts/init-git-repo.sh`

4. GitHub 配置
   - `.github/workflows/ci.yml`
   - `.github/pull_request_template.md`
   - `.github/ISSUE_TEMPLATE/feature_request.md`
   - `.github/ISSUE_TEMPLATE/bug_report.md`
   - `.github/ISSUE_TEMPLATE/config.yml`

5. 导入模板
   - `sample/templates/*_template.csv`

### 隐私保护

- `.gitignore` 已忽略：`data/`、`private/`、`.env`、`.env.*`
- 真实数据应保存在本地 `data/` 或 `private/`
- 真实敏感数据不能提交到仓库
- 可使用 `bash scripts/check-sensitive-data.sh` 检查敏感文件

### 本地验证结果

- `bash scripts/ci.sh` 通过
- `bash scripts/check-sensitive-data.sh` 通过
- Git 仓库已初始化，工作区干净

## 现在应继续的方向

### 目标

开始用真实数据验证当前进销存流程，但真实数据必须留在本地，不能提交到仓库。

### 需要 Claude Code 做的事情

1. 生成“CSV -> SQL 导入”的自动化脚本或 SQL 模板
2. 生成“从本地 CSV 导入数据库并验证”的执行脚本
3. 设计真实数据验证流程，按顺序验证：
   - 基础资料录入
   - 采购单
   - 入库单
   - 销售合同
   - 发货单
   - 出库单
   - 库存与流水对账

### 关键注意事项

- 真实客户、供应商、合同、订单、价格等敏感信息不可写入仓库
- 真实数据只放在本地 `data/` 或 `private/`
- 测试前请先运行：
  - `git status --short`
  - `bash scripts/check-sensitive-data.sh`

## 可用文件与模板

- `sample/templates/products_template.csv`
- `sample/templates/warehouses_template.csv`
- `sample/templates/suppliers_template.csv`
- `sample/templates/customers_template.csv`
- `sample/templates/inventory_template.csv`
- `sample/templates/purchase_orders_template.csv`
- `sample/templates/purchase_order_items_template.csv`
- `sample/templates/stock_in_template.csv`
- `sample/templates/stock_in_items_template.csv`
- `sample/templates/sales_contracts_template.csv`
- `sample/templates/sales_contract_items_template.csv`
- `sample/templates/delivery_orders_template.csv`
- `sample/templates/delivery_order_items_template.csv`
- `sample/templates/stock_out_template.csv`
- `sample/templates/stock_out_items_template.csv`

---

请直接基于这个项目继续完成“真实数据导入与流程验证”工作。