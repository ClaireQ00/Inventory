# Inventory 前端开发长期规划 (Frontend Development Plan)

> 本文档回答："Inventory 项目从"无前端"到"有完整界面"的长期路径是什么"。
> 基于项目现有架构（MySQL + Python 标准库 + Docker + CSV 驱动）和团队约束（后端零第三方依赖、NAS 部署、非技术用户）制定。
>
> 关联文档：`docs/DESIGN.md`（架构设计）、`docs/SPECS.md`（功能规格）、`docs/TASKS.md`（任务清单）

---

## 1. 现状诊断

### 1.1 当前状态

| 维度 | 现状 |
|------|------|
| **数据层** | MySQL 8.0，25 张表，9 大模块，Docker Compose 编排 |
| **业务逻辑层** | Python 3.11 标准库，`tools/csv_to_sql.py` + `tools/local_validator.py`（16 步校验） |
| **前端层** | **阶段一已落地**。Streamlit 工作台（8501 端口）+ Adminer（8080 端口） |
| **数据录入** | Excel → 另存 CSV → `bash scripts/run_local_validation.sh` → `bash scripts/load-csv-to-db.sh` |
| **部署环境** | 绿联 NAS（DXP4800 Plus），已配置 DDNS + 端口转发，外网可访问 |
| **用户群体** | 3 个角色：外贸业务经理、仓库保管员、财务经理（均为非技术人员） |

### 1.2 核心痛点

1. **没有操作界面**：团队只能通过 Adminer 看原始数据表，无法按业务流程录入单据
2. **CSV 门槛高**：非技术同事填 CSV 容易出错（列错位、编码问题、逗号不对齐），虽然 `normalize_csv.py` 能修复一部分
3. **校验结果不直观**：16 步校验跑完输出文本日志，错误定位需要翻文件
4. **无法实时协作**：CSV 文件分散在个人电脑上，多人同时改容易冲突
5. **报表缺失**：库存预警、合同执行、收款对账等关键信息需要手写 SQL 查

### 1.3 现有资产（可复用）

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| 20+ 张表 schema | `sql/01_schema.sql` | API 层直接查询 |
| 16 步校验逻辑 | `tools/local_validator.py` | API 层封装为 `/validate` 接口 |
| 派生字段规则 | `tools/csv_to_sql.py::DERIVED_RULES` | API 层复用，前端调用 |
| CSV→SQL 转换 | `tools/csv_to_sql.py` | 保留为高级功能，API 层替代为主入口 |
| Docker 编排 | `docker-compose.yml` | 增加前端服务容器 |
| NAS 部署经验 | `docs/NAS_DEPLOY.md` | 前端走同样的 DDNS+端口转发 |
| Streamlit 原型 | `tools/streamlit_app.py` | 阶段一已落地，作为查询/报表入口 |

---

## 2. 长期架构选型

### 2.1 选型原则

1. **后端业务逻辑保持零第三方依赖**：校验、派生、转换等核心逻辑仍用 Python 标准库，不依赖框架
2. **API 层允许第三方框架**：前端呈现层需要 REST API 时，允许引入 FastAPI/Flask（后端零依赖原则不限制 API 框架选型）
3. **前端不受任何约束**：前端技术栈可以引入 npm 依赖、Streamlit 等（与后端原则完全独立）
4. **复用现有校验资产**：16 步校验、派生规则、四处同步机制不重写
5. **渐进式过渡**：CSV 流程保留，前端作为**新增入口**而非**替代**
6. **部署简单**：Docker Compose 一键启动，NAS 上能跑

### 2.2 目标架构（三层 + 双前端）

