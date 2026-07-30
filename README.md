# 进销存管理系统（Inventory System）

面向**外贸出口企业**的进销存 + 报关单据 + 应收收款系统。
管"物"的流转（进货/存货/出货）+ 管"单据"的流转（报关/短装/贷记单）+ 管"钱"的流转（外币收款/汇率折算/对账）。

> 📖 完整业务说明、数据模型、设计文档见 **[docs/README.md](docs/README.md)**

---

## 🚀 快速开始（两种方式）

### 方式一：Docker 一键启动（推荐，适合团队）

需要先装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。

```bash
# 1. 准备配置（改一下 .env 里的密码）
cp .env.example .env

# 2. 启动 MySQL + 网页查询界面
docker compose up -d

# 3. （可选）灌入数据
bash scripts/load-csv-to-db.sh --demo    # 演示数据
# bash scripts/load-csv-to-db.sh         # 或用 data/csv 下的真实数据

# 4. 浏览器打开 http://localhost:8080 即可查询数据
```

> 👥 **远程团队（非技术同事）**：请看 **[docs/TEAM_SETUP.md](docs/TEAM_SETUP.md)**，傻瓜式图文步骤。

### 方式二：本地直接跑（适合开发者）

纯 Python 标准库项目，无需安装第三方依赖，只要有 Python 3.11+。

```bash
# 本地端到端校验（用 SQLite，14 步全过才算 OK）
bash scripts/run_local_validation.sh           # 用 data/csv 下的真实数据
bash scripts/run_local_validation.sh --demo    # 或用演示数据
```

---

## 📁 项目结构（Docker 相关）

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
└── tools/                  # 校验与转换工具链（纯标准库）
```

---

## 🔐 数据安全

- `data/`、`private/`、`.env` 已被 `.gitignore` 和 `.dockerignore` 双重排除，**真实业务数据不会进 Git、不会进镜像**。
- 推送 GitHub 前，仓库必须设为 **Private**（见 [PUBLISHING.md](PUBLISHING.md)）。
- 敏感数据扫描：`bash scripts/check-sensitive-data.sh`

## 📚 更多文档

- [docs/README.md](docs/README.md) — 完整项目说明与目录结构
- [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) — 远程团队（非技术）使用指南
- [docs/BUSINESS_FLOW.md](docs/BUSINESS_FLOW.md) — 业务流程全景
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — 数据模型与 ER 图
- [PUBLISHING.md](PUBLISHING.md) — 发布到 GitHub 私有仓库的步骤
