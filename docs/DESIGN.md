# 技术设计文档 (Technical Design)

> 本文件是**设计决策记录**,核心回答"**为什么这么设计**",不是"系统长什么样"。
> 表结构看 `docs/DATA_MODEL.md`,功能看 `docs/SPECS.md`,业务规则看 `docs/BUSINESS_RULES.md`,本文档**不重复**这些内容,只补一层"决策 + 理由 + 代码证据"。
>
> 代码符号引用全部源自真实文件:`tools/csv_to_sql.py` / `tools/local_validator.py` / `sql/01_schema.sql`。每个决策都附"代码证据"小节,便于核对。

---

## 0. 阅读地图

| 你想问 | 看哪一节 |
| --- | --- |
| 为什么不用传统三层架构,搞个 CSV 驱动 | §1 |
| 派生字段为什么不交给数据库生成 | §2 |
| 为什么金额必须四件套、汇率按月固定 | §3 |
| 为什么合同账和报关账不强行统一 | §4 |
| 为什么调拨不建独立表、负库存允许 | §5 |
| 为什么校验放在导入时、ERROR/WARN 怎么分 | §6 |
| 为什么客户/币种/品类都是数据不硬编码 | §7 |
| 为什么 schema 要四处同步 | §8 |
| 为什么报价 brief/formal 共用表、subtotal 用直接公式 | §9 |

---

## 1. 架构总览:CSV 驱动 + 校验前置

### 1.1 系统分层

```
┌─────────────────────────────────────────────────────────────────┐
│  ① CSV 数据层 (本地 data/csv/*.csv)                              │
│     业务人员 Excel → 另存 CSV。真实数据不进仓库 (R8)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ csv_to_sql.py 转换
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  ② Python 工具层                                                 │
│  ┌─────────────────────────┐   ┌────────────────────────────┐   │
│  │ tools/csv_to_sql.py     │   │ tools/local_validator.py   │   │
│  │ - DERIVED_RULES 派生    │   │ - SQLITE_SCHEMA 镜像       │   │
│  │ - DENSITY_RULES 密度    │   │ - 16 个 check_xxx 校验     │   │
│  │ - apply_derived_rules   │   │ - run_validation 16 步     │   │
│  │   (加算 + 反向校验)     │   │ - ValidationReport 红黄灯  │   │
│  └───────────┬─────────────┘   └─────────────┬──────────────┘   │
└──────────────┼────────────────────────────────┼─────────────────┘
               │ 生成 INSERT                    │ 加载 + 校验
               ▼                                ▼
┌──────────────────────────────────┐  ┌──────────────────────────┐
│  ③ SQLite 校验层                 │  │  ④ MySQL 生产层          │
│  data/db/validation.db           │  │  sql/01_schema.sql 真表  │
│  一个 .db 文件 = 一整库          │  │  业务系统最终归宿        │
│  本机免安装,流程验证完再切库     │  └──────────────────────────┘
└──────────────────────────────────┘
```

### 1.2 决策:不走传统三层架构,选"CSV 驱动 + 校验前置"

**理由(从代码找证据)**:

1. **业务源头是 Excel**。外贸企业的真实工作流是"业务员在 Excel/Numbers 里填数据 → 跟客户对账 → 落库",不是"打开一个 Web 表单逐字段录入"。`tools/csv_to_sql.py` 开头注释就写明:"你在 Excel/Numbers 里填好真实数据 → 另存为 CSV → 本脚本翻译成 INSERT"(csv_to_sql.py:9-12)。这意味着**输入边界是 CSV 文件**,不是 HTTP 请求。

2. **校验必须前置到导入环节**。一旦脏数据进了 MySQL,后续业务单据(报关、收款)都跟着错。所以 `csv_to_sql.py::apply_derived_rules` 在生成 SQL **之前**就做两件事:加算(补列)和反向校验(手填值超容差就 `return 0` 阻止写文件,见 csv_to_sql.py:911-914)。这是"质检在出厂前"而非"出厂后再查"。

3. **为什么 SQLite 做中间层**。`local_validator.py` 开头 4 行注释解释了:本机可能没装 MySQL,SQLite 是 Python 自带的,一个 `.db` 文件就是一整库,"等流程验证 OK 了,再切到 MySQL 上,只需要换连接字符串"(local_validator.py:7-12)。SQLite 这一层**纯粹是为了快、免安装、可重跑**,业务规则校验逻辑跟用啥数据库无关。

