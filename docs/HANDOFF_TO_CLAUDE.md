# 交接文档：把 Inventory 项目转交给 Claude Code 继续（2026-08-29）

> 目的：项目此前由多个 AI 接力开发（Claude Code 起步 → Kimi 只读审查 → Codex 收尾）。
> 现在**主工程师正式交回 Claude Code**。本文把现状、约定、环境、未完成事项、踩坑记录一次性写清。
> **Claude 接手后先读本文，再按 `CLAUDE.md` 的其余约定工作。**
> 文档由 Codex 于 2026-08-29 实测环境后撰写；标 `[实测]` 的均为当天验证过的事实。

---

## 1. 30 秒速览

- 系统：外贸出口企业的**进销存 + 报关单据 + 应收收款**一体化系统。管"物"（进货/存货/出货）、管"单据"（报关/短装/贷记单）、管"钱"（外币收款/汇率折算/对账）。
- 样本：印尼客户 Q025（PVC 线管）已跑通端到端；**真实主数据已在库**（14,338 物料 / 596 客户 / 16 业务员）。后续扩展其他地区/品类，数据不是硬编码。
- 当前状态：三批审查修复全部完成、Kimi 只读复核通过、`make check` 全绿 `[实测]`、16 步校验 0 错误。
- **接手第一件事：把本地 `main`（HEAD=61419cc）推送到 GitHub 私有仓库，确认 CI 变绿。** 本地领先远端约 9 个提交（上次推送被质量门槛拦下，已修复并验证，见 §7）。
- 用户背景：老板本人，零编程基础、熟悉中国会计准则、**全程中文沟通**；仓库必须保持 **Private**。

---

## 2. 系统架构（速览）

完整版见 `ARCHITECTURE.md`。核心一句话：**业务规则只写一份**。

```
同事浏览器
   ├── :8082 前端 React + AntD（录入端：业务员/保管员/生产调度）
   │         Nginx 托管打包产物，反代 /api → api:8000
   └── :8501 Streamlit（查询端：老板/财务，只读，唯一例外是"关行复核"按钮）
                │
        :8000 api (FastAPI，唯一写入入口，业务逻辑全部复用 tools/，零重写)
                │
        :3306 db (MySQL 8.0，唯一数据真相源，22+ 张业务表)
                │
        data/csv/ (CSV 双轨，gitignored；离线编辑后 scripts/load-csv-to-db.sh 灌库)
```

- `api/main.py` 只做参数转发 + 调 `tools/db_writer.py`，不写业务规则。
- `tools/db_writer.py` = 所有业务规则闸门（超发/低价/关行/汇率/状态机…），全部走 `write_audit` 留痕。
- 无登录系统（内网信任），替代方案是**留痕（audit_logs）+ 公示（8501 预警卡）**。
- 校验器用 **SQLite 镜像**（`tools/local_validator.py`），不碰 MySQL，离线可跑。
- 派生字段在应用层算（`tools/csv_to_sql.py::DERIVED_RULES`），不用 MySQL GENERATED COLUMN（唯一例外 `delivery_order_items.short_qty`）。

## 3. 文档地图（按这个顺序读，别乱）

| 想看什么 | 看哪个 | 说明 |
| --- | --- | --- |
| 接手必读 | `CLAUDE.md` | 工作约定、铁律、skill 路由（本文就是给它的补充） |
| 项目全貌 | `docs/README.md`、`docs/BUSINESS_FLOW.md` | 一笔订单从询盘到收款怎么走 |
| 术语 | `docs/GLOSSARY.md` | 业务黑话 |
| 业务铁律 | `docs/BUSINESS_RULES.md` | R1~R14，代码必须与它一致 |
| 表结构/字段 | `docs/DATA_MODEL.md` | ER + 字段 |
| 功能需求/验收 | `docs/SPECS.md`、`docs/SCENARIOS.md` | 功能点 F1~F9 |
| 技术设计/决策 | `docs/DESIGN.md`、`docs/adr/` | ADR 0001~0005 |
| 待办清单 | `docs/TASKS.md` | 任务的唯一事实源（取代旧 `CLAUDE_BRIEF.md`） |
| 接口契约 | `API_SPEC.md`（根目录） | 改接口必须先改这里 |
| 架构速览 | `ARCHITECTURE.md`（根目录） | 容器拓扑/数据流 |
| 当前计划 | `PLAN.md`（根目录） | **状态已过期，需要你接手后更新（见 §8）** |
| 变更历史 | `CHANGELOG.md`（根目录） | 阶段归纳 |
| 协作决策 | `DECISIONS.md`（根目录） | 为什么这么选 |
| Kimi 审查产出 | `RESEARCH.md`、`.research/` | 只读审查报告 |

