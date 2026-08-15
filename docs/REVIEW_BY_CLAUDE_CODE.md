# 独立代码审查报告 (2026-08-15)

> 审查人: Claude Code (独立审查, 未参与开发)
> 范围: db_writer.py / api/main.py / local_validator.py / db_to_csv.py / run_local_validation.sh / streamlit_app.py(部分) / frontend/src/pages(重点页) / sql/01_schema.sql(模块五)
> 方法: 纯读代码, 未运行任何脚本、未连数据库、未修改任何文件 (本报告除外)
> 已知设计决策 (快照原则/无登录/CSV 双轨/负库存不拦/8501 只读例外) 不作为问题上报

---

## 🔴 严重 (会导致钱/数据出错)

### 1. 老板特批 (price_gap_approved) 的留痕完全没有落库 —— 机制是空的

- **[tools/db_writer.py:1858-1868]** `create_delivery` 的 `head_row` 里没有 `price_gap_approved` / `price_gap_reason` 两个字段;
- **[sql/01_schema.sql:511-529]** `delivery_orders` 表本身就没有这两列 (全 sql/ 目录 grep `price_gap` 零命中);
- **[tools/db_writer.py:1892-1894]** `write_audit` 的 new_values 只记 `{delivery_no, items, contracts}`, **特批原因一个字都没进审计**。

**为什么是真问题**: BUSINESS_RULES.md 变更记录 (2026-08-14) 明确写着"发货头 `price_gap_approved=true` + `price_gap_reason` 必填（原因随审计留痕）"，且整套无权限系统的替代方案就是"留痕+公示"。现在留痕只存在于一次性的 HTTP 响应里——前端弹窗关掉就没了。叠加 `operator` 是自由文本且默认 `frontend-react` (见 🔵-9), 结果是: 任何人在 8082 勾一下"老板特批"、随便填个字，低价放行就永久匿名, 8501 首页预警卡 (streamlit_app.py:299) 也只显示风险组合、无法区分哪些是已特批放行的。2026-08-14 把这条从 WARN 升级为 ERROR 的那次变更, 其核心承诺 (可追责) 没有兑现。

**复现路径**: 8082 发货页勾选"老板特批"+填原因 → 提交成功 → 查 `delivery_orders` (无此二列)、查 `audit_logs` (new_values 无 reason) → 特批证据全丢。

**建议修法**: 二选一: ① `delivery_orders` 加 `price_gap_approved TINYINT` + `price_gap_reason VARCHAR(255)` 两列, `_doc_insert` 时写入; ② 不动表, 把 reason 塞进 `write_audit` 的 new_values。① 更利于 8501 复核卡直接查询展示。

---

### 2. 超发闸门用 `quantity` 校验、却按 `actual_quantity` 回写 —— 直调 API 可绕过超发拦截

- **[tools/db_writer.py:1803-1806]** 拦截判断: `pending = quantity - delivered_qty; if int(qty) > pending → ERROR`, 这里的 `qty` 只看 items 里的 `quantity`;
- **[tools/db_writer.py:1849]** 落库行: `"actual_quantity": int(_pos(it.get("actual_quantity"), 0) or qty)` —— `actual_quantity` 是前端/API 可传字段, **没有任何 ≤ quantity / ≤ pending 的校验**;
- **[tools/db_writer.py:1872-1875]** 回写合同: `delivered_qty = delivered_qty + actual_quantity`。

**为什么是真问题**: 校验和回写用两个不同的数。页面写明"超发自动拦截" (DeliveryEntry.tsx:127), 前端 InputNumber 有 `max={pending_qty}` (DeliveryEntry.tsx:182), 但后端闸门本身没兜住 `actual_quantity`。绕过后 `delivered_qty` 超过 `quantity`, 后续依赖 `delivered_qty` 的逻辑 (超发拦截、关行余量、8501 还欠统计) 全部被污染, 直到有人跑第 5 步校验才报 ERROR (而第 5 步自身还有问题, 见 🔴-3)。另外 `or qty` 的写法让"填 0" (整行全损) 被当成"发满计划数"。