4. **数据流向是单向的**。CSV → (派生+反校验) → SQL/SQLite → MySQL。没有反向同步、没有 ORM、没有运行时表单。这套架构的复杂度被刻意压到最低,因为业务规则本身(密度公式、UCP600、汇率)才是核心,**框架不该抢戏**。

> **类比**:这就像"先在草稿纸上把账算清楚、验算两遍,再正式抄到账本上"。CSV 是草稿,SQLite 是验算纸,MySQL 是正式账本。

---

## 2. 派生字段策略设计(关键决策)

### 2.1 决策:派生字段默认走应用层(Python),不用 MySQL `GENERATED COLUMN`

**唯一例外**:`delivery_order_items.short_qty`。

### 2.2 理由(代码证据)

派生字段集中在 `tools/csv_to_sql.py::DERIVED_RULES`(csv_to_sql.py:47-407),共 11 张表 23 条派生规则(完整清单见 `DATA_MODEL.md §5.1`)。走应用层而非 DB 生成列,理由有四:

1. **跨表派生 DB 做不了**。`purchase_order_items.volume_subtotal` 依赖 `products.volume`(单件体积),这是跨表关系。MySQL `GENERATED COLUMN` 只能引用**本行**其他列,无法跨表 JOIN。所以这种字段只能在 Python 端算完再落库。证据:`local_validator.py::check_volume_subtotals`(步骤 8/16,local_validator.py:937)专门做跨表体积校验,因为它无法靠 DB 约束保证。

2. **反向校验需要容差逻辑**。客户经常"上下浮动"填一个值,系统不能强行覆盖,而是要**比对公式值,超容差才报错**。`apply_derived_rules`(csv_to_sql.py:653-748)实现了"加算 + 反向校验"双行为:CSV 没填就自动算,填了就跟公式比,超容差(`tolerance_mode` 支持 `absolute`/`percent`,csv_to_sql.py:726-735)报 ERROR。这种"软约束 + 容差"逻辑 DB 生成列完全表达不了——生成列是硬覆盖,客户填的值会被直接丢掉。

3. **密度按品类查表**。重量计算依赖 `DENSITY_RULES`(csv_to_sql.py:470-478),不同 `product_category` 用不同公式(线管固定 1.35;钢丝管 `内径×0.003+1.46`;塑筋管/水带返回 None 跳过)。这种"按业务字典查公式"的逻辑放在应用层最自然,放 DB 要写一堆 CASE WHEN 还难维护。

4. **厚度反推有三条路径**。`calc_theoretical_thickness`(csv_to_sql.py:524-576)按优先级 A > B > C 走:A 几何反推(外径-内径)/2;B 密度方程(内径+米重);C 密度方程(内径+单重+长度)。`apply_derived_rules` 里的 `depends_on_any` 处理(csv_to_sql.py:686-696)支持"任一组依赖齐即可"的 OR 关系,专门服务这种多路径反推。这种分支逻辑写进 DB 生成列几乎不可能。

### 2.3 例外:`short_qty` 为何走 DB 生成列

`delivery_order_items.short_qty` 是**唯一**走 MySQL `GENERATED ALWAYS AS (quantity - actual_quantity) STORED` 的字段(sql/01_schema.sql:532)。

**理由**:
- **纯行内计算**——`short_qty` 只依赖同一行的 `quantity` 和 `actual_quantity`,**不跨表、不容差、不分路径**。DB 生成列恰好擅长这种场景。
- **强一致性**——`actual_quantity` 一改,`short_qty` 自动重算,不存在"应用层忘算"的风险。

**三处代码落点同步的体现**(`BUSINESS_RULES.md R7` 四处中的前三处):
| 位置 | 实现方式 | 代码位置 |
| --- | --- | --- |
| MySQL 真表 | DB 生成列 | `sql/01_schema.sql:532` |
| SQLite 镜像 | 普通 INT 字段(SQLite 不支持 STORED 生成列) | `local_validator.py:298` |
| 应用层兜底 | Python lambda | `csv_to_sql.py:222-235` (`DERIVED_RULES["delivery_order_items"]["short_qty"]`) |

> **设计取舍**:之所以 SQLite 不强制生成列,是因为 SQLite 校验层在导入时已经被 `csv_to_sql.py` 的应用层版本兜底算过一遍了(`load_csv_into_sqlite` 之前先生成 SQL),所以 SQLite 里存普通 INT 即可。

---

## 3. 币种与汇率处理设计

### 3.1 决策:金额四件套 + 汇率月固定

**规则**(详见 `BUSINESS_RULES.md R1` + `R2`):凡外币金额必须同时有 `amount + currency + exchange_rate + amount_cny`,汇率每月 1 日录一次整月用同一汇率,跨月交易用各自月份的汇率。

