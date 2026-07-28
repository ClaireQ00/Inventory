---
name: payment-receivable
description: 进销存项目的应收收款 + 汇率折算规则集。当用户处理"客户打款"、"收款确认"、"水单"、"TT 到账"、"汇率折算"、"本币金额"、"对账"、"应收账款"、"AR aging"时使用此 skill。涉及 tools/local_validator.py 的 check_exchange_rates / check_receipts_vs_contract, 以及 sql/01_schema.sql 的 exchange_rates / receipts 两张表。注意: 涉及短装/贷记单请改用 trade-documents skill; 涉及产品参数请改用 product-params skill; 涉及行内派生字段请改用 derived-fields skill。
allowed-tools: Read, Grep, Glob, Bash(python3:*)
---

# 应收收款 + 汇率折算 · 完整规则集

## ⏱️ 5 分钟速查卡（没时间就只看这 3 条）

1. **铁律**：外币金额必须凑齐 **"四件套"**：`amount + currency + exchange_rate + amount_cny`，缺一个就 ERROR（影响 4 张表：`sales_contracts` / `shipping_records` / `credit_notes` / `receipts`）
2. **必看**：汇率**月固定**（每月 1 日录一次 `exchange_rates`），跨月交易用 `paid_date` 所在月的汇率，**不是合同月**
3. **闪人**：如果是短装 / 贷记单 → `trade-documents`；如果是密度 / 厚度 → `product-params`

---

## 谁会用这个 skill

| 角色 | 关心什么 | 重点看哪节 |
| --- | --- | --- |
| 财务经理 | 月初录汇率、确认收款、对账 | §2 汇率表机制、§3 收款流程、§3.3 对账校验 |
| 外贸业务经理 | 合同金额 / 客户打款跟没跟合同对齐 | §1 金额四件套、§3.3 对账校验 |
| 仓库保管员 | 报关后金额怎么跟收款衔接 | §1 金额四件套（理解 total_amount 怎么传到 receipts） |
| QA / 验收 | 跨月汇率变动 / 汇兑损益 | §5 完整示例（跨月场景） |

## 一句话总结

外贸出口的"钱流"分两步: **外币到账** + **当期汇率折算成人民币记账**, 凡是外币金额必须凑齐 **"四件套"** (amount + currency + exchange_rate + amount_cny), 折算误差 = 0。

---

## 1. "金额四件套"机制 (核心铁律)

**作用**: 让一笔外币交易在任何时候都能被精确还原成人民币, 不依赖"当时的汇率是多少"的记忆。

```
   ┌──── 外币金额 ────┐    ┌── 当期汇率 ──┐    ┌── 人民币金额 ──┐
   │  amount          │    │ exchange_rate│    │ amount_cny    │
   │  currency        │───▶│              │───▶│               │
   │  (USD/EUR/...)   │    │ (查汇率表)   │    │ (派生字段)    │
   └──────────────────┘    └──────────────┘    └───────────────┘
                            amount × rate = amount_cny
```

**字段命名约定**:

| 表 | amount | currency | exchange_rate | amount_cny |
| --- | --- | --- | --- | --- |
| `sales_contracts` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` |
| `shipping_records` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` |
| `credit_notes` | `diff_amount` | `currency` | `exchange_rate` | `diff_amount_cny` |
| `receipts` | `amount` | `currency` | `exchange_rate` | `amount_cny` |

**派生规则**: `tools/csv_to_sql.py::DERIVED_RULES[<表>][<amount_cny>]` 自动算, 容差 0.01。

**类比**: 这就像超市小票同时印"美元价 + 汇率 + 人民币价", 你任何时候看小票都能知道当时折算了多少人民币, 不用再去翻汇率历史。

---

## 2. 汇率表机制 (月固定)

**业务约定** (2026-07-28 客户确认):
- **每月 1 日**记录一次当月固定汇率
- 同一币种同月只有一条记录 (UNIQUE KEY `uk_currency_effective`)
- 整月所有交易都用这一条汇率折算

**表**: `exchange_rates`
```sql
currency        VARCHAR(3)      -- 币种 ISO 码, 如 USD/EUR/JPY/HKD
rate_to_cny     DECIMAL(10,4)   -- 兑人民币汇率
effective_date  DATE            -- 生效日 (一般是月初 1 号)
source          VARCHAR(32)     -- manual/boc(中行)/pboc(人行)
```

**查询规则** (校验函数 `check_exchange_rates`, 步骤 11/12):

```
对每个用到外币的业务记录 (合同/报关/收款), 取它当月的币种:
  ├─ 找到当月汇率 → OK
  ├─ 没找到 → ERROR "缺 X 月 Y 币种汇率, 请补录"
  └─ 汇率字段为 0 或 NULL → ERROR "汇率异常"
```

**类比**: 每月 1 号你定一个"换算系数贴在墙上", 这一个月所有的外币交易都看这张表折算, 月底结账时不会因为汇率波动扯皮。