```
┌─────────────────────────────────────────────────────────────────┐
│  用户层（双前端入口）                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ React 管理台      │  │ Streamlit 原型   │  │ Blueprint    │  │
│  │ (阶段二·主入口)   │  │ (阶段一·已落地)  │  │ Widget 看板  │  │
│  │ ·9模块单据录入    │  │ ·数据查询+报表   │  │ (阶段三)     │  │
│  │ ·16步在线校验     │  │ ·校验报告可视化  │  │ ·库存预警    │  │
│  │ ·库存/合同/收款   │  │ ·快速反馈交互    │  │ ·合同执行    │  │
│  │   报表            │  │                  │  │ ·收款对账    │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────┬───────┘  │
└───────────┼─────────────────────┼───────────────────┼──────────┘
            │                     │                   │
            └─────────────────────┴───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Python API 层     │
                    │  (FastAPI/Flask)   │
                    │  ·复用 validator   │
                    │  ·复用 DERIVED_RULES│
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   MySQL 8.0       │
                    │   (现有 25 张表)   │
                    └───────────────────┘
```

### 2.3 技术栈对比

| 方案 | 后端 | 前端 | 部署 | 优点 | 缺点 | 适用阶段 |
|------|------|------|------|------|------|----------|
| **A: Streamlit** | Streamlit (PyPI) | Streamlit 自带 | Docker 容器 | 极快出界面、复用标准化外贸经验 | 交互弱、不适合生产长期运行 | **阶段一（已落地）** |
| **B: 标准库 API + React** | `http.server` + 手动路由 | React + Tailwind | Nginx + Docker | 后端零依赖、前端现代化 | 开发工作量大、路由/中间件全手写 | **阶段二降级备选** |
| **C: FastAPI + React** | FastAPI (PyPI) | React + Tailwind | Nginx + Docker | 开发效率高、自动文档、生态丰富、生产级 | 引入 PyPI 依赖（仅限 API 层，不影响核心业务逻辑零依赖原则） | **阶段二推荐** |
| **D: Adminer 增强** | 无（纯 SQL） | Adminer 插件 | 已有 | 零工作量 | 功能极有限 | **现状** |

**选型结论**：
- **阶段一**：方案 A（Streamlit）—— 已落地，`tools/streamlit_app.py` + `docker-compose.yml`
- **阶段二**：方案 C（FastAPI + React）—— 生产级主方案；方案 B 作为降级备选（如 PyPI 不可用环境）
- **阶段三**：Blueprint Widget —— 监控看板（Kimi Work 生态）

> **原则澄清**："零第三方依赖"约束的是**后端核心业务逻辑**（校验、派生、转换），不约束**API 框架选型**。FastAPI 仅作为 HTTP 接口层，不替代也不侵入 `tools/` 下的标准库逻辑。

---

## 3. 分阶段实施计划

### 阶段一：Streamlit 快速原型（已落地）

> **目标**：让团队能立即通过浏览器查询数据、查看报表。
> **状态**：`tools/streamlit_app.py` 已完成，`docker-compose.yml` 已更新。

#### 3.1.1 技术方案

- **后端**：复用现有 `tools/csv_to_sql.py` + `tools/local_validator.py`，不改逻辑
- **前端**：Streamlit（PyPI 依赖，仅限前端呈现层）
- **部署**：`docker-compose.yml` 中 `streamlit` 服务，端口 8501

#### 3.1.2 功能范围

| 模块 | 功能 | 优先级 | 状态 |
|------|------|--------|------|
| **首页仪表盘** | 库存总量、执行中合同、累计收款、低库存预警 | P0 | ✅ |
| **库存查询** | 按物料/仓库筛选、低库存标红、出入库流水 | P0 | ✅ |
| **合同执行** | 合同列表、执行进度（已发/未发）、明细查看 | P0 | ✅ |
| **基础资料** | 产品/客户/供应商/仓库一览 | P0 | ✅ |
| **报表中心** | 低库存预警、未发完合同、待处理差异、本月汇率 | P1 | ✅ |
| **校验日志** | 查看最新校验报告、历史日志列表 | P1 | ✅ |

#### 3.1.3 启动方式

```bash
# 本地开发（需安装 streamlit + pymysql）
pip install streamlit pymysql
streamlit run tools/streamlit_app.py

# Docker 一键启动（推荐）
docker compose up -d
# 浏览器打开 http://localhost:8501
```

---

### 阶段二：REST API + React 管理台（预计 3-6 个月）

> **目标**：生产级业务系统，替代 Adminer，部分替代 CSV 流程。
> **原则**：后端 API 允许使用 FastAPI（生产级框架），核心业务逻辑（校验/派生/转换）仍保持零依赖。