### 3.2 四件套的设计意图

**理由(代码证据)**:

1. **杜绝"金额孤岛"**。如果只存 `amount` 不存 `currency`,USD 100 和 IDR 100 在数据库里看起来一样,但实际差几个数量级——印尼盾 100 块几乎可以忽略,美元 100 块是实打实的 720 元人民币。`check_receipts_vs_contract`(local_validator.py:1194-1199)专门校验"合同币种 vs 收款币种必须一致",就是为了堵这个漏洞。

2. **`amount_cny` 永远派生,不手填**。四张外币表的 `*_cny` 字段都在 `DERIVED_RULES` 里(csv_to_sql.py:259-324),公式统一是 `amount × exchange_rate`。**不允许手填**是因为:手填一旦汇率改了就忘了同步,导致本币金额跟原币金额对不上。派生则保证任何时候 `amount_cny` 都是 `amount × exchange_rate` 的精确结果。

3. **命名因表而异但语义统一**(`DATA_MODEL.md §7.4`):
   - `sales_contracts` / `shipping_records` 是**合计**用 `total_amount`
   - `credit_notes` 是**差额**用 `diff_amount`
   - `receipts` 是**单笔**用 `amount`

   语义都是"原币种金额",只是业务语境不同。校验函数按表分别处理(`check_exchange_rates` / `check_receipts_vs_contract`)。

### 3.3 汇率月固定 vs 实时汇率

**决策**:用月固定汇率,**不做实时汇率**。

**理由**:

1. **财务月底结账不扯皮**。如果用实时汇率,同一笔合同今天折算 720、明天折算 725,月底财务对账永远对不平。月固定汇率(`exchange_rates` 表 + 唯一约束 `uk_currency_effective (currency, effective_date)`,sql/01_schema.sql:696)保证**整月所有交易用同一条**,月底结账一笔算清。

2. **跨月产生汇兑损益是正常的,不"统一"**(`BUSINESS_RULES.md R2` 备注)。同一笔合同 7 月签(用 7 月汇率)、8 月装船(用 8 月汇率)、9 月收款(用 9 月汇率),三个月汇率不同会产生汇兑损益。**这是真实业务现象**,系统只记录不消除。定月字段按表不同(`DATA_MODEL.md §7.2`):
   - `sales_contracts` → `sign_date`(签约日)
   - `shipping_records` → `shipping_date`(装船日)
   - `receipts` → `paid_date`(到账日)

3. **校验落点**:`check_exchange_rates`(步骤 12/16,local_validator.py:1100-1159)收集所有非 CNY 业务币种,逐个检查当月是否有汇率记录,缺则报 ERROR "缺 X 月 Y 币种汇率,请补录"。

> **类比**:月固定汇率就像超市标价——这个月所有商品按月初定的汇率折算,不会因为今天汇率波动就改标签。月底统一盘点再算实际盈亏。

> **阶段二规划**:月末汇兑损益结转(`forex_settlements` 表)留阶段二,本阶段只记录不结转(见 `SPECS.md §11`)。

---

## 4. 两套账设计(关键决策)

### 4.1 决策:合同账与报关账并行,允许 ±5% 差异,不强行统一

**规则**(详见 `BUSINESS_RULES.md R3`):
- **合同账**(`sales_contracts` + `delivery_orders`):给客户/财务看的承诺值
- **报关账**(`shipping_records` + `shipping_record_items`):给海关/银行看的实际值
- 两套账允许 ±5% 差异(UCP600 国际惯例),超 5% 走 `credit_notes` 衔接

### 4.2 理由(代码证据)

1. **UCP600 国际惯例的硬约束**。信用证项下数量容差是国际惯例(UCP600 第 30 条),不是项目自定义规则。`local_validator.py::SHORT_SHIPMENT_TOLERANCE = 0.05`(local_validator.py:43)就是这条惯例的代码化。`check_shipping_vs_delivery`(步骤 10/16,local_validator.py:1016-1058)按此判定:偏差 ≤5% → WARN(允许,记录在案);偏差 >5% → ERROR(违规,必须补 credit_note)。

2. **强行统一两套账会破坏业务真实性**。合同是商务承诺(给客户的报价),报关是物理实际(装船后称出来的重量/件数)。两者本来就会有出入:装柜时少了 2 件、毛重比预估多了 3kg,这都是正常物理现象。如果把报关数据强行覆盖回合同,就丢了"实际发了多少"这个事实。所以 schema 把两套账**物理分开**成两组表,各自独立维护。