---

## 3. 收款单 (receipts) 流程

### 3.1 字段一览

| 字段 | 含义 | 必填 |
| --- | --- | --- |
| `receipt_no` | 收款单号 (RC 开头) | ✅ |
| `customer_id` | 哪个客户打的钱 | ✅ |
| `contract_id` | 关联合同 (可空, 多合同合并付款时) | — |
| `shipping_id` | 关联报关单 (可空) | — |
| `delivery_id` | 关联发货单 (可空) | — |
| `amount` | 外币到账金额 | ✅ |
| `currency` | 币种, 默认 USD | ✅ |
| `exchange_rate` | 当期汇率 (按 paid_date 查汇率表) | ✅ |
| `amount_cny` | 人民币金额 (派生 = amount × rate) | 派生 |
| `paid_date` | 客户实际到账日 | ✅ |
| `pay_method` | T/T / L/C / D/P / D/A / other | ✅ |
| `bank_ref` | 银行水单号 | — |
| `status` | draft / confirmed / cancelled | ✅ |

### 3.2 状态机

```
   draft (草稿, 财务录入)
      │
      │ ① 看到水单 / 银行确认到账
      ▼
   confirmed (已确认, 已参与对账)
      │
      │ ② 走错账 / 重复录入
      ▼
   cancelled (作废, 不参与对账)
```

**关键规则**: 只有 `status='confirmed'` 的收款才会被 `check_receipts_vs_contract` 拿来跟合同金额比对。

### 3.3 对账校验 (步骤 12/12)

**校验函数**: `check_receipts_vs_contract()`

```
对每个 sales_contract:
  total_receipts = SUM(receipts.amount WHERE contract_id=X AND status='confirmed')

  ├─ total_receipts > contract.total_amount × 1.05  → ERROR "超收, 可能录错"
  ├─ total_receipts < contract.total_amount × 0.95  → WARN  "未收齐, 催款"
  ├─ receipts.currency != contract.currency         → ERROR "币种不一致"
  └─ exchange_rate 为 0                              → ERROR "未折算汇率"
```

**±5% 容差来源**: 跟 UCP600 短装容差对齐, 客户少发 5% 货或少付 5% 钱都算合理误差。

---

## 4. 业务名词词典 (新手友好版)

| 中文 | 英文/缩写 | 含义 | 类比 |
| --- | --- | --- | --- |
| 水单 | Bank Slip | 银行到账通知 | 微信收款截图 |
| T/T | Telegraphic Transfer | 电汇 | 银行转账 |
| L/C | Letter of Credit | 信用证 | 支付宝担保交易 |
| D/P | Documents against Payment | 付款交单 | 货到付款 (银行版) |
| D/A | Documents against Acceptance | 承兑交单 | 先签字后付款 |
| 应收账款 | AR (Accounts Receivable) | 客户欠我们的钱 | 朋友欠的钱本 |
| 本位币 | Base Currency | 记账用的基准币种 (本项目=CNY) | 中国人算账用人民币 |
| 汇兑损益 | Forex Gain/Loss | 汇率变动产生的差额 | 兑换外币时多收/少收的钱 |

---

## 5. 完整收款流程示例

**场景**: 客户 1 (印尼大雄) 合同 SC20260720001 金额 USD 30000, T/T 分两次到账。

**步骤**:

```csv
# 1. 月初录汇率 (USD/2026-07)
exchange_rates:
  id=1, currency=USD, rate_to_cny=7.15, effective_date=2026-07-01

# 2. 第一船装柜报关 (USD 4500)
shipping_records:
  id=1, total_amount=4500, currency=USD, exchange_rate=7.15, total_amount_cny=32175

# 3. 客户打第一笔款 (USD 4500, 跟报关单对齐)
receipts:
  id=1, receipt_no=RC20260726001, customer_id=1, contract_id=1,
  shipping_id=1, amount=4500, currency=USD, exchange_rate=7.15,
  amount_cny=32175, paid_date=2026-07-26, pay_method=T/T,
  bank_ref=BK-001, status=confirmed

# 4. 客户打第二笔尾款 (USD 25500)
receipts:
  id=2, receipt_no=RC20260810001, customer_id=1, contract_id=1,
  amount=25500, currency=USD, exchange_rate=7.18,  # 注意: 跨月了, 8月汇率变了
  amount_cny=183090, paid_date=2026-08-10, pay_method=T/T,
  bank_ref=BK-002, status=confirmed
```

**对账结果**:
- 合同外币: USD 30000
- 收款外币: 4500 + 25500 = USD 30000 ✓ (币种对齐)
- 合同人民币: 30000 × 7.15 = 214500
- 收款人民币: 32175 + 183090 = 215265 (因为 8 月汇率变动, 多收了 765 CNY)
- 差额: 765 / 214500 = 0.36% < 5%, 不报警 ✓