**复现路径**: `curl -X POST /api/docs/delivery` 传 items `[{"contract_no":..., "contract_item_no":..., "quantity":1, "actual_quantity":9999}]` → 校验通过 (1 ≤ pending), 回写 delivered_qty += 9999。

**建议修法**: 在 1849 行前加一条与 1804 同口径的校验: `actual_quantity` 未显式提供时才默认等于 `qty`; 显式提供时必须 `1 ≤ actual_quantity ≤ pending` (或至少 ≤ quantity), 超出报 ERROR。

---

### 3. 第 5 步校验 `check_delivery_vs_contract` 有一个孤立 JOIN, 客户第 2 张 confirmed 发货单起 SUM 被 K 倍放大

- **[tools/local_validator.py:813-817]**
  ```sql
  LEFT JOIN delivery_orders d ON d.customer_code = sc.customer_code AND d.status='confirmed'
  LEFT JOIN delivery_order_items doi
         ON doi.contract_no = sci.contract_no AND doi.contract_item_no = sci.item_no
  ```
  `d` 既不出现在 SELECT 列, 也不参与 `doi` 的关联条件 —— 它是纯粹的行数放大器: 客户有 K 张 confirmed 发货单、合同行有 M 条发货行时, JOIN 结果是 K×M 行, `SUM(actual_quantity…)` = 真实值 × K。

**为什么是真问题**: 这是 16 步校验的核心步骤, 也是 `delivered_qty` 的"官方回写器" (794-839, 校验时现算回写)。一旦任何客户开出第 2 张 confirmed 发货单: 已发量显示为真实值的 2 倍 → 要么误报 ERROR"发货 X > 合同 Y"卡死整个校验流程, 要么 (未超时) 把 K 倍值回写进镜像库的 `delivered_qty`。此前没炸只是因为真实数据里每个客户恰好只有一张 confirmed 发货单——这是踩着数据形状活着的地雷。同时它正是你担心的"真错误被淹没": 从此每张多单客户都报红, 真正的超发反而看不出。

**复现路径**: 给任一客户开两张 confirmed 发货单 (各发同一合同行一部分, 合计 ≤ 合同量) → 跑 `run_local_validation.sh` → 第 5 步报"发货(2×实际) > 合同" ERROR。

**建议修法**: 删掉 `LEFT JOIN delivery_orders d …` 这一行 (doi 已按 contract_no+contract_item_no 直连合同行, 不需要经 d 中转); 若本意是"只统计 confirmed 发货单上的明细", 应改为 `doi` 的 JOIN 条件里加 `EXISTS (SELECT 1 FROM delivery_orders d2 WHERE d2.delivery_no=doi.delivery_no AND d2.status='confirmed')`。

---

### 4. "装柜后回填 actual_quantity" (F5.2/SOP 保管员必做动作) 在全系统没有任何入口 —— R13 提成"实发口径"名存实亡

