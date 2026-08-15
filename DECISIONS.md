# 技术决策日志（双方追加，新条目放最上面）

> 记录"为什么这么选"。已有正式 ADR 在 `docs/adr/0001-0005`（派生字段应用层 / 调拨软关联 / 报价派生链 / 外键用业务编号 / 快照重量链路），此处不重复，只记决策上下文与未入 ADR 的决定。

## 2026-08-15 暂不引入 structlog / Sentry / Langfuse（用户问，Claude 评估）

- **structlog**: 已有三层日志——uvicorn 访问日志（docker logs 可查）、`audit_logs` 表（业务留痕：谁/何时/改了什么）、`data/logs/validation_*.log`（校验留痕）。格式化库对单人内网系统收益低于引入成本。
- **Sentry**: 内网系统、NAS 部署、无外网依赖偏好；自托管 Sentry 要多养一个重型容器。异常看 `docker logs inventory-api` 已够。**重新评估条件**：系统上公网或多人使用时，自托管 Sentry（或轻量 glitchtip）。
- **Langfuse**: 只适用于运行时调 LLM 的 AI 应用；本项目 LLM 只在开发协作侧（Claude/Kimi CLI），产品本身零 LLM 调用，不适用。
- 业务健康的"监控"已由 8501 承担：超发拦截留痕、关行复核清单、低价特批预警卡、对账平衡。**业务系统监控的是账平不平，不是 QPS。**

## 2026-08-15 暂不引入 CrewAI / AutoGen 编排框架（用户问，Claude 评估）

**问题**: 项目变大后是否用编排框架定义角色（架构师/工程师/测试员）让框架调度？

**结论: 现阶段不引入，用"文件协议 + 硬钩子"轻量编排。** 依据（全部来自本项目实测）：

1. **质量来自门槛，不来自角色扮演** —— 今天真正拦住错误的是 16 步校验、41 断言 e2e、pre-commit/pre-push 钩子和 make check，角色提示词本身不产生正确性。
2. **写权限要物理隔离，不能靠提示词** —— 实测中 agent 会越权并行改 tools/（当天手动拦截 3 次）；框架的"角色权限"仍是提示词层，真隔离靠 git 钩子 + 文件系统。
3. **调试黑盒风险** —— 连"工作目录不对"这类低级错误都重复出现过，框架再包一层调度会更难排查。
4. **成本/延迟** —— 单批修复已要 ~8 分钟；框架多 agent 对话轮次让 token 和时间翻倍，本项目（单人老板 + AI 串行深耕）用不上并行角色。
5. **已有替代** —— PLAN.md/RESEARCH.md/DECISIONS.md 当消息总线，钩子当调度纪律，老板当仲裁者，`scripts/kimi_review.sh` 当只读审查入口。

**何时重新评估**: ≥3 名真人并行开发、任务能拆成独立并行子任务（前后端分仓/多模块重写）时，先试 Claude Code 子代理 + PR 流程，仍不够再考虑框架。

## 2026-08-15 质量门槛（用户定，Claude 落地）

- `Makefile`: `make lint`（秒级语法门，py_compile + ruff 致命级[未装则跳过]）/ `make test`（e2e）/ `make validate`（16 步校验）/ `make check`（完整门槛）
- pre-commit：防泄露 + 暂存区含 .py 时自动 `make lint`
- pre-push：推送含 .py 改动时自动 `make check`（双回归红 = 拒推）
- **Claude 改完代码必须 `make check` 全绿，不过就修复或回滚；Kimi 不参与此循环**
- mypy 暂不进硬门槛：存量代码无类型标注，全量报错无信号；类型渐进补齐后再收（pytest 同理，tests/ 是自研 e2e 非 pytest 用例）
- 钩子源同步在 `scripts/hooks/*.sample`（重跑 setup-git-hooks.sh 不会倒退）

## 技术选型（补记，2026-08-15 整理；选型当时未留 ADR，理由从现状反推，待老板确认）

- **API 框架 FastAPI（而非 Flask）**：录入端字段多（报价/合同/发货动辄几十字段），FastAPI 的 pydantic 校验 + 自动 /docs 文档省掉手写参数检查；async 附件上传（api/main.py:365+）也顺手。Flask 也能做，但校验和文档全要自己拼。业务规则反正全在 tools/db_writer.py（框架无关），换框架成本可控——这是当初敢选的底气。
- **前端 React+AntD（vite dev + Nginx 生产容器）**：录入表单密集场景 AntD 的 Form/Table 现成；Nginx 反代 /api 后前端同源，浏览器直达 :8082。
- **查询端 Streamlit（而非 React 再做一套）**：老板/财务只读报表迭代快，SQL→表格/图一行代码；为此接受 8501 是只读例外（唯一写操作是关行复核按钮）。
- **校验器 SQLite 镜像（而非直查 MySQL）**：校验必须能离线跑（NAS 断网场景），且不能因校验事务锁业务表；代价是 SQLITE_SCHEMA 要跟 MySQL 保持四处同步（R7，已踩过坑）。
- **CSV 双轨（而非纯 DB）**：Excel 是业务员的母语，CSV 是离线兜底和外部协作格式；幂等靠业务编号自然键（R14）。
- **2026-08-01 取消零依赖原则**：核心校验脚本保持纯标准库（NAS/Windows 部署门槛），外围（streamlit/FastAPI/React）按需引入。

## 2026-08-15 分工协议（用户定）

- **Claude Code = 主工程师**: 读写所有代码、跑测试、操作数据库、Git 提交
- **Kimi = 研究员/审查员**: 只读代码；可写 `.research/`、`RESEARCH.md`；禁止改 `tools/` `api/` `frontend/` `sql/` `tests/` `scripts/`、禁改数据库、禁执行写操作
- 协作文件: `PLAN.md`(Claude 写) / `RESEARCH.md`(Kimi 写) / `DECISIONS.md`(双方追加) / `.research/`(Kimi 工作区)
- 本项目沿用既有 `docs/` 体系（AGENT_GUIDE.md / BUSINESS_RULES.md 等），Kimi 的审查类长文可进 docs/，短结论进 RESEARCH.md

## 2026-08-15 第①批收尾（Claude）

- 迁移 `2026-08-15_price_gap_approved.sql` 已执行于真实库；ALTER 曾卡 metadata lock（streamlit/api 长连接持有），`docker compose restart api streamlit` 释放后完成
- 教训: **改 tools/ 或 api/ 后必须 `docker compose restart api`** 才对真实容器生效（tools/ 是 ro 挂载，uvicorn 缓存旧模块）；此前第①批双回归的 41/41 是旧代码跑的，重启后复跑仍 41/41 才算数
- 迁移前教训: 先 ALTER 加列、再重启 api（顺序反了新代码会撞缺列）

## 2026-08-15 第②批分工调整（用户定）

- 第②批原派给 Kimi 执行，因分工协议改为 **Claude 亲自实现**，Kimi 事后只读复核