#### 3.2.1 架构设计

```
frontend/                       # React 项目（新目录）
├── public/
├── src/
│   ├── components/            # 通用组件
│   ├── pages/                 # 按模块分页面
│   │   ├── Dashboard/         # 首页仪表盘
│   │   ├── Products/          # 基础资料-物料
│   │   ├── Purchase/          # 采购模块
│   │   ├── Inventory/         # 库存模块
│   │   ├── Sales/             # 销售合同
│   │   ├── Delivery/          # 发货模块
│   │   ├── Shipping/          # 报关模块
│   │   ├── Receipts/          # 收款模块
│   │   ├── Quotation/         # 报价模块
│   │   └── Reports/           # 报表中心
│   ├── api/                   # API 客户端
│   └── utils/                 # 工具函数
├── package.json
└── Dockerfile

api/                           # Python API 层（新目录）
├── main.py                    # FastAPI 应用入口
├── routers/                   # 各模块接口
│   ├── products.py
│   ├── purchase.py
│   ├── inventory.py
│   ├── sales.py
│   ├── delivery.py
│   ├── shipping.py
│   ├── receipts.py
│   └── quotation.py
├── services/                  # 业务逻辑封装
│   ├── validators.py          # 调用 local_validator.py（零依赖）
│   └── derived.py             # 调用 csv_to_sql.py DERIVED_RULES（零依赖）
├── db.py                      # 数据库连接配置
└── Dockerfile
```

#### 3.2.2 API 设计（FastAPI）

```python
# api/main.py — FastAPI 应用入口
# 核心业务逻辑仍复用 tools/ 下的标准库代码

from fastapi import FastAPI
from routers import products, purchase, inventory, sales, delivery, shipping, receipts, quotation

app = FastAPI(title="Inventory API", version="1.0")

# 各模块路由
app.include_router(products.router, prefix="/api/products", tags=["基础资料"])
app.include_router(purchase.router, prefix="/api/purchase-orders", tags=["采购"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["库存"])
app.include_router(sales.router, prefix="/api/sales-contracts", tags=["销售"])
app.include_router(delivery.router, prefix="/api/delivery-orders", tags=["发货"])
app.include_router(shipping.router, prefix="/api/shipping-records", tags=["报关"])
app.include_router(receipts.router, prefix="/api/receipts", tags=["收款"])
app.include_router(quotation.router, prefix="/api/quotations", tags=["报价"])

# 校验接口（复用 local_validator.py）
@app.post("/api/validate")
async def run_validation():
    # 调用 tools/local_validator.py::run_validation()
    # 不改任何校验代码，仅做 HTTP 包装
    pass

# 派生接口（复用 csv_to_sql.py）
@app.post("/api/derive")
async def apply_derived_rules(data: dict):
    # 调用 tools/csv_to_sql.py::apply_derived_rules()
    # 不改任何派生逻辑，仅做 HTTP 包装
    pass
```

#### 3.2.3 前端设计（React）

| 页面 | 功能 | 对应模块 |
|------|------|----------|
| **仪表盘** | 库存总量、待处理单据数、本月收款、低库存预警 | 全局 |
| **物料档案** | 增删改查、密度反推预览、跨字段一致性提示 | F1.1~F1.3 |
| **采购管理** | PO 录入、状态流转、入库关联、金额校验 | F2.1~F2.2 |
| **库存管理** | 实时库存、出入库流水、调拨操作、库存对账 | F3.1~F3.6 |
| **销售合同** | SC 录入、金额四件套自动折算、状态机 | F4.1~F4.3 |
| **发货管理** | DO 录入、装柜回填、短装自动计算 | F5.1~F5.4 |
| **报关管理** | SH 录入、UCP600 容差提示、credit_note 处理 | F6.1~F6.5 |
| **收款管理** | 汇率录入、收款单、应收对账 | F7.1~F7.4 |
| **报价管理** | brief/formal 报价、KG×系数定价、转合同 | F9.1~F9.4 |
| **报表中心** | 低库存、合同执行、AR Aging、差异处理 | 全局 |
| **校验中心** | 在线跑 16 步校验、可视化报告、错误定位 | F10.3 |

