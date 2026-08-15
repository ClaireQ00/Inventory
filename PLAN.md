# 当前迭代计划（Claude 写，Kimi 读）

> 来源: docs/REVIEW_BY_CLAUDE_CODE.md（Claude 独立审查）+ 附2（Kimi 逐条核对，23 成立 / 1 误判撤销）
> 分工: 按 DECISIONS.md 分工协议，Claude 实现全部代码，Kimi 只读复核
> 每批完成后跑双回归: `python3 tests/demo_roleplay_test.py` + `bash scripts/run_local_validation.sh --demo`

## 第①批「钱和账」— ✅ 已完成 (2026-08-15)

| Commit | 条目 | 内容 |
| --- | --- | --- |
| 9aad257 | 🔴-3 | 删 check_delivery_vs_contract 孤立 LEFT JOIN（SUM 被 K 倍放大） |
| 792928c | 🔴-2 | actual_quantity 后端闸门：显式传必须 1 ≤ actual ≤ pending |
| a46ffc2 | 🔴-1 | price_gap_approved/reason 落库，四处同步 + 迁移 SQL + 审计带 reason |
| e6a7e52 | 🟡-9 | SQLITE_SCHEMA 四张明细表补 UNIQUE 自然键 |
| e1359c3 | 🟡-5 | create_delivery 读合同行 FOR UPDATE |
| 384e821 | 🟡-6 | draft 合同拒发，仅 confirmed/delivering/completed 可发 |

- 迁移 `sql/migrations/2026-08-15_price_gap_approved.sql` 已在真实库执行（ALTER 遇 MDL 等待，重启 api/streamlit 后完成）
- api / streamlit 容器已重启加载新代码
- 双回归: demo_roleplay_test 41/41 ✓，local_validation --demo 16 步 0 ERROR ✓

## 第②批「流程闭环」— 🔜 进行中（Claude 实现）

1. [🔴-4] actual_quantity 回填通道
   - db_writer 新增 `update_delivery_actual(delivery_no, items, operator)`：按行回填 actual_quantity，重算 short_qty = quantity - actual，按差额修正 sales_contract_items.delivered_qty；FOR UPDATE；cancelled 单拒改；审计留痕（old_values 记旧值）
   - api 加路由（POST /api/docs/delivery/actual）
   - 前端 8082 保管员回填入口
2. [🟡-7] `cancel_delivery(delivery_no, reason, operator)`
   - 置 cancelled + 反向冲减 delivered_qty + 合同状态重算（全回冲退回 confirmed）+ 审计
   - 仅 draft/confirmed 可作废（shipped 后涉及报关不许）
   - API 路由 + 前端作废按钮
3. [🟡-13] 销售出库累计校验
   - 按 (delivery_no, material_id)：Σ历史出库 + 本次 ≤ 发货实发数（actual>0 取 actual 否则 quantity，R13 口径），超出 ERROR
4. [🟡-8] 汇率月固定（R2）强实现
   - check_exchange_rates 逐表按交易月核对（contract→sign_date / shipping→shipping_date / receipt→paid_date），缺月即 ERROR
   - 录入端 lookup_exchange_rate 借用非当月汇率时升级为前端可见 WARN

注意: tests 打真实 API 容器（tools/ ro 挂载），改完 db_writer/api 必须 `docker compose restart api` 再跑回归；demo_roleplay_test 补第②批场景（Z9999 测试段，跑完自动清理）。

## 第③批「加固」— ⏳ 待做

- [🟡-11] CORS 收紧为前端两个源
- [🟡-12] 附件上传流式限长 + aux_code 白名单
- [🔵-16] 审计 record_id 指错表（lastrowid 取在明细插入后）
- [🔵-24] 关行留痕 stamp 截断吃掉盖章内容
- 其余 🔵（15/17/18/19/20/21/22/23）顺手修

## Kimi 复核任务（只读）

每批完成后 Kimi 复核 diff 是否贴合 docs/REVIEW_BY_CLAUDE_CODE.md 对应条目的修法建议，结论追加到 RESEARCH.md。