**这个 765 元差额 = 汇兑收益**, 第 2 阶段会在月末自动结转到损益表 (本阶段先记着, 不做结转)。

---

## 6. 给 Claude 自己的提醒

- ✅ **金额四件套是铁律**: 凡是外币金额必须同时有 amount + currency + exchange_rate + amount_cny 四个字段
- ✅ **汇率表月固定**: 每月 1 日录一次, 整月所有交易都用这条
- ✅ **跨月交易**: 用 `paid_date` 所在月的汇率, 不是合同月
- ✅ **状态过滤**: 对账只看 `confirmed` 收款, `draft` 不参与
- ✅ **派生字段**: `amount_cny` 永远由 csv_to_sql.py 自动算, 不要手填
- ❌ **不要**把人民币和外币混在一个字段 (老代码 total_amount_usd 已废, 改用 total_amount + currency)
- ❌ **不要**用"当天实时汇率"折算, 本项目只用月固定汇率 (跟客户 2026-07-28 确认)
- ❌ **不要**让 `exchange_rate` 留 0 或 NULL, 业务上是数据缺陷
- ➡️ 涉及短装/贷记单 → `trade-documents` skill
- ➡️ 涉及密度/厚度 → `product-params` skill
- ➡️ 涉及体积/外径派生 → `derived-fields` skill

---

## 7. 第 2 阶段规划 (本阶段不做)

以下功能在本项目第 1 阶段不实现, 留接口位置:

| 功能 | 涉及表 | 何时做 |
| --- | --- | --- |
| 供应商付款 (AP) | 新建 `supplier_payments` 表 | 第 2 阶段 |
| 多合同合并收款分配 | `receipts` 加 `allocations` 子表 | 第 2 阶段 |
| 汇兑损益月末结转 | `forex_settlements` 表 + 月末脚本 | 第 2 阶段 |
| 应收账龄 (AR Aging) | 视图 `v_ar_aging` | 第 2 阶段 |
| 信用证单证管理 | `lc_documents` 表 | 第 2 阶段 |
| 审计日志逻辑 | `audit_logs` 表已建, 触发器未做 | 第 2 阶段 |

---

## 🔗 跨 skill 协作场景

### 场景 1：短装退款折算（trade-documents → payment-receivable）

**触发**：装柜短装，客户要求退款（不补发）

**协作顺序**：
1. 先用 **trade-documents** 创建 `credit_notes`：`diff_qty=5, diff_amount=1000 USD, resolution=refund`
2. 再用 **payment-receivable**（本 skill）把 `diff_amount` 折算 CNY：`diff_amount_cny = 1000 × 7.15 = 7150 CNY`，并在收款对账时减掉这笔

**关键**：credit_notes 的 `diff_amount_cny` 是金额四件套的一部分，必须由 `DERIVED_RULES` 自动算，不要手填。

### 场景 2：报关后收款对账（trade-documents → payment-receivable）

**触发**：装船报关，客户 T/T 付款到账

**协作顺序**：
1. trade-documents 出 `shipping_records`（`total_amount` 外币 + 汇率 + `total_amount_cny`）
2. payment-receivable（本 skill）收 `receipts`，按 `paid_date` 所在月查汇率，跟合同 / 报关单对账
3. 对账规则：`SUM(receipts.amount) vs sales_contracts.total_amount`，±5% 容差（跟 UCP600 对齐）

**举例**：合同 USD 30000，分两笔收款
- 7 月装船 USD 4500（rate 7.15）→ receipts #1
- 8 月尾款 USD 25500（rate 7.18，跨月了）→ receipts #2
- 合计 USD 30000 ✓；CNY 因为 8 月汇率变动，多收 765 元 = 汇兑收益

### 场景 3：跨月汇率衔接（payment-receivable 内部）

**触发**：合同在 7 月签，但客户 8 月才付款

**关键点**：用 **`paid_date` 所在月**的汇率，不是合同月。8 月付款就用 8 月 1 日的汇率表记录。

---

## 8. 相关文件索引

| 文件 | 作用 |
| --- | --- |
| `sql/01_schema.sql` | `exchange_rates` / `receipts` 表定义; sales_contracts/shipping_records/credit_notes 加金额四件套字段 |
| `tools/local_validator.py` | `check_exchange_rates` (步骤 11); `check_receipts_vs_contract` (步骤 12); SQLITE_SCHEMA 同步新增表 |
| `tools/csv_to_sql.py` | `DERIVED_RULES["receipts"]["amount_cny"]`; 4 个表的 `*_cny` 派生规则 |
| `sample/templates/exchange_rates_template.csv` | 汇率录入模板 |
| `sample/templates/receipts_template.csv` | 收款录入模板 |
| `data/csv/demo_runtime/exchange_rates.csv` | demo 数据 |
| `data/csv/demo_runtime/receipts.csv` | demo 数据 |