> ⚠️ `docs/CLAUDE_BRIEF.md` 已被 `docs/TASKS.md` 取代，仅留历史，不要再参考。

## 4. 当前完成度（2026-08-29 实况）

### 4.1 已完成（都能跑，均已实测）

- 端到端主流程：报价 → 合同 → 采购 → 入库 → 发货 → 出库 → 报关 → 收款 → 提成，全通。
- **16 步业务校验**（`tools/local_validator.py`）本地全绿：`make check` 全绿 `[实测]`（lint + e2e 41 断言 + 16 步校验）。
- 三批审查修复全部完成，Kimi 只读复核结论**全部"贴合"**，0 个新 🔴/🟡：
  - 第①批「钱和账」（`9aad257`…`384e821`）：删孤立 JOIN / actual_quantity 闸门 / 老板特批留痕落库 / SQLite 补自然键 / FOR UPDATE / draft 拒发
  - 第②批「流程闭环」（`77ad901` + `b1d7c3c`）：回填实发 `/api/docs/delivery/actual` + 前端页 / 作废发货 `/api/docs/delivery/cancel` / 销售出库累计闸门 / 汇率月固定双落地
  - 第③批「加固七件套」（`0040d83`）：贷记单录入通道 + 前端页 / CORS 收紧 / 附件上传流式限长+白名单 / 收款累计口径统一 / 审计 record_id / 校验步号 / 关行留痕截头留尾
- 真实主数据治理（2026-08-11）：物料全量重编码 `M-{客户编码}-{3位流水}`、客户编码 R12（字母+4位数字）、业务员档案、14,338 行产品核实。
- 录入端 React 15 个页面全上线（报价/合同/发货/回填实发/出入库/收款/汇率/客户/物料/业务员/辅料/贷记单…）。
- 辅料模块 M1~M3：档案/收发存/标签纸需求测算/包装与工艺档案自动建档。
- CSV 双轨 + 灌库幂等（R14）+ `tools/db_to_csv.py` 回写方向。
- 简要报价单导出（`tools/export_brief_quote.py` → `output/quotes/`，模板 `data/简要报价模板.xltx`）。

### 4.2 未完成（见 §8 详表）

- 计划文档 `PLAN.md` 状态过期（②③批实际已完成，还没改状态）。
- `docs/TASKS.md` 里还有一批未勾项（F1.5 团队试用 / FB.1 导入中心页 / G7.8 客户名称整理 / M4 辅料校验 / F3.1 打印导出等）。
- Kimi 最新报告留了 2 条 🔵 级观察（贷记单三角关系校验、附件上传内存缓冲），属于"有空再修"。

## 5. 质量门槛与多 AI 协作（2026-08-15 建立，必须遵守）

### 5.1 质量门槛（`Makefile`）

```bash
make lint      # 秒级语法门：py_compile 全文件 + ruff 致命级（ruff 未装则跳过）
make test      # e2e：tests/demo_roleplay_test.py，打真实 API（需 docker 容器在跑）
make validate  # 16 步业务校验：SQLite 镜像跑 demo 数据，不碰 MySQL
make check     # 完整门槛 = lint + test + validate（pre-push 自动跑）
```

- **约定：改完代码必须 `make check` 全绿才提交/推送；不过就修复或回滚，不要 `--no-verify`。**
- pre-commit：防泄露扫描 + 暂存区含 `.py` 时自动 `make lint`。
- pre-push：防泄露扫描 + 推送范围含 `.py` 时自动 `make check`。
- 钩子本体在 `hooks/`（版本化），安装方式：`bash tools/install_hooks.sh`（本机已装，符号链接到 `.git/hooks/`）。
- `make check` 需要两样东西，缺一必挂：
  1. **Docker 在运行**（e2e 连 MySQL + 打真实 API）；
  2. **Python ≥ 3.10**（测试用了 `dict | None` 注解；本机系统 `python3` 是 3.9.6 会报 `TypeError`，必须用 conda 的 3.12，见 §6.3）。