3. **credit_note 做闭环衔接**。差异(短装/超装)用 `credit_notes` 记录,4 种 `resolution`(`pending`/`replenish`/`refund`/`writeoff`)对应不同处理方式。`check_credit_notes_balance`(步骤 11/16,local_validator.py:1059-1098)强制 `pending` 不能无限期挂账:超 30 天 WARN(催办),超 90 天 ERROR(严重逾期必须 close)。

4. **`delivery_order_items` 是两套账的交汇点**。这张表同时有 `quantity`(计划,合同账)和 `actual_quantity`(实际,装柜后填)。`short_qty` 自动算差值。这是设计上刻意让"承诺 vs 实际"在同一行可见,便于追溯(见 `DATA_MODEL.md §4.5`)。

> **类比**:就像电商"订单量"和"实际发货量"——你承诺发 100 件,实际发了 98 件,这两笔账都要留着。差异 2 件要么补发、要么退款、要么注销,不能假装没发生。

---

## 5. 调拨软关联设计(关键决策)

### 5.1 决策:复用 `stock_in`/`stock_out` + `transfer_ref` 软关联,不建独立 `transfers` 表

**规则**(详见 `BUSINESS_RULES.md R3.5` + `DATA_MODEL.md §6`):调拨就是一对特殊类型的出入库单(`in_type='transfer'` / `out_type='transfer'`),两边填同一个 `transfer_ref` 号串起来。

### 5.2 理由(代码证据)

1. **调拨在业务上是"特殊出入库",不是独立单据类型**。证据:ENUM 已经包含 `'transfer'`(`stock_in.in_type` ENUM 含 `purchase`/`production`/`transfer`/`return`,sql/01_schema.sql:358;`stock_out.out_type` ENUM 含 `sale`/`production`/`transfer`/`scrap`,sql/01_schema.sql:408)。这说明调拨从建模之初就被视为出入库的一个**子类型**,而不是平行的新单据。

2. **复用现有流水和对账零额外代码**。`rebuild_stock_logs`(local_validator.py:839-895)重建流水时**不区分** `in_type`/`out_type`,所有 `confirmed` 状态的出入库都进流水。`check_reconciliation`(步骤 7/16,local_validator.py:896-936)按 `(material_id, warehouse_code)` 聚合流水对比库存表,**自动覆盖调拨**。如果建独立 `transfers` 表,这套流水/对账逻辑要单独维护一份。

3. **配对校验靠应用层兜底**。`check_transfer_pairs`(步骤 14/16,local_validator.py:1208-1269)按 `(transfer_ref, material_id)` 聚合两边数量:
   - 出库总量 ≠ 入库总量 → **ERROR**(差额、漏录或在途)
   - 只有一边(只出库没入库,或反之)→ **WARN**(在途或方向录错)

   两个索引 `idx_si_transfer`(sql/01_schema.sql:379)/ `idx_so_transfer`(sql/01_schema.sql:429)加速这种按 `transfer_ref` 聚合的查询。

4. **表数量零增量**。`DATA_MODEL.md §6.4` 给出对比表:独立 `transfers` 表要 +1 主表 +1 明细,而软关联方案 0 增量。核心权衡写在 `DATA_MODEL.md §6.4` 末段:"这个代价(软关联无外键约束)远小于多维护一张表 + 它的明细 + 它跟流水的同步逻辑"。

### 5.3 软关联的代价(取舍)

| 维度 | 代价 | 缓解措施 |
| --- | --- | --- |
| 关联强度 | 无外键约束,`transfer_ref` 可以填错或漏填 | `check_transfer_pairs` 兜底校验 |
| 跨仓不强制 | 源仓和目标仓可以填同一个仓(逻辑错) | 应用层后续可加校验,本阶段不做 |
| 配对完整性 | 单边调拨(只出库没入库)不会立即报错 | 单边 → WARN,差额 → ERROR |

**收益**(对比独立表):完全复用出入库主流程;流水/库存对账自动覆盖;`transfer` 类型天然不进报关/收款流程(隔离性)。

### 5.4 配套:负库存校验为何从 ERROR 降级为 WARN

**决策**:`check_stock_out_vs_inventory`(步骤 6/16)的累计出库 > 累计入库从 ERROR 降级为 **WARN**(local_validator.py:790-837,函数内全是 `report.warn` 无 `report.error`)。

**理由**(`BUSINESS_RULES.md R3.5` 配套规则):外贸调拨常"先做后补"——源仓先出库(此时源仓透支)、目标仓后入库(货物还在路上)。如果硬拦 ERROR,这种正常的在途业务就跑不通。降级为 WARN 提醒"请补货",但不阻断流程。

