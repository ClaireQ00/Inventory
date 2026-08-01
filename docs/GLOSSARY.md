# 术语表 (Glossary)

> 本文件是项目的**业务术语单一事实源**。所有人(含 Claude)讨论业务时,词汇含义以本表为准。
> 来源:从 `CLAUDE.md`、4 个 skill 文件、`sql/01_schema.sql`、`docs/BUSINESS_FLOW.md` 反向提炼。
> 新增术语时请同步更新本表,并在 `BUSINESS_RULES.md` 补充相关规则。

## 1. 单据与流程术语

| 中文 | 英文 / 缩写 | 含义 | 对应数据表 |
| --- | --- | --- | --- |
| 询盘 | (Inquiry) | 客户邮件/WhatsApp 问价,纯口头或邮件 | (不落表) |
| 简要报价 | brief | 询盘后的**初版轻量报价**,只含"每卷重量 × 系数 × 数量"算出的单价/小计,不带贸易条款 | `quotations`(`quote_type='brief'`) + `quotation_items` |
| 形式发票 | PI / PROFORMA INVOICE | 客户确认简要报价后,发出的**正式报价单**,含完整贸易/付款/包装条款,作为承诺(报价)性质的单据 | `quotations`(`quote_type='formal'`) + `quotation_items` |
| 销售合同 | SC (Sales Contract) | 双方签字的合同,合同账的起点(从 formal 报价转单,回填 `converted_contract_no`) | `sales_contracts` + `sales_contract_items` |
| 采购单 | PO (Purchase Order) | 接单后向供应商采购的承诺单 | `purchase_orders` + `purchase_order_items` |
| 装箱计划 | Packing Plan | 装柜前 7-10 天的预估 | 不独立建表,反算核对字段挂在 `delivery_order_items` 上(`expected_unit_price`/`coeff_diff`/`coeff_check_status`),由第16步自动算(R11) |
| 发货单 | DO / DN (Delivery Order / Note) | 装柜前 1-2 天的内部发货指令(计划数) | `delivery_orders` + `delivery_order_items` |
| 入库单 | SI (Stock In) | 实际入库记录;`in_type='purchase'`=采购到货,`=transfer'`=调拨接收 | `stock_in` + `stock_in_items` |
| 出库单 | SO (Stock Out) | 实际出库记录;`out_type='sale'`=销售装柜,`=transfer'`=调拨发出 | `stock_out` + `stock_out_items` |
| 调拨 | Transfer | 仓库间挪货;**由配对的一对 SI+SO 共用同一个 `transfer_ref` 实现**,不走报关/收款 | `stock_in` + `stock_out`(配对) |
| 商业发票 | CI (Commercial Invoice) | 报关用的发票(结账小票) | `shipping_records` |
| 装箱单 | PL (Packing List) | 报关用的货物清单 | `shipping_record_items` |
| 报关单据 | SH (Shipping Records) | 装船时的实际报关记录,报关账的起点 | `shipping_records` + `shipping_record_items` |
| 提单 | B/L (Bill of Lading) | 物权凭证 | (字段级,落在 `shipping_records`) |
| 原产地证 | CO (Certificate of Origin) | 产地证明 | (字段级) |
| 贷记单 | CN (Credit Note) | 对账时处理两套账差异的差异单 | `credit_notes` |

**流程时序**:询盘 → brief → formal(PI) → SC → PO → Packing Plan → DO → SO → SH/CI/PL → CN(如有差异)。
**关键节点**:`delivery_orders`(合同账/计划)→ `shipping_records`(报关账/实际)之间允许 ±5% 偏差。
**平行流程**:仓库间调拨(Transfer)可发生于任意时刻,平行于主线,由一对 SI+SO 共用 `transfer_ref` 实现,不进报关/收款流程。

> **PI/正式报价术语澄清**(2026-07-29 修):本项目里 **PI = `quotations.quote_type='formal'` 的正式报价单**,**不是**独立表也不是销售合同。formal 含完整 5 个贸易条款字段(`trade_terms`/`port_loading`/`port_discharge`/`payment_term`/`packing`),brief 阶段条款留空待确认后补。转单时这些条款字段连同明细一起拷贝到 `sales_contracts`。
> **卖方公司(自己)** 不单独建表,通过 `suppliers.is_self=1` 在供应商表里标记(合同模板通过 `WHERE is_self=1` 调取卖方开票/收款信息)。

## 2. 单据状态

业务单据统一使用四态机:

| 状态 | 含义 |
| --- | --- |
| `draft` | 草稿,可改 |
| `confirmed` | 已确认,不可改业务字段 |
| `completed` | 已完成(闭环) |
| `cancelled` | 已作废 |

## 3. 金额与汇率术语

