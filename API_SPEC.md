# 接口契约（API_SPEC.md）

> 前后端和 AI 都按这个来。实现：`api/main.py`（参数转发）→ `tools/db_writer.py`（业务规则）。
> 本文列全部端点 + 通用契约；逐参数细节以 `api/main.py` 为准，改接口必须同步本文。

## 通用约定

- Base URL：`http://127.0.0.1:8000`（前端经 Nginx 同源反代 `/api/*`，无需跨域）
- 请求/响应都是 JSON；写操作全部 POST
- 统一响应骨架：

```json
{ "ok": true, "errors": [], "doc_no": "DN20260815001", "warnings": ["..."], "...": "业务字段" }
```

- `errors` 非空 = 业务闸门拦截（超发/低价/状态不符…），此时**整单回滚，库里无残留**
- `warnings` 是放行但需人注意的提示（如"已列入 8501 复核清单"）
- 无鉴权（内网）；操作人靠 `operator` 字符串留痕进 `audit_logs`
- 单号格式：`QT`报价 / `SC`合同 / `DN`发货 / `IN`入库 / `OUT`出库 / `SH`报关 / `RC`收款 + 日期 + 流水

## 1. 单据录入（/api/docs/*，核心写入口）

| 方法 | 路径 | 说明 | 规则闸门（db_writer） |
| --- | --- | --- | --- |
| POST | `/api/docs/quotation` | 报价落库 | 公斤价系数定价；金额四件套 |
| POST | `/api/docs/contract` | 报价转合同 | 源报价置 converted，二次转拒 |
| POST | `/api/docs/delivery` | 发货单 | 超发拦截（qty 与 actual 双闸门）；低价拦截（高价未发完合同存在时 ERROR，`price_gap_approved+reason` 特批放行并落库）；draft/cancelled 合同拒发；FOR UPDATE 防并发双超发；状态联动 delivering/completed |
| POST | `/api/docs/stock-in` | 入库（purchase/production/adjust） | 采购必须挂 po_no；生产必须挂合同且物料在合同内 |
| POST | `/api/docs/stock-out` | 出库（sale/transfer/production/use） | 销售必须挂发货单且物料在发货单内；调拨必须同号 transfer_ref |
| POST | `/api/contracts/{no}/items/{item}/close` | 合同行关闭 | 原因必填；余量 >5% 进 8501 复核清单 |

> 🔜 规划中（审查修复第②批）：`POST /api/docs/delivery/actual`（装柜后回填实发数）、`POST /api/docs/delivery/cancel`（作废冲减）

## 2. 通用预览/插入（/api/preview, /api/insert）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/derive` | 行内派生字段计算（外径/体积/金额小计），纯计算不落库 |
| POST | `/api/preview` | 插入前预览（走 FIELD_RULES 校验，返回将被写入的行） |
| POST | `/api/insert` | 通用表插入（白名单 ALLOWED_TABLES：exchange_rates / receipts / products） |
| POST | `/api/validate` | 跑 16 步校验（读 CSV，只读） |

## 3. 下拉与选项（/api/options/*，全部 GET 只读）

`customers` `contracts` `contract-receipt-summary` `categories` `suggest-material-id` `brands` `field-values` `nominal-inches` `doc-header-terms` `warehouses` `exchange-rates` `suggest-customer-code`(R12 规则) `salespersons` `suggest-doc-no` `products-picker` `quotations` `deliveries` `purchase-orders` `contract-materials` `delivery-materials` `contract-stock-progress`

## 4. 档案

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST/GET/PUT | `/api/salespersons`(+`/{code}`) | 业务员档案 |
| POST | `/api/customers` | 客户建档（编号 R12：字母+4位数字） |

## 5. 辅料模块（/api/aux/*）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/api/aux/materials` | 辅料档案 |
| GET | `/api/aux/inventory` `moves` | 辅料库存/流水 |
| POST | `/api/aux/stock-in` `stock-out` | 辅料收发 |
| GET | `/api/aux/label-demand` | 标签纸需求测算（合同量 → 需求/库存/缺口） |
| GET/POST | `/api/aux/purchase-requests` | 辅料采购需求单 |
| POST | `/api/aux/materials/{aux_code}/attachments` | 附件上传（≤10MB，落 data/attachments，DB 存路径+sha256） |
| GET | `/api/aux/attachments(/{id}/download)` | 附件列表/下载 |

## 6. 健康

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | DB 连通探测（错误详情脱敏待第③批） |

## 变更纪律

1. 新增/修改端点：先改本文 → 再改 `api/main.py` + `tools/db_writer.py` → 补 `tests/demo_roleplay_test.py` 场景
2. 所有写操作必须走 `db_writer` 规则层 + `write_audit`，禁止 API 直连 SQL 写
3. 改完必须 `docker compose restart api`（tools/ 只读挂载，uvicorn 缓存旧模块）