### 5.2 多 AI 分工协议（`DECISIONS.md`）

- **Claude Code = 主工程师**：读写所有代码、跑测试、操作数据库、Git 提交。
- **Kimi = 研究员/审查员**：只读代码；唯一可写文件是 `.research/review_YYYYMMDD.md`；禁止改 `tools/ api/ frontend/ sql/ tests/ scripts/`、禁碰数据库、禁跑写操作。
- 协作文件：`PLAN.md`（Claude 写）/ `RESEARCH.md`（Kimi 写）/ `DECISIONS.md`（双方追加）/ `.research/`（Kimi 工作区）。
- Kimi 审查入口：`bash scripts/kimi_review.sh [N]`（N=最近 N 次 commit，默认 3）。
- 无人值守驱动：`bash scripts/claude-driver.sh`（每轮读 `CLAUDE.md`+`docs/TASKS.md` 挑一件推进，自动跑校验并 commit）。
- **提交纪律**：只 `git add` 明确路径，永远不用 `git add -A`（防止把别的 agent 的半成品卷进提交）；同一时间只让一个 agent 改 `tools/`。

## 6. 环境与启动方式

### 6.1 一键启动（Docker）

```bash
open -a Docker                       # 启动 Docker Desktop（如没开）
docker compose up -d                 # 起全部 5 个服务
docker compose ps                    # 应看到 5 个容器 Up
```

| 容器 | 端口 | 用途 |
| --- | --- | --- |
| inventory-db | 127.0.0.1:3306 | MySQL 8.0（真实数据真相源） |
| inventory-api | 127.0.0.1:8000 | FastAPI，唯一写入入口 |
| inventory-adminer | localhost:8080 | 网页查库（看数据用这个） |
| inventory-streamlit | localhost:8501 | 查询/报表端 |
| inventory-frontend | localhost:8082 | React 录入端 |

当前 5 个容器全部 Up `[实测]`；`db` 健康检查通过。

### 6.2 Python 版本坑（重点！）

```bash
python3 --version                    # 系统自带 = 3.9.6 ❌ 跑不了 e2e
/opt/anaconda3/bin/python3 --version # conda = 3.12.4 ✅
```

- 在 `(base)` 终端里 `python3` 就是 conda 的 3.12，没问题。
- **但 Claude 子进程/钩子可能拿到 `/usr/bin/python3`（3.9）**：若 `make check` 报
  `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`，就是它。
  解决：`PATH="/opt/anaconda3/bin:$PATH" make check`，或让 shell 激活 conda。
- CI（GitHub Actions）里用的是 `setup-python@v6` + 3.11，没有这个问题。

### 6.3 自检命令（每天收工前跑）

```bash
bash scripts/run_local_validation.sh           # 真实数据（data/csv）
bash scripts/run_local_validation.sh --demo    # demo 数据（沙箱）
PATH="/opt/anaconda3/bin:$PATH" make check     # 完整门槛（需 Docker）
```

## 7. 接手后第一件事：推送 + 确认 CI（最重要）

### 7.1 背景

- 上次 `git push --set-upstream origin main` 被 pre-push 质量门槛拦下（当时 Docker 没启动，e2e 预检连不上 MySQL 中止）。
- 已修复验证：Docker 已启动、5 容器在跑、`make check` 全绿 `[实测]`。**现在可以推了。**

### 7.2 本地领先远端的提交（约 9 个，按顺序）

```text
2ce3b16  ci: 升级 GitHub Actions 到 checkout@v5 / setup-python@v6   ← 修 CI 的根因
dc1022f  chore(collab): 多 AI 协作基础设施 (分工协议/文档驱动/质量门槛)
192e602  fix(schema): 01_schema.sql 补四张明细表自然唯一键 (第①批返工)
365396a  chore(hooks): 根 hooks/ 目录同步质量门槛段
945f1e5  docs(review): 收录 Kimi 第①批只读审查报告
77ad901  feat(batch2): 流程闭环四件套 (第②批)
b1d7c3c  fix(batch2): cancel_delivery 补锁合同行 FOR UPDATE
0040d83  feat(batch3): 加固七件套 (第③批)
61419cc  docs(review): 收录 Kimi 第③批只读审查报告  ← 当前 HEAD
```