> **注意**:这跟对账(F3.4 / `check_reconciliation`)不同。**对账仍是 ERROR**——库存表跟流水累加对不上是硬错(可能漏录出入库),不允许。降级的只是"单次出库超当前库存"这一项。

> **类比**:从 A 银行卡转 100 到 B 银行卡,记账必是两笔(A 卡 -100、B 卡 +100),靠同一个转账流水号串起来对账。中途丢钱或凭空多钱都要立刻发现——这就是 `check_transfer_pairs` 的逻辑(`DATA_MODEL.md §6.1`)。

---

## 6. 16 步校验体系设计

### 6.1 设计哲学:校验前置(导入时校验)而非运行时校验

**决策**:所有业务规则校验集中在数据导入环节(`run_validation`,local_validator.py:1421-1450),不在 Web 表单运行时逐字段校验。

**理由**:

1. **输入边界是 CSV 批量导入**(见 §1.2),不是单条表单提交。批量导入天然适合"一次性全量校验",逐条运行时校验反而低效。

2. **脏数据进 MySQL 之前拦截**。`csv_to_sql.py::apply_derived_rules` 在反向校验失败时 `return 0` 阻止生成 SQL 文件(csv_to_sql.py:911-914);`local_validator.py` 在 SQLite 镜像上跑完整 16 步,任何 ERROR 都让进程退出码 = 1(local_validator.py:1555)。两层拦截确保脏数据进不了生产库。

3. **CI 门禁**(`BUSINESS_RULES.md R9`):`scripts/run_local_validation.sh` 是 CI 的门禁脚本,16 步全过才算改对。

### 6.2 ERROR / WARN 分级设计

`ValidationReport`(local_validator.py:542-567)用"红黄灯"比喻:
- `error()` → 红灯,**必须修**,会让 `report.ok = False`(local_validator.py:549-557)
- `warn()` → 黄灯,**提醒一下**,不影响 `ok`

**分级原则**(从 16 个 check 函数归纳):
| 级别 | 适用场景 | 示例 |
| --- | --- | --- |
| **ERROR** | 数据矛盾、缺失关键字段、违反硬约束 | 主表金额 ≠ 明细之和(`check_purchase_orders` / `check_sales_contracts`);入库 > 采购(`check_stock_in_vs_purchase`);对账不平(`check_reconciliation`);UCP600 超 5%(`check_shipping_vs_delivery`);调拨出库 ≠ 入库(`check_transfer_pairs`);credit_note 超 90 天(`check_credit_notes_balance`) |
| **WARN** | 业务允许但需关注、在途、催办 | 未全部到货(`check_stock_in_vs_purchase`);未发完(`check_delivery_vs_contract`);负库存(`check_stock_out_vs_inventory`);UCP600 ≤5%(`check_shipping_vs_delivery`);credit_note 超 30 天(`check_credit_notes_balance`);未收款(`check_receipts_vs_contract`);调拨单边(`check_transfer_pairs`) |

**核心判据**:ERROR 是"数据错了/缺失",WARN 是"业务没走完/在途"。前者必须修数据,后者只需催办或等待。

### 6.3 退出码二值设计

**决策**:`sys.exit(0 if report.ok else 1)`(local_validator.py:1555),只有 0/1 两个退出码。

**理由**:
- CI 只需要二值信号——绿(通过)或红(失败)。复杂的退出码(2=WARN、3=ERROR)反而让 CI 脚本难写。
- WARN 不影响退出码,因为 WARN 是"提醒"不是"失败"——业务在途是正常的,不该让 CI 红。
- 日志文件(`data/logs/validation_*.log`,local_validator.py:1543-1552)保留完整的 ERROR + WARN 详情,供人工排查。

> **16 步覆盖对照** 见 `SPECS.md §F10.3`,每一步对应的功能点都列在那里,本文不重复。

---

## 7. 数据即数据设计(关键决策)

### 7.1 决策:客户/币种/口岸/品类都是数据,不硬编码

**规则**(详见 `BUSINESS_RULES.md R6`):当前联调样本(印尼客户 Q025、PVC 线管)只是数据,不是系统边界。加新品类在 `DENSITY_RULES` 加一条公式即可,**不要新建 skill**。

### 7.2 理由(代码证据)