| 术语 | 含义 |
| --- | --- |
| **金额四件套** | 任何外币金额必须同时具备 `amount + currency + exchange_rate + amount_cny` 四个字段,缺一报错。详见 `BUSINESS_RULES.md §金额四件套铁律` |
| 记账本位币 | 人民币(CNY)。所有外币最终折算成 CNY 记账 |
| 默认币种 | USD。未指定币种时按 USD |
| 当期汇率 | 交易发生当月(由日期字段所在月决定)的固定汇率 |
| 汇兑损益 | 跨月交易中,合同月汇率与收款月汇率不同导致的差额 |
| 应收账款 | AR (Accounts Receivable),客户欠款 |
| AR aging | 应收账龄分析,按欠款时长分桶 |

**四张表涉及四件套**:`sales_contracts` / `shipping_records` / `credit_notes` / `receipts`。
**字段命名因表而异**(详见 `BUSINESS_RULES.md` 对照表),但语义一致。

## 4. 报关 / 贸易术语

| 中文 | 英文 / 缩写 | 含义 |
| --- | --- | --- |
| 短装 | Short Shipment | 实际装柜量 < 计划量 |
| 超装 | Over Shipment | 实际装柜量 > 计划量 |
| 唛头 | Shipping Mark | 包装外部的标识文字 |
| 毛重 | Gross Weight | 含包装的重量 |
| 净重 | Net Weight | 不含包装的重量 |
| 虚标 / 虚重 | Virtual Mark | 单据上写的数量/重量大于实际(报关红线) |
| 件数 | Package Qty | 包装件数 |
| CBM | Cubic Meter | 体积(立方米) |
| HS 编码 | HS Code | 海关商品编码 |
| 信用证 | L/C (Letter of Credit) | 银行担保付款方式 |
| UCP600 | — | 国际惯例,规定单据允许 ±5% 数量容差 |
| 交货条款 | FOB / CIF / EXW | 贸易术语,决定运费/风险归属 |

## 5. 收款术语

| 中文 | 英文 / 缩写 | 含义 |
| --- | --- | --- |
| 水单 | Bank Slip | 客户汇款凭证 |
| T/T | Telegraphic Transfer | 电汇,常见付款方式 |
| 收款 | Receipt | 客户实际打款到账 | `receipts` |
| 对账 | Reconciliation | 合同/报关应收与实际收款核对 |

## 6. 产品参数术语

| 术语 | 单位 | 含义 |
| --- | --- | --- |
| 物料编号 | — | `material_id`,企业内部唯一(如 M-001) |
| 内径 | mm | `inner_diameter`(英寸另存 `inner_diameter_inch`) |
| 外径 | mm | `outer_diameter = inner_diameter + thickness × 2` |
| 厚度 | mm | `thickness` |
| 长度 | m | `length` |
| 米重 | g/m | `weight_per_meter` |
| 单件重量 | kg | `weight` |
| 密度 | 无量纲 | `ρ`,由产品类别决定(线管固定 1.35) |
| 产品类别 | — | `product_category`:线管 / 钢丝管 / 塑筋管 / 水带 |

## 7. 系统约定术语

| 术语 | 含义 |
| --- | --- |
| 合同账 | 承诺值,给客户/财务看(源自 `sales_contracts` / `delivery_orders`) |
| 报关账 | 实际值,给海关/银行看(源自 `shipping_records`) |
| 派生字段 | 由其他字段自动计算的字段,默认走应用层(Python),不写 DB 生成列 |
| 四处同步 | 改 schema 必须同步:`sql/01_schema.sql` + `tools/local_validator.py::SQLITE_SCHEMA` + `tools/csv_to_sql.py::DERIVED_RULES` + `sample/templates/*_template.csv`（第 4 处由 `scripts/check-template-schema-sync.sh` 自动兜底；2026-07-30 升级，之前是三处） |

## 8. 报价术语

| 术语 | 含义 |
| --- | --- |
| 简要报价 | brief,内部快速算价,可多版本(对应'简要报价728.xlsx') |
| 正式报价 | QT form,formal,发给客户的正式报价合同(对应'QT form-709') |
| 报价系数 | price_coefficient,USD/KG 单价系数,不同管径组不同(如1.112) |
| 分组码 | group_code,同组管径共用一个报价系数 |
| 单卷重量 | weight_per_unit,KG,从 products.weight 带出可覆盖 |
| 报价参数表 | quotation_params,全局参数(汇率/默认币种/有效期) |
| 快照重量 | 报价明细 `weight_per_unit` 的语义:录入时从 `products.weight` 带出、可覆盖的行上副本。客户谈价改重量只改快照,主数据不动,别的报价/合同不受影响 |
| 归位 | formal/converted 阶段要求快照重量与物料编码一致:要么改回主数据值,要么克隆新建物料并换码。由 `check_quotations` 子校验 5 分阶段提醒(brief/draft 普通 WARN,formal/converted `[正式报价须归位]` 强提醒 WARN,不阻断但报告里无处遁形),见 ADR-0005 |
| 克隆建物料 | 用 `tools/clone_material.py` 以源物料为模板建新物料(几何派生列置空待重算),`--update-quote`/`--update-contract` 连带换码;合同已发货历史行自动跳过留痕(历史真相不动) |