#### 3.2.4 与现有架构的衔接

```
┌─────────────────────────────────────────────────────────────────┐
│  React 前端                                                      │
│  ·表单录入 → POST /api/xxx → FastAPI                            │
│  ·校验触发 → POST /api/validate → 复用 local_validator.py        │
│  ·派生计算 → POST /api/derive → 复用 csv_to_sql.py DERIVED_RULES│
│  ·报表查询 → GET /api/reports/xxx → SQL 直接查                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  FastAPI 层        │
                    │  ·HTTP 路由/参数校验│
                    │  ·自动 API 文档     │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Python 业务逻辑   │
                    │  ·local_validator  │ ← 零依赖（标准库）
                    │  ·csv_to_sql       │ ← 零依赖（标准库）
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   MySQL 8.0       │
                    │   (已有 25 张表)   │
                    └───────────────────┘
```

**关键衔接点**：
1. **校验逻辑**：FastAPI 层调用 `local_validator.py::run_validation()`，不改任何校验代码
2. **派生规则**：FastAPI 层调用 `csv_to_sql.py::apply_derived_rules()`，不改任何派生逻辑
3. **四处同步**：前端表单的字段名与 `sql/01_schema.sql` 保持一致，新增第 5 处同步（前端表单字段 ↔ schema）
4. **CSV 保留**：前端录入的数据可以导出为 CSV，也可以导入 CSV，双向兼容
5. **零依赖边界**：`tools/` 目录下的代码保持零第三方依赖，FastAPI 只作为 HTTP 包装层

#### 3.2.5 Docker Compose 更新

```yaml
# docker-compose.yml 增加两个服务
services:
  db:
    # ... 保持不变

  adminer:
    # ... 保持不变（保留作为备用查询入口）

  streamlit:
    # ... 阶段一已落地（保留作为查询入口）

  api:
    build: ./api
    container_name: inventory-api
    ports:
      - "127.0.0.1:8000:8000"  # 仅内网访问，React 前端反向代理
    environment:
      - DB_HOST=db
      - DB_NAME=inventory_db
      - DB_USER=inventory
      - DB_PASSWORD=${MYSQL_PASSWORD}
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build: ./frontend
    container_name: inventory-frontend
    ports:
      - "${FRONTEND_PORT:-3000}:80"  # 对外暴露，团队访问
    depends_on:
      - api
```

#### 3.2.6 验收标准

- [ ] 3 个角色各自有独立的首页和数据权限视图
- [ ] 9 大模块的增删改查全部可用
- [ ] 16 步校验能在线跑，错误信息定位到具体字段
- [ ] 派生字段实时计算（外径、体积、金额四件套）
- [ ] 报表中心包含：低库存预警、合同执行、AR Aging、差异处理
- [ ] CSV 导入/导出功能保留且可用
- [ ] NAS 上 `docker compose up -d` 一键启动全部服务
- [ ] 外网通过 DDNS 域名访问正常

---

### 阶段三：Blueprint Widget 监控层（持续迭代）

> **目标**：在 Kimi Work Dashboard 上建立库存/合同/收款的监控看板，服务管理层决策。
> **原则**：不替代操作层，只提供"一目了然"的监控视角。

#### 3.3.1 看板规划

| 看板 | Widget | 数据内容 | 刷新频率 |
|------|--------|----------|----------|
| **库存预警** | 库存总量 + 低库存列表 | `inventory` 表聚合 | 每小时 |
| **合同执行** | 合同数/已发/未发/已收 | `sales_contracts` + `delivery_orders` + `receipts` | 每小时 |
| **收款对账** | 本月收款/待收/逾期 | `receipts` + `sales_contracts` | 每天 |
| **报关进度** | 待报关/已报关/差异处理 | `shipping_records` + `credit_notes` | 每天 |
| **汇率看板** | 当月汇率 + 历史趋势 | `exchange_rates` | 每月 |

#### 3.3.2 技术方案