> 远端至少已推到 `0576a02`（CI 曾在该提交上跑过）。`2ce3b16` 及之后是否已推未确认
> （网络受限无法核对），接手后先 `git fetch origin` 再用
> `git log --oneline origin/main..main` 精确列出差额。

### 7.3 推送步骤

```bash
cd /Users/guixinqie/inventory
git status                        # 应为干净工作区
git push --set-upstream origin main   # 若报 "no upstream"，用这条；否则 git push 即可
```

- 推送会再自动跑一次 `make check`（需 Docker 开着 + `(base)` 环境）。
- 凭据：用户名 `ClaireQ00`，密码栏粘贴 PAT（`ghp_` 开头，需勾 `repo` + `workflow` 两个 scope）。
- 脏凭据先清：`printf "protocol=https\nhost=github.com\n\n" | git credential-osxkeychain erase`
- 推完去 GitHub Actions 页看最新一次 run 是否变绿。
  - 之前的失败原因：旧 workflow 用 `checkout@v4`/`setup-python@v5`（Node 20 运行时），
    GitHub 已强制改用 Node 24，旧 action 直接挂（11 秒就失败）。
  - 现在 `ci.yml` 已是 `checkout@v5` + `setup-python@v6`（Node 24），`scripts/ci.sh` 不需要 Docker，应能过。

### 7.4 推完后顺手做

- 更新 `PLAN.md`：第②批「流程闭环」✅ 已完成、第③批「加固」✅ 已完成。
- 检查 `README.md` 里"13 步校验"字样（实际已是 16 步），顺手改成 16。

## 8. 待办与已知缺口（按优先级）

### 8.1 开发侧待办（`docs/TASKS.md` 未勾项）

| ID | 事项 | 优先级 | 状态/卡点 |
| --- | --- | --- | --- |
| F1.5 | 团队试用 + 反馈收集 | P1 | **等老板把 8082/8501 发给业务/财务经理** |
| FB.1 | 导入中心页（React：上传 CSV→校验→导入） | P1 | 可做 |
| G7.8 | 客户真实名称整理（596 占位名 + 21 条 5 位异常码 + 6 个业务员姓名） | P1 | **等老板交付名单** |
| M4 | 辅料校验报表（库存=流水一致性 + 低库存预警进 16 步） | P2 | 可做 |
| F3.1 | 打印导出（合同/发货/出库/对账/报关，共 6 种） | P2 | **等老板给 ①空白底稿 ②真实样张脱敏版**（已落地 1 种：简要报价单） |
| G7.9 | 半成品原材料收发模块 | P2 | 预留 |
| G7.10 | 成本指导价→利润核算 | P2 | 预留 |
| S5.9 | 历史行免反算开关（快照重量链路） | P2 | 预留 |
| T3.x | 阶段二财务深化（AP/账龄/汇兑损益/信用证） | 暂缓 | 录入端稳定后再动 |
| 🔵 | 贷记单三角关系校验（shipping_no/material_id/contract_no） | 低 | Kimi 建议，见 `.research/review_20260815.md` |
| 🔵 | 附件上传边读边落盘（现先缓冲到内存再落盘） | 低 | Kimi 建议 |

### 8.2 老板待补的数据/决策（阻塞项，主动找老板要）

1. 客户真实名称名单（G7.8）。
2. 6 个业务员姓名（C/E/K/P/T/Z）。
3. 提成系数与计算公式、回款时间分档（`commission_rules` 表已建，系数空）。
4. 辅料标签尺寸 width/height、min_stock 安全库存、材质/默认供应商。
5. 30/40/60/90/110mm 五档管径归类确认（新规则 vs 历史归类，只影响新录入）。
6. 其余 5 种单据打印模板（F3.1）。
7. 2026-09-01 记得录 9 月汇率（16 步校验已在 WARN 提示"下月汇率还没录"）。

## 9. 数据安全红线（违反 = 泄密，最高优先级）

