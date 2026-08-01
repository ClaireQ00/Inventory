# 业务规则库 (Business Rules)

> 本文件是项目的**业务规则单一事实源**。所有硬性业务规则集中在此,代码实现必须遵循。
> 与 `CLAUDE.md`(对话式约定)的区别:本文件是结构化、可追溯的正式规则库,`CLAUDE.md` 仅做路由提示。
> 规则来源:`CLAUDE.md`、4 个 skill 文件、`sql/01_schema.sql` 字段注释、客户确认(标注日期)。

---

## R1. 金额四件套铁律 ⭐核心 (2026-07-28 客户确认)

**规则**:凡是外币金额,必须同时具备四个字段,缺一个即报错(ERROR):

```
amount + currency + exchange_rate + amount_cny
```

### 字段命名对照表(因表而异,语义一致)

| 数据表 | amount | currency | exchange_rate | amount_cny |
| --- | --- | --- | --- | --- |
| `sales_contracts` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` |
| `shipping_records` | `total_amount` | `currency` | `exchange_rate` | `total_amount_cny` |
| `credit_notes` | `diff_amount` | `currency` | `exchange_rate` | `diff_amount_cny` |
| `receipts` | `amount` | `currency` | `exchange_rate` | `amount_cny` |

### 派生关系

- `amount_cny = amount × exchange_rate`(容差 0.01)
- `amount_cny` 是**派生字段**,由 `tools/csv_to_sql.py::DERIVED_RULES[<表>][<amount_cny>]` 自动算,**不要手填**
- 影响表:`sales_contracts` / `shipping_records` / `credit_notes` / `receipts`

### 默认值

- **币种默认 USD**,记账本位币是 CNY
- 不允许出现"只有 amount 没有 currency"的数据

---

## R2. 汇率月固定规则 (2026-07-28 客户确认)

**规则**:汇率按"月"固定,每月 1 日录一次,整月用同一条。

| 项 | 规定 |
| --- | --- |
| 录入时机 | 每月 1 日录一次当月固定汇率 |
| 表 | `exchange_rates` |
| 唯一约束 | `UNIQUE KEY uk_currency_effective (currency, effective_date)` —— 同币种同月仅一条 |
| 数据来源字段 | `source`:manual / boc(中行) / pboc(人行) |
| 字段 | `currency` / `rate_to_cny` / `effective_date` |

### 跨月交易取汇率规则(关键)

交易用**该交易日期所在月**的汇率,**不是合同月**:

| 表 | 决定月份的日期字段 |
| --- | --- |
| `sales_contracts` | 签约日(contract date) |
| `shipping_records` | `shipping_date`(报关/装船日) |
| `receipts` | `paid_date`(收款到账日) |

> ⚠️ 同一笔合同,签约、报关、收款可能跨三个月,各自用各自月份的汇率 → 产生**汇兑损益**,这是正常现象,不要"统一"。

### 校验

`tools/local_validator.py::check_exchange_rates`(步骤 12/16):对每个用外币的业务记录,查其当月币种汇率,缺则报 ERROR "缺 X 月 Y 币种汇率,请补录"。

---

## R3. 两套账与 ±5% 容差规则 (UCP600)

**规则**:外贸订单并行存在两套账,允许 ±5% 差异,**不要试图统一**,差异用 `credit_note` 衔接。

```
合同账(承诺值)               报关账(实际值)
sales_contracts              shipping_records
delivery_orders              shipping_record_items
   │                              │
   └──── 允许 ±5% ────────────────┘
                │
        差异超 5% → credit_notes 闭环
```

- **合同账**:给客户/财务看的承诺值
- **报关账**:给海关/银行看的实际值
- **±5% 来源**:UCP600 国际惯例(信用证项下数量容差)
- **超出 5%** 的差异,通过 `credit_notes`(贷记单)处理,不允许直接改合同或报关数据

### 报关必填字段(`shipping_record_items`)

唛头 / 毛重 / 净重 / 件数 / CBM —— 缺一不可报关。

### 校验

`tools/local_validator.py::check_shipping_vs_delivery` / `check_credit_notes_balance`。

---

## R3.5. 多仓库调拨配对铁律 (2026-07-29)

**规则**:仓库间挪货,必须用一对配对的出入库单 + 同一个 `transfer_ref`,且每个物料的**出库总量 = 入库总量**。

```
stock_out (out_type='transfer', transfer_ref='TR20260729001', warehouse=源仓)
stock_in  (in_type='transfer',  transfer_ref='TR20260729001', warehouse=目标仓)
                                  ↑ 同一个号串起来
                                  ↓
              check_transfer_pairs 聚合两边数量对比, 差额非 0 报 ERROR
