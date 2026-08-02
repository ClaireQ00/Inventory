# 进销存管理系统（Inventory System）

面向**外贸出口企业**的进销存 + 报关单据 + 应收收款一体化系统。
管"物"的流转（进货 / 存货 / 出货），管"单据"的流转（报关 / 短装 / 贷记单），管"钱"的流转（外币收款 / 汇率折算 / 对账）。

当前以客户 Q025（PVC 线管）作为样例客户跑通端到端流程，后续可扩展其他地区 / 品类的客户。

> 📖 完整业务说明、数据模型、设计文档见 [docs/README.md](docs/README.md)

---

## ✨ 功能总览

系统按业务流程分为 **9 大模块**：

| 模块 | 作用 |
| --- | --- |
| 📋 基础资料 | 物料、仓库、供应商、客户四类目录数据 |
| 🛒 采购 | 向供应商签采购单（PO） |
| 📦 库存 | 入库单、出库单、库存余额与流水 |
| 🤝 销售 | 与客户签销售合同（SC），含外币金额四件套 |
| 🚚 发货 | 内部装柜指令（DO），衔接合同账与报关账 |
| 🛃 报关 | 装船后的实际数据（SH / CI / PL），差异超 5% 走贷记单 |
| 💰 收款 | 客户付款 + 月固定汇率折算 CNY，应收对账 |
| 🔄 调拨 | 仓库间挪货，复用出入库流水 |
| 💬 报价 | 简要报价（brief）→ 正式报价（QT）→ 销售合同（PI）派生链 |

配套 **13 步业务校验**：合同金额 = 明细之和、入库 ≤ 采购、发货 ≤ 合同、库存对账、报价金额 = 明细之和等，从数据源头拦截错误。

---

## 🚀 快速开始

### 方式一：Docker 一键启动（推荐）

需要先安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

```bash
# 1. 准备配置（复制模板并改掉里面的密码）
cp .env.example .env

# 2. 启动 MySQL + 网页查询界面（Adminer）
docker compose up -d

# 3. （可选）灌入数据
bash scripts/load-csv-to-db.sh --demo    # 演示数据
# bash scripts/load-csv-to-db.sh         # 或用 data/csv 下的真实数据

# 4. 浏览器打开 http://localhost:8080 即可查询数据
```

> 🔒 **防泄露守门钩子（数据安全）**：仓库带 pre-commit/pre-push 双闸门，
> 拦截 `data/`、`.env`、大文件误提交/误推送。主人的 Mac 已配全局 git 模板，
> **在这台电脑上克隆自动生效，不用管**；其他电脑克隆后跑一次
> `bash tools/install_hooks.sh` 即可（就这一条指令）。钩子靠根目录
> `.inventory-guard` 文件认主，只在本项目生效，不影响其他仓库。

> 👥 **远程团队（非技术同事）**：请看 [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md)，傻瓜式图文步骤。

### 方式二：本地直接校验（适合开发者）

核心校验工具链只要有 Python 3.11+ 即可运行（2026-08-01 起项目取消零依赖原则，前端等扩展模块按需引入第三方依赖）：

```bash
bash scripts/run_local_validation.sh           # 用 data/csv 下的真实数据
bash scripts/run_local_validation.sh --demo    # 或用演示数据
```

---

## 🧰 技术栈

| 组件 | 用途 |
| --- | --- |
| MySQL 8.0 | 生产数据库（Docker 编排） |
| SQLite | 本地校验用轻量数据库（开发调试） |
| Adminer | 网页版数据库管理界面 |
| Docker Compose | 一键启动环境 |
| Python 3.11+ | 校验与转换工具链（核心脚本纯标准库；扩展模块按需引入第三方库） |

---

## 📁 项目结构

```
inventory/
├── Dockerfile              # 应用镜像（校验工具链）
├── docker-compose.yml      # MySQL + Adminer 一键编排
├── .env.example            # 数据库配置模板（复制成 .env 用）
├── .dockerignore           # 镜像构建排除清单（防数据外泄）
├── sql/                    # MySQL 建表 + 基础数据（启动时自动执行）
│   ├── 01_schema.sql
│   ├── 02_seed_data.sql
│   └── 03_master_data.sql
├── scripts/
│   ├── run_local_validation.sh   # 本地一键校验
│   └── load-csv-to-db.sh         # CSV → MySQL 灌数
└── tools/                  # 校验与转换工具链（核心纯标准库，含 streamlit 前端等扩展）
```

---

## 🔐 数据安全

- `data/`、`private/`、`mysql-data/`、`.env` 已被 `.gitignore` 和 `.dockerignore` 双重排除，**真实业务数据不会进 Git、不会进镜像**。
- 本仓库必须保持 **Private**（见 [PUBLISHING.md](PUBLISHING.md)）。
- 上传前可运行敏感数据扫描：`bash scripts/check-sensitive-data.sh`

---

## 📚 更多文档

- [docs/README.md](docs/README.md) — 完整项目说明与目录结构
- [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) — 远程团队（非技术）使用指南
- [docs/BUSINESS_FLOW.md](docs/BUSINESS_FLOW.md) — 业务流程全景
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — 数据模型与 ER 图
- [docs/BUSINESS_RULES.md](docs/BUSINESS_RULES.md) — 13 步业务校验规则
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — 业务术语表
- [PUBLISHING.md](PUBLISHING.md) — 发布到 GitHub 私有仓库的步骤

---

## 📌 当前进度

- ✅ 端到端主流程：询盘 → 报价 → 合同 → 采购 → 入库 → 发货 → 出库 → 报关 → 收款
- ✅ 13 步业务校验 + 敏感数据扫描
- ✅ 本地校验全通过（`--demo` 0 错误）
- 🔄 待办事项见 [docs/TASKS.md](docs/TASKS.md)