- **[frontend/src/**]** 整个 8082 前端 grep `actual_quantity` 零命中——发货录入页没有这个输入框, 也没有任何单据编辑页;
- **[tools/db_writer.py]** 没有任何"回填实发数/确认发货单"的函数 (只有 create_delivery 一次性写入);
- **[tools/streamlit_app.py:480-481,755,917,1190,1382]** 8501 全部是只读 SELECT。

**为什么是真问题**: 这不是缺个便利功能, 而是核心流程断裂:
1. SOP_ROLES 保管员红线: "回填实发数 actual_quantity，当天必做，忘填全系统数据失真"——现在**想做也没地方做** (唯一通道是手工改 CSV 再 `load-csv-to-db.sh --mode replace` 全行替换, 这不是给保管员用的);
2. **[tools/db_writer.py:1849]** 8082 建单时 `actual_quantity` 默认=计划数 `quantity` → `short_qty` 恒为 0, "两套账"的短装/超装机制 (schema:540-545) 从未真正运转;
3. **R13 (2026-08-14 老板定)**: 提成吨位基数 = "实际发货数量"× 单重, 8501 报表用 `IF(actual>0, actual, quantity)`——因为 actual 恒等于计划数, **短装时提成按计划数虚算** (计划 100 实发 95, 提成按 100 卷的吨位算), 直接多算钱;
4. SOP 写的"draft 预制单 → 装柜回填 → 确认"三步, 代码里一步到位 `status='confirmed'` (db_writer.py:1866), draft 形同虚设。

**复现路径**: 开一张计划 100 卷的发货单 → 装柜实际只装 95 卷 → 全系统查无任何界面可以改成 95 → 提成报表按 100 卷吨位计提。

**建议修法**: 加一个 `update_delivery_actual(delivery_no, items=[{item, actual_quantity}], operator)` 走 db_writer 规则层+审计 (照 8501 关行按钮的模式), 8082 或 8501 给保管员一个回填入口; 回填后同步修正 MySQL `sales_contract_items.delivered_qty` (现第 5 步回写只发生在 SQLite 镜像里, 见 🟡-7)。

---

## 🟡 中等 (边界场景出错或误导操作)

### 5. create_delivery 读合同行无 FOR UPDATE, 并发开单可双超发

- **[tools/db_writer.py:1781-1789]** 读取 `delivered_qty` 是普通 SELECT (快照读); 回写在 1872-1875。
- 对比: 同文件 **[2032]** `_apply_inventory` 和 **[1014]** `aux_stock_move` 都规规矩矩用了 `FOR UPDATE`, 唯独超发拦截这条最要命的链路没锁。

**为什么是真问题**: 两个业务员同时给同一合同行各开一张发货单 (SOP 场景 5 明确支持多人并发抢开单): 两边都读到旧的 `delivered_qty`, 都通过校验, 都提交 → 合计超发。"先到先得只看确认顺序"是人对物理库存的约定, 但 `delivered_qty` 是合同账, 账不能靠礼貌保证。同理 `close_contract_item` 与 `create_delivery` 之间也有同类窗口 (关行提交前, 发货单读到的是 active 行)。

**复现路径**: 合同行余量 100, 两个会话同时 POST `/api/docs/delivery` 各发 100 → 两个都成功, delivered_qty=200。

**建议修法**: 1781 的 SELECT 加 `FOR UPDATE` (注意它 JOIN 了 sales_contracts, InnoDB 会锁两表行, 可接受); 或把回写改成带条件的 `UPDATE … SET delivered_qty=delivered_qty+%s WHERE … AND delivered_qty+%s<=quantity` 检查受影响行数。

### 6. draft 合同可以直接发货, 状态联动却不动 draft

- **[tools/db_writer.py:1796-1797]** 只拦 `sc.status='cancelled'`; draft 合同照发。
- **[tools/db_writer.py:1887-1889]** 状态联动 `WHERE status IN ('confirmed','delivering')` —— draft 合同发完货永远是 draft, 带着 `delivered_qty>0` 的"未生效"合同。SOP 时间节点: 合同须客户确认 (confirmed) 才进入发货。

**建议修法**: 1796 处补 `if ci["status"] not in ("confirmed","delivering","completed"): errors…` (draft/cancelled 一律拒发)。

### 7. 发货单没有作废通道, 且"回写增量"与"现算口径"两本账会分叉

- **[tools/db_writer.py:1866]** `status` 从 header 透传 (`header.get("status") or "confirmed"`), ENUM 之外的怪值靠 DB 报错兜底;
- 全后端没有取消/作废发货单的接口 (ALLOWED_TABLES 也不含 delivery_orders), 作废只能改库或 CSV;
- 作废后: MySQL `delivered_qty` 是 1872-1875 的**增量硬写**不会回冲, 而 8501 统计 (streamlit_app.py:917-920 等) 是 `IF(status IN confirmed/shipped)` **现算**——作废一张单, 两侧立即差一张单的量, 超发拦截 (用 delivered_qty) 从此虚拦正常发货。
- 同根问题: 第 5 步校验对 `delivered_qty` 的权威回写只发生在 SQLite 镜像 (local_validator.py:835-839), MySQL 侧没人同步, CSV 改过 actual_quantity 后两侧漂移无人收敛。

**建议修法**: 补一个 `cancel_delivery(delivery_no, reason)` 走规则层: 置 cancelled + 反向冲减 delivered_qty + 合同状态重算 + 审计; 并明确 delivered_qty 的唯一真相源 (建议统一为"现算", 或校验器把回写同步回 MySQL)。

### 8. R2"汇率月固定"在录入和校验两端都是弱实现

- **[tools/db_writer.py:226-227]** `lookup_exchange_rate` 取"paid_date 当天或之前最近一条"——交易日所在月没录汇率时, **静默借用上月汇率**; `create_quotation/create_contract` 调它时把提示 note 丢弃 (只 `rate, _note = …`), 跨月错汇率无任何 WARN 到达用户;
- **[tools/local_validator.py:1159-1216]** `check_exchange_rates` 只检查"每币种最近一条是否 ≥ 本月 1 号", **不逐笔核对每张合同的汇率月份**——R2 §校验原文承诺"对每个用外币的业务记录,查其当月币种汇率,缺则报 ERROR", 历史月份缺汇率完全查不出 (本月刚录过一条就全绿)。

**为什么是真问题**: 三不管地带正好对上你说的"两个校验各自假设对方会查": 录入端假设"校验会抓月份", 校验端只查"最新一条", 结果谁都沒抓。跨月汇率错一条, amount_cny 全月错。

**建议修法**: `check_exchange_rates` 改为逐表 JOIN `exchange_rates` 按交易月份查 (contract→sign_date 月, shipping→shipping_date 月, receipt→paid_date 月), 查不到该月记录即 ERROR; 录入端 `lookup_exchange_rate` 命中"非当月"汇率时至少把 rate_note 升级为前端可见的 WARN。

### 9. SQLITE_SCHEMA 未同步 R14 自然唯一键, 违反 R7 四处同步

- **[tools/local_validator.py:305-323, 237-246, 263-272, 357-372]** `delivery_order_items` / `stock_in_items` / `stock_out_items` / `shipping_record_items` 四张表在 SQLite 镜像里**都没有 UNIQUE 约束**, 而 MySQL 侧 2026-08-14 已补 `uk_doi_doc_item` 等四个自然键 (R14)。
- 后果: `load_csv_into_sqlite` 的 `INSERT OR REPLACE` (615 行) 在这些表上失去锚点退化为纯追加——CSV 一旦有重复行 (R14 事故清理前正是这个形态), 校验库重复计数, 所有 SUM 类校验跟着失真, 与 🔴-3 叠加更难排查。

**建议修法**: SQLITE_SCHEMA 四张表补上与 MySQL 相同的 UNIQUE 约束 (R7 第 2 处); 顺手可加一个脚本比对两套 schema 的键差异。

### 10. credit_notes (R3 差异闭环) 没有任何录入通道

- **[api/main.py]** 全部路由中没有 credit_note 的创建接口; **[tools/db_writer.py]** 无对应函数; 前端无页面。ALLOWED_TABLES 也不含它。
- R3 规定"超出 5% 的差异通过 credit_notes 处理", `check_shipping_vs_delivery` 超差报 ERROR 后, 用户下一步只能手工编 CSV 再灌库——报关员/财务没有可用的操作界面, 闭环只剩校验器在催 (check_credit_notes_balance)。

**建议修法**: 至少给 credit_notes 一个 preview+insert 通道 (加进 ALLOWED_TABLES + FIELD_RULES), 或在 8082 加简单录入页; 否则把 R3 的 ERROR 降级说明"需管理员手工处理", 别让录入员面对一个无法消除的 ERROR。

### 11. CORS `allow_origins` 默认 `*`, 任何外部网页可驱动员工浏览器写内网库

- **[api/main.py:34-40]** 默认 `*` + `allow_methods=["*"]`。系统无鉴权, 所以恶意页面不需要 cookie——员工在内网电脑上打开任意外部网站, 该站点的 JS 可直接向 `http://内网IP:8000/api/docs/delivery` 等 POST 写数据 (JSON POST 会发预检, 预检被 `*` 放行)。这属于你说的"哪怕内网也不该裸奔"的一类。

**建议修法**: `CORS_ORIGINS` 默认收紧为前端自己的两个源 (Vite 端口 + Nginx 同源本来就不用 CORS), 环境变量按需放开。

### 12. 附件上传: 先整读进内存再验大小; aux_code 未做格式校验

- **[api/main.py:373-375]** `content = await file.read()` 无上限读完整后才检查 10MB——并发几个大文件就能吃光 API 容器内存 (DoS 向量);
- **[api/main.py:377]** `rel_path = f"aux/{aux_code}/{uuid}.{ext}"`, `aux_code` 是路径参数, 未校验格式。受 Starlette 路由 `{aux_code}` 不匹配 `/` 限制, 穿越深度最多一级 (`aux_code=..` → 写到 ATTACH_DIR 根), 危害有限, 但目录名可以塞任意长字符串/怪字符, 且行为完全依赖框架细节, 属于不该依赖的隐式防御。

**建议修法**: 流式读取并在累计超过 10MB 时中断 (`file.read(chunk)` 循环); `aux_code` 加 `^[A-Za-z0-9_-]+$` 白名单校验 (反正辅料编码有格式)。

### 13. 销售出库与发货单数量完全脱钩, 可重复超额出库

- **[tools/db_writer.py:2237]** 出库校验只到"物料在发货单明细里"这一步, **不校验出库数量 ≤ 发货数量, 也不累计同一发货单的历史出库**; 前端 StockOutEntry 也只做"选了发货单"的检查 (56 行)。
- 后果: 同一发货单可以对同一物料出库任意多次、每次任意量, 库存被扣成大负数只有仓库级 WARN (负库存不拦是已知约定, 但那是给"先做后补"的调拨/生产场景兜底的, 不是给"同一张发货单重复出库"用的)。

**建议修法**: sale 类型出库时按 (delivery_no, material_id) 累计校验 `Σ已出库 + 本次 ≤ 发货数量`, 超出报 ERROR; 确有分批出库场景再放宽为 WARN。

### 14. [存疑] 前端必填约束后端未全部兜底

- 前端强制: 采购入库必须选 po_no (StockInEntry.tsx:59)、生产入库必须选合同 (60)、销售出库必须选发货单 (StockOutEntry.tsx:56)。
- 后端 `create_stock_in` 我确认到生产入库的合同匹配检查 (2100-2125 区间), 但**采购入库缺 po_no、销售出库缺 delivery_no 时后端是否同样报错, 我没有读到明确分支** (出库只在 delivery_no 存在时才做 2237 的匹配检查)。
- **需要确认**: 直调 API 传 `in_type='purchase'` 且无 `po_no` / `out_type='sale'` 且无 `delivery_no` 的请求, 后端是拒绝还是静默入库/出库成"无来源单据"。若静默接受, 则校验器 `check_stock_in_vs_purchase`/调拨配对会把它们算漏 (LEFT JOIN 不上就当 0), 与 🔴-2 同属"闸门只装在前端"。

---

## 🔵 建议 (可读性/健壮性/可维护性)

### 15. 收款累计口径三处不一致
- **[tools/db_writer.py:260]** `post_checks` 收款累计 = `status != 'cancelled'` (含 draft);
- **[tools/local_validator.py:1240]** 校验器 = `status = 'confirmed'` (不含 draft);
- **[frontend/src/pages/ReceiptEntry.tsx:67]** 前端固定传 `'confirmed'`。
当下真实数据无 draft 收款所以无感, 一旦 CSV 灌了 draft 收款, 录入端拦截与校验器结论会互相矛盾。建议统一成"非 cancelled"。

### 16. 审计 record_id 指向了错误的表
- **[tools/db_writer.py:1891]** `record_id = cur.lastrowid` 取的是**最后一个 INSERT** 的 id——循环里最后插入的是 `delivery_order_items` 的行, 而 audit 记的是 `table_name='delivery_orders'`。按 (table_name, record_id) 反查会定位到一张明细表的主键。应在 `_doc_insert(cur, "delivery_orders", head_row)` 后立刻取 lastrowid 保存。

### 17. 校验器输出 [0/15] 硬编码
- **[tools/local_validator.py:1703]** 打印 `[0/15]`, 实际 CHECK_STEPS 是 16 步 (函数注释里自己批评过这种不同步)。

### 18. CSV 数值猜测转换静默吞错
- **[tools/local_validator.py:626-632]** `"." in v` 试 float、失败留原字符串。手工 CSV 敲错 (如 `1.2.3`) 不报错, 直接以文本进 SQLite, SUM 时按 0 算——错误被静默放大成"对账不平"而不是"这格填错了"。建议数值列类型不符时报 WARN 带行号。

### 19. db_to_csv 的转义还原顺序有缺陷 + 表名拼接
- **[tools/db_to_csv.py:61]** 还原顺序是 `\n`→换行、`\t`、最后 `\\\\`→`\`: 字段里真的出现过"反斜杠+n"文本时会被错误还原成换行。应先还原 `\\\\` 再还原其余。
- **[tools/db_to_csv.py:72-74]** 表名直接拼进 information_schema 查询——本地自用工具风险低, 但加一个 `^[a-z_]+$` 校验成本几乎为零。
- **[tools/db_to_csv.py:61]** 同一行: 值恰为字面 `"NULL"` 的字段会被误转成空串 (与 batch 输出的 NULL 指示符无法区分, 属工具固有限制, 提醒知悉)。

### 20. /api/health 泄露 DB 连接错误详情
- **[api/main.py:74-75]** `str(e)` 原样返回, 可能带主机名/用户名/网络拓扑。内网危害小, 建议只返回 ok/false + 错误类别。

### 21. suggest_doc_no 对非标准单号脆弱
- **[tools/db_writer.py ~1780 区间]** 取 `row[col][-3:]` 转 int 作流水基数。库里存在 `DN20260802-1` 这类手改格式时, `int("-1")` 合法得 -1 (推出 000), `int("2-1")` 直接 ValueError → 接口 500。建议对单号格式先 `isdigit()` 防御。

### 22. 跑一次校验会自动改写 data/csv 源文件
- **[scripts/run_local_validation.sh:63]** 步骤 2c `normalize_csv.py` 无条件"修复"用户 CSV (压平多行字段等)。文档已声明此行为, 但"校验"名义上是只读操作, 隐式变更源数据容易在排障时造成困惑——建议 normalize 前备份原文件或输出 diff 摘要。

### 23. operator 自由文本且无记忆, 审计里大概率永远是 "frontend-react"
- **[frontend/src/pages/DeliveryEntry.tsx:221]** 操作人输入框不持久化 (无 localStorage), 每单都要手敲。人性结果是大量留空 → 审计 operator 全是默认值, "谁干的"这个信息实际上不存在。建议至少 localStorage 记住上次填写, 并在留空时用红色提示"审计将无法追溯到人"。

### 24. 关行留痕 remark 截断会吃掉盖章内容
- **[tools/db_writer.py:1939]** `((remark or "") + stamp)[:255]` —— 原 remark 较长时, 时间/操作人/原因 (stamp 恰在末尾) 被整段截掉; **[tools/streamlit_app.py:332]** 复核卡 `split("|")[-1]` 取到的就是残缺甚至完全错误的"留痕"。建议 stamp 放前面或单独加列, 至少保证 stamp 完整。

---

## 附: R1–R14 逐条核对结论 (仅列有缺口的)

| 规则 | 结论 |
| --- | --- |
| R2 汇率月固定 | **缺口** — 录入端跨月静默借旧汇率、校验端不逐笔核月份 (🟡-8) |
| R3 ±5%/credit_note 闭环 | **缺口** — credit_notes 无录入通道, 闭环只有催办没有出口 (🟡-10) |
| R7 schema 四处同步 | **缺口** — SQLITE_SCHEMA 未跟 R14 的四个自然唯一键 (🟡-9) |
| R13 提成实发口径 | **缺口** — actual_quantity 无回填入口, "实发"实为计划数 (🔴-4) |
| R14 双轨幂等 | **缺口** — 同 R7; 另 8501/校验器与 MySQL 的 delivered_qty 双真相源未收敛 (🟡-7) |
| 2026-08-14 低价拦截变更 | **缺口** — 特批留痕未落库 (🔴-1) |
| 2026-08-14 关行变更 | 基本落地; 边界 (恰 5% 不触发、quantity>0 防除零) 与文档一致; 留痕截断见 🔵-24 |
| R1/R3.5/R4/R5/R6/R8/R9/R10/R11/R12 | 未发现问题 (R11 取数优先级/容差/覆盖范围与文档逐项一致) |

> [存疑] 项 (🟡-14) 需要的信息: 直调 API 省略 po_no/delivery_no 时 `create_stock_in/create_stock_out` 的实际行为——读 2172-2260 区间未能完全确认 sale 无 delivery_no 是否有前置拦截分支。

---

## 附 2: Kimi 逐条核对结论 (2026-08-15)

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| 🔴-1 特批留痕未落库 | **成立** | head_row 无 price_gap 字段; audit new_values 仅 delivery_no/items/contracts; delivery_orders 表无列 |
| 🔴-2 actual_quantity 绕过闸门 | **成立** | 闸门只查 quantity; 回写用 actual_quantity 且无上限校验 |
| 🔴-3 孤立 JOIN 放大 SUM | **成立** | local_validator.py:813 亲见, d 不出现在 SELECT 也不参与 doi 关联; 当前真实数据每客户恰一张 confirmed 单所以未爆 |
| 🔴-4 actual_quantity 无回填入口 | **成立** | 前端 grep 0 命中; 后端无 update/cancel 函数; R13 实发口径因此名存实亡 |
| 🟡-5 无 FOR UPDATE | 成立 | create_delivery 读合同行为快照读 |
| 🟡-6 draft 可发货 | 成立 | 只拦 cancelled |
| 🟡-7 无作废通道+双真相源 | 成立 | 无 cancel_delivery; MySQL 增量写 vs 8501 现算 |
| 🟡-8 汇率弱实现 | 成立 | check_exchange_rates 只查 MAX(effective_date) 比本月1号 |
| 🟡-9 镜像缺唯一键 | 成立 | SQLITE_SCHEMA 四张明细表无 UNIQUE, MySQL 侧 8-14 已补 |
| 🟡-10 credit_notes 无通道 | 成立 | ALLOWED_TABLES 仅 exchange_rates/receipts/products |
| 🟡-11 CORS * | 成立 | api/main.py:36 亲见 |
| 🟡-12 上传先读后验 | 成立 | api/main.py:373-377 亲见 |
| 🟡-13 出库数量脱钩 | 成立 | 只校验物料在发货单明细里 |
| 🟡-14 [存疑] 后端必填兜底 | **误判, 撤销** | create_stock_in 有 "采购入库必须关联采购单号"; create_stock_out 有 "销售出库必须关联发货单号", 后端有兜底 |
| 🔵-15~24 | 成立(小) | 16 审计 record_id 指错表、24 remark 截断吃留痕, 优先修; 其余顺手 |

> 修复分三批: ①钱和账(🔴-3/2/1, 🟡-9/5/6) ②流程闭环(🔴-4, 🟡-7/13/8) ③加固(🟡-11/12, 🔵)。
> 每批跑 tests/demo_roleplay_test.py + scripts/run_local_validation.sh 双回归。