```

**类比**:从 A 银行卡转 100 到 B 银行卡,记账必是两笔:A 卡 -100、B 卡 +100,靠同一个转账流水号串起来对账。中途丢钱或凭空多钱都要立刻发现。

### 字段(`stock_in` / `stock_out` 共有)

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `in_type` / `out_type` | ENUM | 已含 `'transfer'` 枚举值 |
| `transfer_ref` | VARCHAR(32) | 调拨关联号,**两边填同一个值**,如 `TR20260729001` |

### 校验

`tools/local_validator.py::check_transfer_pairs`(步骤 14/16):

- 出库总量 ≠ 入库总量 → **ERROR**(差额、漏录或调拨在途)
- 只有一边(只有出库没入库,或反之)→ **WARN**(在途、漏录或方向录错)

### 配套规则(本次新增的其他改动)

- **负库存允许但报警**:`check_stock_out_vs_inventory`(步骤 6/16)从 ERROR 降级为 WARN。理由:外贸调拨常"先做后补",允许 source 仓暂时透支,后续补货即可。
- **调拨不走外贸单据流程**:不产生报关单、不触发 UCP600、不涉及收款/汇率/credit_note。`trade-documents` / `payment-receivable` skill 不管调拨。

---

## R4. 产品参数计算规则

**规则**:所有重量计算从**密度公式**出发,不要为不同产品类别写多套公式。

### 密度公式(按产品大类,2026-08-01 老板确认)

| 产品大类 | 密度 ρ | 代码位置 |
| --- | --- | --- |
| 线管 | 固定 `1.35` | `DENSITY_RULES` |
| 水带 | 固定 `1.35`(与线管相同) | `DENSITY_RULES` |
| 钢丝管 | `inner_diameter × 0.003 + 1.46` | `DENSITY_RULES` |
| 复合管 | `inner_diameter × 0.003 + 1.46`(与钢丝管相同) | `DENSITY_RULES` |
| 塑筋管 | TODO 待客户补充 | — |

> `products.product_category` 存客户原始类别(70+ 种,如"无味钢丝管""白复合防静电""钩编管"),
> 密度计算前先用 `tools/csv_to_sql.py::CATEGORY_ALIASES` 映射成上表 4 个大类
> (含"钢丝"→钢丝管、含"复合"→复合管、含"水带"→水带,其余已梳理类别→线管)。
>
> **手填值保留约定(2026-08-01)**:products 的 厚度/米重/单重 手填值与密度公式偏差 >5% 时,
> **保留客户手填值不改**,反向校验降级为 WARN,偏差提示写入 `remark`。

### 统一公式链

```
密度 ρ (由 product_category 决定)
   ▼
理论米重(g/m) = (内径 + 厚度) × 厚度 × 3.14 × ρ
   ▼