- **数据源**：Python 脚本定时从 MySQL 查询 → 生成 JSON 数据文件
- **展示层**：Kimi Work Blueprint Widget（HTML + JS）
- **部署**：Widget 部署在 Kimi Work 环境中，通过 API 拉取 NAS 上的数据

#### 3.3.3 与阶段二的关系

```
阶段二（React 管理台）          阶段三（Blueprint Widget）
     │                                │
     │ 操作层：录单据、跑校验          │ 监控层：看数据、做决策
     │                                │
     └──────────┬─────────────────────┘
                │
        ┌───────▼────────┐
        │  MySQL 8.0     │
        │  （唯一数据源） │
        └────────────────┘
```

---

## 4. 实施时间线

```
2026-Q3          2026-Q4          2027-Q1          2027-Q2
   │                │                │                │
   ▼                ▼                ▼                ▼
┌──────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│阶段一 │      │ 阶段二   │      │ 阶段二   │      │ 阶段三   │
│Stream│      │ API 开发 │      │ React    │      │ Widget   │
│lit   │      │ + 基础   │      │ 前端     │      │ 看板     │
│原型  │      │ 模块     │      │ 完善     │      │ 迭代     │
│已落地│      │ 4-6 周   │      │ 6-8 周   │      │ 持续     │
└──────┘      └──────────┘      └──────────┘      └──────────┘
   │
   └── 阶段一已可用，可并行推进阶段二设计
```

---

## 5. 风险评估与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| **FastAPI 学习成本** | 低 | 中 | FastAPI 文档完善、社区活跃；如团队不熟悉，先从简单 CRUD 开始 |
| **前端开发工作量大** | 高 | 中 | 优先做核心模块（库存+销售+收款），其他模块后续补齐；用现成 UI 库（Ant Design / shadcn/ui）减少工作量 |
| **NAS 性能瓶颈** | 低 | 中 | React 前端是静态文件，不占资源；API 层轻量；MySQL 已有优化；如不够再升级 NAS 内存 |
| **团队成员抗拒新系统** | 中 | 高 | 阶段一 Streamlit 已可用，让团队先用起来提反馈；保留 CSV 入口作为 fallback |
| **schema 变更导致前后端不同步** | 中 | 高 | 把前端表单字段加入"四处同步"升级为"五处同步"；加自动化检查脚本 |
| **外网访问安全问题** | 中 | 高 | API 服务绑 127.0.0.1（仅内网），前端 Nginx 做反向代理；加 Basic Auth 或简单 token；不暴露 3306 |

---

## 6. 立即行动项（Next Steps）

### 本周可做（阶段一已落地）

1. **验证 `docker compose up -d` 启动 Streamlit**
   - 浏览器打开 http://localhost:8501
   - 确认数据库连接、各模块查询正常

2. **让团队试用**
   - 发给外贸业务经理和财务经理试用
   - 收集反馈，验证交互模式

### 下周启动（阶段二设计）

3. **设计 API 接口规范**
   - 基于 FastAPI，列出所有 REST 接口
   - 确定请求/响应格式（JSON）

4. **搭建阶段二骨架**
   - `frontend/` 目录 + React + Vite + Tailwind
   - `api/` 目录 + FastAPI + PyMySQL

---

## 7. 与现有文档体系的衔接

| 本文档涉及 | 应同步更新的文档 |
|-----------|----------------|
| schema 变更 | `docs/DATA_MODEL.md`、`sql/01_schema.sql`、`tools/local_validator.py::SQLITE_SCHEMA` |
| 新增 API 接口 | `docs/SPECS.md`（新增功能点 F11.x） |
| 前端字段同步 | 新增"五处同步"规则到 `docs/BUSINESS_RULES.md R7` |
| 部署变更 | `docs/NAS_DEPLOY.md`（新增前端端口转发说明） |
| 任务拆分 | `docs/TASKS.md`（新增 F 组：前端开发任务） |

---

## 附录 A：标准化外贸工作流 → Inventory 代码复用清单