- `data/`、`private/`、`mysql-data/`、`.env`、`output/`、`data/backups/` **永不进 Git、永不进镜像**（.gitignore + .dockerignore 双重排除）。
- 仓库必须保持 **Private**；上传前跑 `bash scripts/check-sensitive-data.sh`。
- 钩子会拦截敏感路径；**不要 `--no-verify` 强推**（一旦进历史，清洗很麻烦）。
- 真实数据位置（都是正式数据，勿删勿动）：
  - `data/csv/`：真实 CSV 双轨（约 15,000 行）
  - `data/产品数据.xlsx`、`data/产品数据_整理后.xlsx`：14,338 行产品原始/整理稿
  - `data/简要报价模板.xltx`：简要报价单模板（含真实业务痕迹）
  - `data/attachments/`：用户真实上传的标签 PDF（如 SELANG BENANG），**勿删**
  - `data/logs/material_remap_20260811.csv`：物料重编码映射留痕
  - `mysql-data/`：MySQL 数据目录（整个项目最重的资产）
- `.env` 里是真实数据库密码；`.env.example` 是占位模板，允许进仓库。

## 10. 踩坑记录（都是真金白银换来的，别再踩）

1. **改 `tools/` 或 `api/` 后必须 `docker compose restart api`** 才对真实容器生效（tools/ 是 ro 挂载，uvicorn 进程缓存旧模块）。之前出现过"双回归跑的是旧代码"的假绿。
2. **改 schema 必须四处同步（R7）**：`sql/01_schema.sql` / `tools/local_validator.py::SQLITE_SCHEMA` / `tools/csv_to_sql.py::DERIVED_RULES`（仅派生字段）/ `sample/templates/*_template.csv`。漏一处校验就对不上；`scripts/check-template-schema-sync.sh` 自动兜底。
3. **执行迁移 DDL 前先查 `SHOW PROCESSLIST`**：曾因长时间连接卡 metadata lock（ALTER 挂住），`docker compose restart api streamlit` 释放后完成。
4. **测试数据编码段铁律**：客户 `Z9999` / 物料 `M-Z9999-*` / 单据 `*-TEST*`，跑前自动冲突预检，撞上现存数据立即中止。别用真实编码段做测试。
5. **提交只 `git add` 明确路径**，不用 `git add -A`。
6. **系统 `python3` 是 3.9**，跑测试/推送前确认在用 conda 3.12（见 §6.2）。
7. 迁移过"先 ALTER 加列、再重启 api"，顺序反了新代码会撞缺列。
8. 本机无 `gh` CLI、无 GitHub connector 权限，查远端状态用浏览器或 `git fetch origin` 后看日志。

## 11. 本机工具链备注

- Claude Code 此前配置过 `ANTHROPIC_BASE_URL=https://api.moonshot.cn/anthropic`（即用 Kimi 的模型跑 Claude Code CLI），token 在用户的 shell 配置文件里（**本文不写 token**）。如要转回官方 Claude 模型，记得先核对这几个环境变量。
- `scripts/claude-driver.sh`：无人值守驱动（会自动 commit，要求工作区干净）。
- `scripts/kimi_review.sh`：Kimi 只读审查入口。
- `.claude/settings.json` 有 PostToolUse 钩子：每次 Edit/Write 后自动跑 `scripts/auto-review.sh`。
- `.claude/skills/` 有 4 个业务 skill（product-params / derived-fields / trade-documents / payment-receivable），路由表在 `CLAUDE.md`。

## 12. 交接核对清单（Claude 第一天照做）

```bash
# 1) 环境自检
git status                                        # 干净
git log --oneline -3                              # HEAD=61419cc
docker compose ps                                 # 5 容器 Up
PATH="/opt/anaconda3/bin:$PATH" make check        # 全绿

# 2) 推送
git fetch origin                                  # 确认远端状态
git log --oneline origin/main..main               # 列出待推提交
git push --set-upstream origin main               # 推送（自动跑 make check）

# 3) 收尾
#    更新 PLAN.md 状态；改 README 的"13 步"→"16 步"
#    然后找老板对 §8.2 的待补清单
```

---

*交接人：Codex（2026-08-29）｜ 主工程师：Claude Code（即日起）｜ 项目主人：老板（ClaireQ00）*