1. **密度公式按品类查表,不写 `if 品类`**。`DENSITY_RULES`(csv_to_sql.py:470-478)是字典,key 是 `product_category`(字符串),value 是 lambda:
   ```python
   DENSITY_RULES = {
       "线管": lambda row: 1.35,
       "钢丝管": lambda row: ... ,
       "塑筋管": lambda row: None,   # TODO 待客户补充
       "水带": lambda row: None,
   }
   ```
   `calc_density`(csv_to_sql.py:481-490)用 `DENSITY_RULES.get(category)` 查表,**找不到返回 None 跳过校验**,不报错。加新品类只需加一行字典项,不改任何业务逻辑。

2. **币种是 VARCHAR(3) 字段,不是 ENUM**。`sales_contracts.currency` / `shipping_records.currency` / `credit_notes.currency` / `receipts.currency` 全是 `VARCHAR(3) DEFAULT 'USD'`(sql/01_schema.sql:257/588/652/715)。加 IDR/EUR/SGD 只需加数据,不改 schema。`exchange_rates.currency` 同理。

3. **口岸是 VARCHAR 字段**。`port_loading` / `port_discharge`(sql/01_schema.sql:263-264)是 `VARCHAR(64)`,不是 ENUM。加新口岸(Qingdao、Jakarta、Manila...)只需加数据。

4. **客户/供应商是独立目录表**。`customers` / `suppliers` 是基础资料表(`DATA_MODEL.md §4.1`),被业务表用外键引用。加新客户只需 INSERT 一行,不改任何代码。

**违反本规则的表现**(`BUSINESS_RULES.md R6` 警告):代码里出现 `if 印尼` / `if PVC` 这类硬编码分支,应消除。

### 7.3 路由约定的边界

四个 skill 的路由是按**问题领域**分,不是按客户/品类分(`CLAUDE.md` 路由表):
- 密度/厚度/米重 → `product-params`(物理参数)
- 外径/体积/金额小计 → `derived-fields`(行内派生)
- 报关/短装/UCP600/credit_note → `trade-documents`(外贸单据)
- 收款/汇率/水单 → `payment-receivable`(财务)

加新品类**不新建 skill**,因为新品类只是多一条密度公式,问题领域没变。

---

## 8. 四处同步设计(关键决策)

### 8.1 决策:改 schema 必须同步四处

**规则**(详见 `BUSINESS_RULES.md R7`):
1. `sql/01_schema.sql` — MySQL 真表
2. `tools/local_validator.py::SQLITE_SCHEMA` — SQLite 镜像
3. `tools/csv_to_sql.py::DERIVED_RULES` — 派生字段(仅当字段是派生时)
4. `sample/templates/<表名>_template.csv` — CSV 模板表头(2026-07-30 真实数据试用踩坑后新增)

### 8.2 理由:为什么必须四处同步

**根本原因**:SQLite 校验层和 MySQL 生产层是**两套独立的 schema**,派生字段规则是**第三处独立逻辑**,CSV 模板表头是**第四处独立约束**。四处各管一摊,漏一处就会出现"MySQL 能跑但 SQLite 校验报错"或"派生字段在 CSV 转换时算错"或"模板表头跟 schema 字段对不上,录入时列错位"的不一致。

**证据(`short_qty` 这个例子最能说明 R7 四处中的前三处代码落点)**:

| 位置 | 实现 | 代码行 |
| --- | --- | --- |
| MySQL 真表 | `GENERATED ALWAYS AS (quantity - actual_quantity) STORED` | `sql/01_schema.sql:532` |
| SQLite 镜像 | 普通 `INTEGER NOT NULL DEFAULT 0`(SQLite 不支持 STORED 生成列) | `local_validator.py:298` |
| 应用层 | Python lambda 兜底版 | `csv_to_sql.py:222-235` |

如果只改 MySQL 加了生成列,但忘了 SQLite 镜像和 `DERIVED_RULES`,会出现:
- SQLite 校验时 `short_qty` 永远是 0(没有生成列机制)
- CSV 转换时 `short_qty` 不会被算出来(`DERIVED_RULES` 没这条规则)
- → 校验通过但数据是错的

**第 4 处(模板表头)踩过的坑**(2026-07-30):customers 表加了 `brand_name`/`company_profiles`/`billing_profiles` 3 个字段,但 `sample/templates/customers_template.csv` 表头没同步,真实数据 CSV 按旧模板填,多列地址被塞进 `bank_account`,触发 `ERROR 1406 Data too long`。

所以四处必须同步,`BUSINESS_RULES.md R7` 列为铁律。

### 8.3 校验机制

本项目用**静态对照**保证四处一致,而非运行时检测:

| 检查对象 | 检查方式 | 入口 |
| --- | --- | --- |
| 前三处(schema/SQLite/派生) | `schema-sync-checker` agent 静态对照 + 人工 review | `.claude/agents/schema-sync-checker.md` |
| 第四处(模板表头) | **自动化** `check-template-schema-sync.sh`,对比 schema CREATE TABLE 字段 vs 模板表头 | `scripts/run_local_validation.sh` 第 2b 步 |

原因:
- 前三处是**异构**(SQL / Python 字符串 / Python 字典),运行时统一检测复杂
- 模板表头对 schema 字段是**纯字符串比对**,可以全自动化(系统字段 `id`/`created_at`/`updated_at`/`deleted_at` 自动豁免)
- 改动频率低(加字段才需要同步),前三处静态对照 + 人工 review 足够;第四处加上自动化兜底,彻底堵死"漏改模板"的常见坑
- 配合 16 步校验(`scripts/run_local_validation.sh`)做最终兜底——如果四处没同步,某个 check 函数会报错

### 8.4 维护清单

| 改动类型 | 同步动作 |
| --- | --- |
| 加新字段(非派生) | 改 `01_schema.sql` + `SQLITE_SCHEMA` + **模板表头**(`sample/templates/<表名>_template.csv`) |
| 加新派生字段 | 改 `01_schema.sql` + `SQLITE_SCHEMA` + `DERIVED_RULES` + **模板表头** + `DATA_MODEL.md §5.1` 表格 |
| 加新表 | 改 `01_schema.sql` + `SQLITE_SCHEMA` + 新建模板表头 + `DATA_MODEL.md §2/§3/§4` |
| 改 ENUM 值 | 改 `01_schema.sql` + `SQLITE_SCHEMA`(SQLite 是 TEXT 不严格,但保持一致) |
| 删字段 / 删表 | 改对应 schema/SQLite/派生,**同步删模板**(`audit_logs_template.csv` 阶段一就是这样删的) |

> 改完后跑 `bash scripts/run_local_validation.sh`,第 2b 步自动校验模板表头一致性(WARN 不阻断,但建议尽快修)。

---

## 9. 报价派生关系设计(关键决策)

> 业务规则权威源:`BUSINESS_RULES.md R10`(报价定价铁律)。本节讲"为什么这么建表",单页决策摘要见 `docs/adr/0003-quotation-derive-from-brief.md`。

### 9.1 决策一:简要报价 brief 与正式 QT formal 共用 `quotations` 表

**决策**:brief 和 formal 两种报价类型共用 `quotations` 一张表,靠 `quote_type` ENUM(`brief`/`formal`)区分,**不建独立表**。派生关系用 `parent_quote_no` 自引用软关联(formal 指向其 brief 来源)。

**理由(代码证据)**:

1. **复用主表结构 + 金额四件套**。brief 和 formal 的字段几乎一致(都有 `quote_no`/`customer_code`/金额四件套/状态机),只是 formal 多一个"从哪派生来"的语义。共用表等于复用 `R1` 金额四件套约束和状态机,不为派生单独建一套。证据:`quotations` 表同时承载两种类型(`sql/01_schema.sql:793-824`,`quote_type` ENUM 在第 797 行)。

2. **派生关系用软关联,类似调拨 `transfer_ref`**。`parent_quote_no` 是**自引用外键**(`FOREIGN KEY (parent_quote_no) REFERENCES quotations(quote_no) ON DELETE SET NULL`,`sql/01_schema.sql:823`),靠应用层校验(formal 的 parent 必须是 brief)而非 DB 强约束。这跟调拨复用 `stock_in`/`stock_out` + `transfer_ref` 软关联(ADR-0002)是同一个思路——核心约束(出=入 / formal 来自 brief)外键保证不了,必须靠应用层聚合校验,那为了"强外键"多背一张表就不划算。

3. **被否决的备选**:独立 `brief_quotes` 表 + `formal_quotes` 表。否决理由:字段重复维护两份;派生时要跨表 JOIN;金额四件套校验要写两遍。共用表零增量,靠 `quote_type` 一个枚举区分。

**校验落点**:`check_quotations`(步骤 15/16)子校验 2——formal 的 `parent_quote_no` 必须非空且指向 brief(`local_validator.py:1300-1311`)。

### 9.2 决策二:`subtotal` 用直接公式,不走派生 `unit_price` 依赖链

**决策**:`quotation_items.subtotal` 直接写成 `weight_per_unit × price_coefficient × quantity`(三个原始字段相乘),**不**写成 `unit_price × quantity`(不依赖派生的 `unit_price`)。