| 标准化外贸工作流功能 | Inventory 对应功能 | 复用度 |
|-------------------|-------------------|--------|
| 客户下拉选择器 | 客户/供应商/仓库选择器 | 高 |
| IQ 文件上传 | CSV 文件上传 | 高 |
| 产品明细预览表 | 库存/合同/采购明细表 | 高 |
| 订单信息表单 | 单据录入表单 | 中（字段不同） |
| 5 步生成流程按钮 | 16 步校验流程按钮 | 中（逻辑不同，UI模式同） |
| 文件生成状态看板 | 校验报告红黄灯 | 高 |
| PDF 导出 | CSV 导出 | 中（格式不同） |
| 客户档案配置 | 基础资料维护 | 中 |

**结论**：Streamlit 的前端代码（组件使用模式、状态管理、文件处理）可以大量复用，但业务逻辑必须重写为数据库操作。

---

## 附录 B：技术决策记录（ADR）

### ADR-FE-001：阶段二后端框架选型（FastAPI vs 标准库 http.server）

**决策**：阶段二后端 API 层使用 **FastAPI**，不复用标准库 `http.server`。

**背景**：项目原有"零第三方依赖"原则仅约束核心业务逻辑（校验、派生、转换），不约束 API 框架。Streamlit（阶段一）已证明前端层引入 PyPI 依赖不会破坏后端零依赖原则。

**理由**：
1. **开发效率**：FastAPI 自动生成 OpenAPI 文档、参数校验、依赖注入，减少重复代码
2. **生产级**：内置异步支持、自动文档（`/docs`）、类型提示，适合长期维护
3. **生态丰富**：中间件、认证、数据库 ORM（SQLAlchemy）生态成熟
4. **零依赖边界清晰**：FastAPI 仅做 HTTP 路由和参数校验，业务逻辑仍调用 `tools/local_validator.py` 和 `tools/csv_to_sql.py`（标准库）

**被保留的备选**：标准库 `http.server`（方案 B）—— 如部署环境无法安装 PyPI 包，可降级使用。

**被否决的方案**：Flask（功能足够但异步支持弱、文档生成需额外插件）、Django（过重，不适合 API-only 场景）。

### ADR-FE-002：为什么前端用 React 而非 Vue/Svelte

**决策**：前端用 React + Tailwind CSS。

**理由**：
1. React 生态最成熟，组件库（Ant Design、shadcn/ui）选择最多
2. 团队如果未来需要扩展，React 人才最好找
3. Tailwind CSS 与现有设计风格（简洁、功能导向）匹配

**被否决的备选**：Vue（也不错，但生态略小）、Svelte（太新，组件库少）。

### ADR-FE-003：为什么保留 CSV 入口

**决策**：前端录入不替代 CSV 流程，两者并存。

**理由**：
1. 项目设计哲学"输入边界是 CSV 文件"（`DESIGN.md §1.2`）
2. 批量导入场景下 CSV 仍最高效（一次导数百行）
3. 前端表单适合单笔/少量录入，CSV 适合批量
4. 给团队一个 fallback，防止前端出问题时业务中断

### ADR-FE-004：零第三方依赖原则的边界定义

**决策**：明确"零第三方依赖"的约束范围——仅约束 `tools/` 目录下的核心业务逻辑（校验、派生、转换），不约束前端呈现层和 API 框架层。

**分层说明**：

| 层级 | 约束 | 原因 |
|------|------|------|
| `tools/csv_to_sql.py` | ✅ 零依赖 | 核心数据转换逻辑，不能依赖框架 |
| `tools/local_validator.py` | ✅ 零依赖 | 核心校验逻辑，必须可独立运行 |
| `tools/streamlit_app.py` | ❌ 允许 Streamlit | 前端呈现层，非业务逻辑 |
| `api/` (FastAPI) | ❌ 允许 FastAPI | API 框架层，仅做 HTTP 包装 |
| `frontend/` (React) | ❌ 允许 npm | 完全独立的前端项目 |

**验证方式**：`bash scripts/run_local_validation.sh` 仍只依赖标准库，不受前端技术栈影响。

---

*本文档版本：v1.1 | 创建日期：2026-08-01 | 修订：2026-08-01 | 下次评审：阶段二启动时*
