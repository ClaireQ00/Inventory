# 系统架构（ARCHITECTURE.md）

> 外贸出口企业的进销存 + 报关单据 + 应收收款系统。
> 本文是全项目架构速览；更细的字段/规则见 `docs/DATA_MODEL.md`、`docs/BUSINESS_RULES.md`。

## 1. 部署拓扑（docker compose，4 个业务容器）

```
                        同事浏览器（内网）
                       /                \
              :8082 前端(React)      :8501 查询(Streamlit)
               Nginx 托管打包产物        只读报表/复核卡
               反代 /api → api:8000     (老板用)
                       \                /
                        :8000 api (FastAPI)
                         tools/ 只读挂载
                              |
                        :3306 db (MySQL 8.0)
                         22 张业务表
                              |
              data/csv/ (CSV 双轨，gitignored)
```

| 容器 | 端口 | 角色 | 说明 |
| --- | --- | --- | --- |
| inventory-frontend | 127.0.0.1:8082 | 录入端（业务员/保管员/生产调度） | React + AntD，Nginx 反代 /api |
| inventory-api | 127.0.0.1:8000 | 唯一写入入口 | FastAPI，复用 tools/ 规则层（ro 挂载，改代码需 `docker compose restart api`） |
| inventory-streamlit | 127.0.0.1:8501 | 只读查询端（老板/财务） | 全部 SELECT；唯一例外是首页"关行复核"按钮 |
| inventory-db | 内部 3306 | 唯一数据真相源 | MySQL 8.0；adminer/phpmyadmin 辅助 |

无登录系统（内网信任），替代方案是**留痕（audit_logs）+ 公示（8501 预警卡）**。

## 2. 模块依赖（核心原则：规则只写一份）

```
frontend/src/pages/*  ──HTTP──▶  api/main.py
                                     │
                                     ▼
                              tools/db_writer.py   ← 所有业务规则闸门（超发/低价/关行/汇率…）
                                     │                全部走 write_audit 留痕
                                     ▼
                              MySQL (inventory_db)

streamlit_app.py ──SELECT──▶ MySQL（只读例外：关行复核）

data/csv/*.csv ◀──▶ MySQL    双轨：CSV 可离线编辑，scripts/load-csv-to-db.sh 灌库，
                              tools/db_to_csv.py 导出；幂等锚点是业务编号自然键(R14)

local_validator.py：把 CSV 重建到 SQLite 镜像 → 16 步业务校验（不碰 MySQL）
```

- `api/main.py` 不写业务规则，只做参数转发 + 调 `tools/db_writer.py`
- 派生字段（体积/金额小计/amount_cny）在应用层算：`tools/csv_to_sql.py::DERIVED_RULES`
- 金额四件套铁律：amount + currency + exchange_rate + amount_cny 缺一报错

## 3. 数据流（一张发货单的一生）

```
报价(quotation) → 合同(sales_contract) → 生产入库(stock_in, 挂合同)
   → 调拨(transfer, 出入库同号软关联) → 发货单(delivery, 超发闸门+低价拦截+特批留痕)
   → 销售出库(stock_out, 挂发货单) → 报关(shipping, UCP600 ±5%)
   → 收款(receipt, 汇率月固定) → 提成(实发口径 R13)
每步都写 audit_logs；delivered_qty 由第 5 步校验回写（跑过校验才可信）
```

## 4. 校验体系（16 步，本地可跑）

```bash
bash scripts/run_local_validation.sh          # 真实数据
bash scripts/run_local_validation.sh --demo   # demo 假数据
python3 tests/demo_roleplay_test.py           # 四角色 13 场景 e2e（打真实 API）
```

改 schema 必须四处同步（R7）：`sql/01_schema.sql` / `SQLITE_SCHEMA` / `DERIVED_RULES`(派生时) / `sample/templates/`。

## 5. 已知架构决策（详见 docs/adr/）

| ADR | 决策 |
| --- | --- |
| 0001 | 派生字段走应用层，不用 MySQL GENERATED COLUMN |
| 0002 | 调拨用软关联（同号 transfer_ref），不建专表 |
| 0003 | 报价从 brief 一路派生到 formal |
| 0004 | 外键用业务编号（code），不用自增 id |
| 0005 | 重量快照链路 + R11 反算快照优先 |
