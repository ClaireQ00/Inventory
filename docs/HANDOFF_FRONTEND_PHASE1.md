# Inventory 项目前端阶段一 · 交接文档

> 发件：前端参考项目（标准化外贸工作流）协作 agent
> 收件：Inventory 项目主 agent
> 日期：2026-08-01

---

## 1. 本次交付了什么

### 1.1 新增文件

| 文件 | 路径 | 说明 |
|------|------|------|
| Streamlit 工作台 | `tools/streamlit_app.py` | 6 个模块查询界面（见 §2） |
| 长期规划文档 | `docs/FRONTEND_PLAN.md` | 三阶段路线图 + 技术选型 ADR |

### 1.2 修改文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `docker-compose.yml` | **仅新增** `streamlit` 服务（端口 8501） | `db` / `adminer` 完全未动 |
| `.env.example` | **仅新增** `STREAMLIT_PORT=8501` | 不影响原有变量 |

### 1.3 核心业务文件 · 零改动确认

以下文件**未被任何方式修改**，可放心继续开发：

- ✅ `tools/csv_to_sql.py`
- ✅ `tools/local_validator.py`
- ✅ `sql/01_schema.sql`
- ✅ `scripts/run_local_validation.sh`
- ✅ `scripts/load-csv-to-db.sh`
- ✅ `data/csv/` 下所有模板和数据

---

## 2. `tools/streamlit_app.py` 功能清单

| 模块 | 功能 | 说明 |
|------|------|------|
| 🏠 首页仪表盘 | 库存品种数、执行中合同、累计收款(USD)、低库存预警 | 4 个关键指标卡片 |
| 📦 库存查询 | 按物料/仓库筛选、低库存标红、出入库流水 | 联动查询 |
| 📋 合同执行 | 合同列表（含已发/未发数）、合同明细查看 | 支持按客户筛选 |
| 🏭 基础资料 | 产品/客户/供应商/仓库 四表一览 | `is_self` 本公司标记显示 |
| 📊 报表中心 | 低库存预警、未发完合同、待处理差异、本月汇率 | 下拉切换 |
| 🔍 校验日志 | 最新校验报告、历史日志列表 | 自动判断 ERROR/WARN/通过 |

**数据录入仍走 CSV → 校验 → 导入流程**，本界面只提供**查询和报表**。

---

## 3. 启动方式

```bash
# Docker 一键启动（推荐）
docker compose up -d

# 浏览器访问
http://localhost:8080   # Adminer（原有）
http://localhost:8501   # Streamlit 工作台（新增）
```

NAS 部署需额外做端口转发（8501 → NAS 内网 IP:8501），详见 `docs/NAS_DEPLOY.md` 模式。

---

## 4. 已知问题与修复记录

| # | 问题 | 修复 | 状态 |
|---|------|------|------|
| 1 | `sales_contract_items` 无 `contract_item_no` 字段，SQL 报错 | 改为 `item_no AS contract_item_no` | ✅ 已修复 |
| 2 | `credit_notes` 无 `customer_code` 字段，JOIN `customers` 报错 | 改为通过 `sales_contracts` 间接 JOIN | ✅ 已修复 |
| 3 | `stock_logs` 查询未验证 `warehouse_code` 是否存在 | 已通过 `JOIN warehouses` 确保 | ✅ 设计已处理 |

**待验证**（需你跑启动确认）：
- [ ] Docker 容器内 `pip install streamlit pymysql` 是否正常
- [ ] 数据库连接环境变量是否正确传入
- [ ] 各模块在有 demo 数据时查询结果是否正常

---

## 5. 下一步建议（由你接手）

### 5.1 立即做（验证启动）

```bash
docker compose up -d
# 等待 10-15 秒让 db 初始化完成
docker compose logs -f streamlit
# 浏览器打开 http://localhost:8501
```

观察：
1. 侧边栏显示"数据库连接正常"
2. 首页 4 个指标卡片有数字（不是 0/空）
3. 库存查询 / 合同执行 / 基础资料 各模块数据正常

### 5.2 本周做（团队试用）

- 发给外贸业务经理和财务经理试用
- 收集"还需要什么查询/报表"的反馈
- 根据反馈决定阶段二优先级

### 5.3 阶段二启动时参考

- 技术选型见 `docs/FRONTEND_PLAN.md` §2.3
- FastAPI + React 是推荐方案，标准库 API 是降级备选
- 核心业务逻辑（`tools/` 下）保持零依赖，不碰

---

## 6. 参考来源说明

`streamlit_app.py` 的交互模式（selectbox、dataframe、progress、session_state）借鉴了「标准化外贸工作流」项目的 `workflow_app.py`，但**代码从零写成**，没有直接复制。业务逻辑全部改为数据库查询，与标准化外贸工作流的文件系统操作完全不同。

---

## 7. 回滚方式（如需）

```bash
# 仅移除 streamlit 服务，保留所有数据
docker compose stop streamlit
docker compose rm streamlit

# 如需彻底回滚代码
git checkout docker-compose.yml .env.example
git rm -f tools/streamlit_app.py docs/FRONTEND_PLAN.md
```

---

**文档版本：v1.0 | 如有问题请随时反馈**