**理由(代码证据)**:

`apply_derived_rules` 是**单轮遍历**——对每行只扫一遍派生规则,不做多轮依赖链计算。如果 `subtotal` 声明 `depends_on: ["unit_price", "quantity"]`,而 `unit_price` 本身也是派生字段,那么遍历到 `subtotal` 时 `unit_price` 可能**尚未加算**,导致 `subtotal` 因依赖缺失被跳过(算出 0 或 None)。

证据在代码注释里直接写明(`tools/csv_to_sql.py:334-337`):

```
# 注意: subtotal 不依赖派生的 unit_price, 而是直接展开成原始字段
#       乘积 (weight_per_unit × price_coefficient × quantity)。
#       原因: apply_derived_rules 是单轮遍历, 不做多轮依赖链计算,
#       若 subtotal 依赖 unit_price 会在 unit_price 尚未加算前就跳过。
```

实现上 `subtotal` 的 `depends_on` 是 `["weight_per_unit", "price_coefficient", "quantity"]`(`csv_to_sql.py:372`),全部是**原始输入字段**,不碰任何派生字段。`unit_price` 仍然单独派生(`csv_to_sql.py:352-361`),供查询/展示用,但不作为 `subtotal` 的输入。

**被否决的备选**:`subtotal = unit_price × quantity`(依赖链)。否决理由:单轮遍历失效。要支持依赖链得引入"多轮迭代直到收敛"的机制,复杂度暴涨,且其他表(subtotal=数量×单价)的依赖恰好都是原始字段,不需要多轮——为报价一个字段引入多轮机制不划算。

> 这条决策也呼应 §2(派生字段走应用层):正因为应用层 `apply_derived_rules` 是单轮的,所以设计派生规则时要**显式避免依赖链**,把派生字段都挂在原始字段上。

### 9.3 决策三:报价系数 `price_coefficient` 放明细,不放主表

**决策**:`price_coefficient`(报价系数 USD/KG)放在 `quotation_items` 明细表,**不放 `quotations` 主表**。

**理由(代码证据)**:

一张报价单里**可以有多个管径组,每组用不同系数**。例如 demo 数据里 QT20260729001 的两行明细都用 `A组-1.112`(`data/csv/demo_runtime/quotation_items.csv`),但实际业务中一张单可能同时有 `A组-1.112`、`B组-1.065`、`C组-1.075` 三组系数。如果系数放主表,只能存一个值,无法承载"一单多组"。

证据:`quotation_items` 有 `group_code VARCHAR(32)`(分组码)+ `price_coefficient DECIMAL(10,4)`(系数)两个字段(`sql/01_schema.sql:845-846`),`group_code` 上还建了索引 `idx_qi_group`(`sql/01_schema.sql:868`)加速按组聚合查询。主表 `quotations` 没有系数字段。

**被否决的备选**:主表加一个 `default_coefficient`。否决理由:无法表达一单多组;若强行按主表系数算,不同管径的报价会算错。

### 9.4 衔接销售合同:`converted_contract_no` 回填

**决策**:报价转销售合同后,`quotations.status` 推进到 `'converted'`,`converted_contract_no` 回填对应的 `sales_contracts.contract_no`,形成"报价→合同"链路。

**理由**:报价是合同的前置环节(R10),转单后需要可追溯(这份合同从哪份报价来)。`converted_contract_no` 是可空字段(未转单时为 NULL),不建强外键(因为销售合同生命周期独立于报价),靠 `check_quotations` 子校验 3 兜底:converted 状态的报价若填了 `converted_contract_no`,该合同号必须在 `sales_contracts` 存在(`local_validator.py:1313-1322`)。

---

## 附录:文档维护约定

- **本文档只记录"为什么"**:表结构看 `DATA_MODEL.md`,功能看 `SPECS.md`,规则看 `BUSINESS_RULES.md`,校验步骤看 `VALIDATION_GUIDE.md`。本文档大量引用,不复制。
- **加新设计决策**:在对应章节加"决策 + 理由 + 代码证据"三段式结构,代码符号必须真实存在(可在 `sql/` / `tools/` / `scripts/` 里 grep 到)。
- **代码符号变更**:如果引用的函数/常量改名(如 `check_transfer_pairs` 重命名),必须同步更新本文档引用。
- **真实数据不进仓库**(`BUSINESS_RULES.md R8`):本文档不引用任何真实客户/供应商/合同数据,示例编号均为格式示例。
- **自检**:`bash scripts/run_local_validation.sh`,16 步全过才算改对(`BUSINESS_RULES.md R9`)。

DONE