理论单件重量(kg) = 理论米重 × 长度 / 1000
```

- 外径 = 内径 + 厚度 × 2(单位 mm)
- 单位约定:内径/厚度/外径 mm,长度 m,米重 g/m,单件重量 kg,密度无量纲

### 厚度反推三条路径(优先级 A > B > C)

当客户未提供厚度时,按优先级依次尝试:

| 路径 | 已知条件 | 公式 | 精度 |
| --- | --- | --- | --- |
| **A(优先)** | 外径 + 内径 | `厚度 = (外径 - 内径) / 2` | 100% 精确(纯几何) |
| B | 内径 + 米重 + 密度 | 解密度方程 | 依赖密度准确度 |
| C | 内径 + 单重 + 长度 | 反推 | 依赖密度 |

代码:`tools/csv_to_sql.py::calc_theoretical_thickness`。

### 重量容差(5%)

米重 / 单件重量与理论值允许 **±5%** 偏差(客户会"上下浮动"确认),按**客户给定的值**保存,不强行覆盖。校验:`check_cross_field_consistency`。

---

## R5. 行内派生字段规则

**规则**:外径、体积、金额小计等行内派生字段由其他字段自动算。

- 唯一例外(走 DB):`delivery_order_items.short_qty`(纯行内计算)
- 其余派生默认走**应用层**(Python 算),不用 MySQL `GENERATED COLUMN`
- 代码:`tools/csv_to_sql.py::DERIVED_RULES`

> ⚠️ **主表 `total_volume` 不是 DERIVED_RULES**,是**应用层汇总字段**(同 `total_amount` 模式):4 张主表(`quotations` / `sales_contracts` / `purchase_orders` / `delivery_orders`)的 `total_volume` = Σ 各自明细的 `volume_subtotal`(或 `quotation_items.total_volume`),WARN 级校验(容差 0.01)。**跟 `shipping_records.total_cbm`(装柜后报关真实 CBM)是两个概念**——前者是给客户看的展示统计,后者是要交海关的实际数。

> 路由约定:外径/体积/金额小计 → `derived-fields` skill;密度/厚度/米重 → `product-params` skill。

---

## R6. 数据即数据,不硬编码规则 ⭐

**规则**:客户 / 币种 / 口岸 / 产品品类**都是数据,不是硬编码**。

- 当前联调样本:印尼客户 Q025、PVC 线管 —— **这只是数据,不是系统边界**
- 加新品类:在 `tools/csv_to_sql.py::DENSITY_RULES` 加一条公式即可,**不要新建 skill**
- 加新币种/口岸/客户:加数据,不改代码

> 违反本规则的表现:代码里出现 `if 印尼` / `if PVC` 这类硬编码分支 —— 应消除。

---

## R7. Schema 四处同步规则 ⭐

**规则**:修改 schema 时,必须同步以下四处,漏一处校验即对不上:

1. `sql/01_schema.sql` —— MySQL 真表
2. `tools/local_validator.py::SQLITE_SCHEMA` —— SQLite 镜像
3. `tools/csv_to_sql.py::DERIVED_RULES` —— 派生字段(仅当字段是派生时)
4. `sample/templates/<表名>_template.csv` —— CSV 模板表头(加字段必须同步表头列,否则录入时列错位)

> 第 4 处是 2026-07-30 真实数据试用踩坑后补的(当时 customers 表加了 `brand_name`/`company_profiles`/`billing_profiles` 3 个字段但模板没同步,导致 CSV 列错位)。
> 自动检测:`bash scripts/check-template-schema-sync.sh`(已集成进 `run_local_validation.sh` 第 2b 步,WARN 不阻断)。

---

## R8. 隐私与数据隔离规则

**规则**:真实敏感数据不进仓库。

- `.gitignore` 已忽略:`data/` / `private/` / `.env` / `.env.*`
- 真实数据(客户、供应商、合同、订单、价格)只存本地 `data/` 或 `private/`
- 仓库内只放:模板(`sample/`)、demo 假数据、结构、脚本
- 校验:`bash scripts/check-sensitive-data.sh`
- 改动前先跑:`git status --short` + `bash scripts/check-sensitive-data.sh`

---

## R9. 自检门禁规则

**规则**:任何改动,16 步自检全过才算改对。

```bash
bash scripts/run_local_validation.sh           # 真实数据
bash scripts/run_local_validation.sh --demo    # demo 假数据
```

CI 同样以此为门禁(`scripts/ci.sh` / `.github/workflows/ci.yml`)。

---

## R10. 报价定价铁律 (2026-07-29 客户确认)

**规则**:报价单价 = 单卷重量(KG) × 报价系数(USD/KG)。

- **报价系数**:不同管径组用不同系数(如实际数据 1.112/1.065/1.075 USD/KG),存于 quotation_items.price_coefficient
- **分组**:同一报价单内可有多组系数,用 group_code 区分(如 'A组-1.112')
- **单卷重量**:从 products.weight 带出,可在报价明细里覆盖(weight_per_unit)
- **派生关系**(全部走 DERIVED_RULES,不要手填):
  - total_weight(总重KG) = weight_per_unit × quantity
  - unit_price(单卷价) = weight_per_unit × price_coefficient
  - subtotal(小计) = unit_price × quantity
  - total_volume(总体积) = volume × quantity(volume 复用 inventory 体积公式)
- **报价主表金额四件套**:total_amount = Σ subtotal,仍遵循 R1(currency/exchange_rate/total_amount_cny)
- **报价主表 total_volume**:**应用层汇总**(同 total_amount 模式,不是 DERIVED_RULES)= Σ quotation_items.total_volume。同字段也存在于 `sales_contracts` / `purchase_orders` / `delivery_orders` 主表(各自 = Σ 明细 volume_subtotal)。**展示用统计**(给客户看),WARN 级校验,跟 `shipping_records.total_cbm` 报关实际数是两个概念
- **派生关系**:正式 QT form(quote_type='formal')从简要报价(quote_type='brief')派生,parent_quote_no 指向来源
- **转换**:报价转销售合同后,status='converted',converted_contract_no 回填
- 影响表:quotation_params / quotations / quotation_items(新增 3 表)

---

## R11. Packing Plan 公斤价反算铁律 (2026-07-29 客户确认)

**业务背景**:报价按公斤系数(USD/KG)定价,但后续进销存为避免小数点累积误差,**全部按件价走**。
制作发货单(Packing Plan)时,要用"报价单的公斤价"反算/正算核对,确保合同单价与报价基准一致。

**正算公式(丙方案,客户 2026-07-29 确认;2026-07-31 修正单位)**:
```
应等于的合同单价(原币种/件) = 报价系数(原币/KG) × 单重(KG/件)
```

- **报价系数**:取 `quotation_items.price_coefficient`(通过 `material_id` 反查最近一条非 reject 报价)
- **单重**:取 `products.weight`(主数据唯一来源,不一致就加新物料,不在单据里改)
- **实际合同单价**:`sales_contract_items.unit_price`(原币种/件,R10 顺带澄清注释)

> ⚠ 2026-07-31 修正:原公式误乘 `sales_contracts.exchange_rate`,把"原币/件"算成了"人民币/件",
> 与 `unit_price`(原币种/件)单位不匹配,真实数据 Q025 跑出 11 条 WARN 暴露(见 `docs/TASKS.md` 坑 6)。
> 报价单价 = 报价系数 × 单重(原币),汇率只用于金额四件套折算,不参与件价反算。

**差异判定**:
```
差异 = 实际合同单价 − 应等于的合同单价
|差异| ≤ 0.01   →  pass   (合同单价按 2 位小数报价, 0.01 覆盖最大舍入误差 0.005)
|差异| > 0.01   →  warn   (超差只警告不报错, 业务上确认正常)
缺任一字段        →  pending (提示补数据)
```

**会计对应**:标准成本差异分析。报价 = 标准成本,合同 = 实际成本,允许精度损失内的微小差异。

**落点**:不新建 Packing Plan 表(项目刻意不落表),复用 `delivery_order_items` 加 3 个反算字段:
- `expected_unit_price` DECIMAL(12,4) — 正算应等于的合同单价
- `coeff_diff` DECIMAL(10,4) — 差异
- `coeff_check_status` VARCHAR(16) — pass/warn/pending

**校验**:`check_packing_coefficient` 第 16 步(`tools/local_validator.py`)。跨表派生不在 `DERIVED_RULES` 做(超出单行能力),由校验阶段 JOIN 计算并回写。

**为什么用合同单价不用报关单价**:核对的是"承诺价层面的偏离",报关单价是装柜后的实际成交价,时点偏晚。

**Packing Plan 不新建独立表的理由**:它本质是发货单的"前置草稿",时序紧贴 DO,独立建表会让流程节点重复;字段直接挂在 `delivery_order_items` 上更内聚。

- 影响表:`delivery_order_items`(加 3 字段)
- 关联铁律:R1 金额四件套、R10 报价定价

---

## 规则变更记录

| 日期 | 规则 | 变更 |
| --- | --- | --- |
| 2026-07-28 | R1 金额四件套 | 客户确认,确立铁律 |
| 2026-07-28 | R2 汇率月固定 | 客户确认 |
| 2026-07-29 | 本规则库 | 从 CLAUDE.md / skills 反向提炼,结构化集中 |
| 2026-07-29 | R3.5 调拨配对 | 新增 `transfer_ref` 字段 + `check_transfer_pairs` 第 13 步;负库存校验由 ERROR 降级为 WARN。自检从 12 步增至 13 步 |
| 2026-07-29 | R10 报价定价 | 新增报价模块,KG×系数定价 + 简要报价→QT form→PI 派生。新增 `check_quotations` 第 14 步,自检从 13 步增至 14 步 |
| 2026-07-29 | R11 Packing Plan 反算 | 客户确认方案 A(复用 delivery_order_items)+ 丙方案(正算应等于的合同单价)。新增 `check_packing_coefficient` 第 15 步,自检从 14 步增至 15 步;同步澄清 `sales_contract_items.unit_price` 为"原币种/件" |
| 2026-07-30 | 主表 total_volume 字段 | 4 张主表(quotations/sales_contracts/purchase_orders/delivery_orders)新增 `total_volume` 字段(DECIMAL(10,2),展示用统计 = Σ 明细 volume_subtotal/quotation_items.total_volume)。新增 `check_delivery_order_volume` 第 9 步,自检从 15 步增至 16 步。**与 `shipping_records.total_cbm` 是两个概念**——前者是给客户看的展示统计,后者是装柜后报关真实 CBM。校验用 WARN 级(容差 0.01),不阻断业务流程 |
| 2026-07-31 | R11 反算公式修正 | 真实数据 Q025 跑出 11 条 WARN:公式误乘汇率导致单位不匹配(原币 vs 人民币)。修正为 `报价系数×单重`,容差 0.001→0.01(2 位小数报价);demo 合同件价同步修正 |
