# 生产辅料管理模块计划 (标签纸先行)

> 来源：2026-08-01 老板需求——标签纸建立原料库，可上传尺寸和 PDF/Word/图片附件，
> 按订单使用情况收发（出入库）+ 查询计数，新合同推送生产时提示所用标签纸数量。
> 定位：作为**生产辅料收发管理**的第一种类型引入数据库和工作流，后续可扩展到其他辅料。
>
> 关联文档：`docs/FRONTEND_PLAN.md`（阶段二 React+FastAPI）、`sql/01_schema.sql`、`docs/TASKS.md`

---

## 1. 需求拆解

| # | 老板原话 | 落地为 |
|---|---------|--------|
| 1 | 标签纸需要新建原料库 | 新表 `aux_materials` 辅料主档（标签纸=第一种类型） |
| 2 | 更改 MySQL，加入这个表单 | schema 变更 + React 录入端「辅料档案」表单页 |
| 3 | 上传尺寸和 pdf/word/图片 | 尺寸=结构化字段（宽/高 mm）；附件=文件落盘 + `aux_attachments` 表登记 |
| 4 | 根据订单使用情况收发物料（出入库） | `aux_stock_moves` 辅料收发流水 + `aux_inventory` 辅料库存 |
| 5 | 增加查询和计数 | 辅料库存查询页 + 流水账 + 用量统计 |
| 6 | 新合同推送生产时提示标签纸数量 | 标签需求计算接口 + 合同页/生产推送处提示（库存够不够） |
| 7 | 作为生产辅料的一种引入 | `aux_type` 枚举预留扩展（label_paper 先行） |
| 8 | 物料类型/用料/打线/米标做同样处理（2026-08-01 追加，**当日定案**） | **打线/米标/物料类型=工艺参数档案**：保留 products 字段+按客户历史值下拉（已落地），不入辅料库、不管库存（米标=喷码后打印的格式，纯工艺参数）；**用料=半成品原材料，后续开发独立模块管收发**，本模块只预留，不做 |

**现状盘点**：`products.label_paper` 已有引用约定（R 开头=长方形/纸卡，C 开头=圆环），
真实数据 12 条引用、3 个品种（R02502/R02505/R02506）——迁移量极小，直接种子化。

---

## 2. 数据库设计（3 张新表 + 1 张附件表）

> 设计原则：照抄现有库存模块的"主档 → 库存 → 流水"骨架（`inventory`/`stock_logs` 同款），
> 但辅料**不进 products 表**（不是产品），独立成 `aux_` 前缀一族。
> 收发单简化：辅料收发场景简单（采购入/生产领用出/盘点调整），
> 用**单表流水**代替成品的"单头+明细"四表结构，审计靠 audit_logs + 流水自证。

### 2.1 `aux_materials` 辅料主档

```sql
CREATE TABLE aux_materials (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    aux_code        VARCHAR(32)  NOT NULL UNIQUE    COMMENT '辅料编码, 如 LP-R02502 (标签纸沿用原R/C编号)',
    aux_type        ENUM('label_paper','packaging','other')
                                 NOT NULL DEFAULT 'label_paper' COMMENT '辅料类型: 标签纸/包装/其他(预留)。用料=半成品原材料, 后续独立模块, 不在此表',
    name            VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '名称, 如 长方形标签 25×40',
    shape           VARCHAR(8)   NOT NULL DEFAULT '' COMMENT '形状: R=长方形/纸卡, C=圆环形 (沿用 products.label_paper 约定)',
    width_mm        DECIMAL(8,2) DEFAULT NULL        COMMENT '宽度(mm)',
    height_mm       DECIMAL(8,2) DEFAULT NULL        COMMENT '高度(mm)',
    material_desc   VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '材质描述, 如 铜版纸/不干胶',
    supplier_code   VARCHAR(32)  DEFAULT NULL        COMMENT '默认供应商(关联 suppliers.code)',
    unit            VARCHAR(16)  NOT NULL DEFAULT '张' COMMENT '计量单位: 张/卷/包',
    pcs_per_unit    INT          DEFAULT NULL        COMMENT '每单位张数(按卷/包采购时换算用)',
    min_stock       INT          DEFAULT NULL        COMMENT '安全库存(低于则预警), NULL=不预警',
    remark          VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_aux_supplier FOREIGN KEY (supplier_code) REFERENCES suppliers(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='生产辅料主档(标签纸等)';
```

### 2.2 `aux_inventory` 辅料库存（当前存量，"结果"）

```sql
CREATE TABLE aux_inventory (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    aux_code        VARCHAR(32)  NOT NULL,
    warehouse_code  VARCHAR(32)  NOT NULL,
    quantity        INT          NOT NULL DEFAULT 0 COMMENT '当前库存(张)',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_aux_warehouse (aux_code, warehouse_code),
    CONSTRAINT fk_auxinv_aux       FOREIGN KEY (aux_code)       REFERENCES aux_materials(aux_code),
    CONSTRAINT fk_auxinv_warehouse FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料当前库存';
```

### 2.3 `aux_stock_moves` 辅料收发流水（"原因"，入库为正/出库为负）

```sql
CREATE TABLE aux_stock_moves (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    move_no         VARCHAR(32)  NOT NULL              COMMENT '收发单号, 如 AXIN20260801001 / AXOUT20260801001',
    aux_code        VARCHAR(32)  NOT NULL,
    warehouse_code  VARCHAR(32)  NOT NULL,
    direction       ENUM('in','out') NOT NULL          COMMENT '入库/出库',
    change_qty      INT          NOT NULL              COMMENT '变动数量(张), 入正出负',
    after_qty       INT          NOT NULL              COMMENT '变动后该仓该辅料库存',
    source_type     ENUM('purchase','production_use','adjust','scrap')
                                 NOT NULL              COMMENT '来源: 采购入库/生产领用/盘点调整/报废',
    source_no       VARCHAR(32)  NOT NULL DEFAULT ''   COMMENT '关联单号: 采购PO号/合同号(生产领用时填)',
    operator        VARCHAR(32)  NOT NULL DEFAULT '',
    move_date       DATE         NOT NULL,
    remark          VARCHAR(255) NOT NULL DEFAULT '',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auxmv_aux       FOREIGN KEY (aux_code)       REFERENCES aux_materials(aux_code),
    CONSTRAINT fk_auxmv_warehouse FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料收发流水';

CREATE INDEX idx_auxmv_aux_time ON aux_stock_moves(aux_code, move_date);
CREATE INDEX idx_auxmv_source   ON aux_stock_moves(source_type, source_no);
```

### 2.4 `aux_attachments` 辅料附件（文件落盘，DB 登记）

```sql
CREATE TABLE aux_attachments (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    aux_code        VARCHAR(32)  NOT NULL,
    file_name       VARCHAR(128) NOT NULL              COMMENT '原始文件名',
    file_type       VARCHAR(16)  NOT NULL              COMMENT 'pdf/doc/docx/jpg/jpeg/png',
    file_path       VARCHAR(255) NOT NULL              COMMENT '落盘相对路径 data/attachments/aux/<aux_code>/<uuid>.<ext>',
    file_size       INT          NOT NULL              COMMENT '字节数',
    sha256          CHAR(64)     NOT NULL              COMMENT '内容哈希(去重+完整性)',
    uploaded_by     VARCHAR(32)  NOT NULL DEFAULT '',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_auxat_aux FOREIGN KEY (aux_code) REFERENCES aux_materials(aux_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料附件(图纸/样张/规格书)';
```

**附件存储**：文件存 `data/attachments/aux/<aux_code>/`（compose 挂载卷，NAS 可备份），
DB 只存路径+哈希——与项目"文件系统+MySQL 各司其职"的哲学一致，不放 BLOB。
限制：pdf/doc/docx/jpg/jpeg/png，单文件 ≤ 10MB，sha256 去重。

### 2.5 与 products 的联动

- `products.label_paper`（VARCHAR）保持不动——它是"该产品用哪款标签"的引用。
- 种子迁移：把现有 3 个品种（R02502/R02505/R02506）灌进 `aux_materials`，
  `aux_code = LP-{label_paper}`（如 `LP-R02502`），name/shape 按 R/C 约定填。
- 标签需求计算的链条：`合同明细.material_id → products.label_paper → aux_materials.aux_code → aux_inventory`。

---

## 3. 标签需求提示（合同 → 生产）

**用量规则（待老板确认 Q1）**：默认 **每卷产品用 1 张标签纸**，即
某合同需要的标签数 = 合同明细里使用该标签的产品卷数之和。

**接口**：`GET /api/aux/label-demand?contract_no=SCxxx` 返回：

```json
{
  "contract_no": "SC20260730001",
  "lines": [
    {"aux_code": "LP-R02502", "name": "长方形标签", "required": 500,
     "in_stock": 1200, "shortage": 0}
  ],
  "all_sufficient": true
}
```

**提示时机**：
1. **近期（M3a）**：Streamlit 合同执行页加"标签需求"区块——录入端合同页没好之前就能用；
2. **正式（M3b）**：React 合同录入页（F2.6）保存合同时自动调用，
   缺料弹红字警告（不阻止保存，只提示——与项目 WARN 语义一致）。

**扣减时机（待老板确认 Q6，建议）**：合同推送生产 = **只提示+预留提醒，不扣库存**；
实际扣减发生在「辅料出库（生产领用）」操作时，流水带合同号可追溯到单。
避免合同改单/取消后库存反复回滚。

---

## 4. 接口与页面清单

### 4.1 API（FastAPI, 复用 db_writer 规则层模式）

| 接口 | 说明 |
|------|------|
| `GET /api/aux/materials?type=` | 辅料档案列表（含库存合计） |
| `POST /api/aux/materials` | 新增辅料（两段式 preview/insert 同款） |
| `POST /api/aux/materials/{code}/attachments` | 上传附件（multipart, ≤10MB, sha256 去重） |
| `GET /api/aux/attachments/{id}/download` | 下载附件 |
| `GET /api/aux/inventory` | 库存查询（按辅料/仓库/低库存筛选） |
| `POST /api/aux/stock-in` | 辅料入库（采购/调整） |
| `POST /api/aux/stock-out` | 辅料出库（生产领用，带合同号） |
| `GET /api/aux/moves?aux_code=` | 流水账 |
| `GET /api/aux/label-demand?contract_no=` | 合同标签需求测算 |

写库全部走「字段校验 → 事务（库存增减+流水同事务）→ 写后校验 → audit_logs」同款护栏。

### 4.2 React 录入端新菜单「辅料管理」

| 页面 | 功能 |
|------|------|
| 辅料档案 | 列表 + 新增表单（类型/形状/尺寸/供应商/安全库存）+ 附件上传/预览/下载 |
| 辅料入库 | 选辅料+仓库+数量+来源，确认后库存+流水 |
| 辅料出库 | 生产领用：选辅料+数量+关联合同号（自动带出该合同需求数做参照） |
| 辅料库存 | 当前存量计数、低库存红标、流水账、按合同用量统计 |

### 4.3 Streamlit（保留的查询侧）

- 合同执行页：加「标签需求」区块（M3a）
- 报表中心：辅料低库存预警条目（M4）

---

## 5. 阶段拆分

| 阶段 | 内容 | 验收 |
|------|------|------|
| **M1 档案** | 4 张表建表（01_schema + 迁移 SQL）+ R/C 品种种子化 + 档案接口 + React 辅料档案页（含附件上传） | 建 1 款标签纸、传 1 张 PDF 样张、能下载 |
| **M2 收发存** | 入库/出库/流水接口 + React 三页面 + 库存计数 | 入 1000 出 300 → 库存 700、流水 2 条、负数出库被拦 |
| **M3 需求提示** | label-demand 接口 + Streamlit 合同页提示（M3a）；React 合同页接入（M3b, 随 F2.6） | 合同 SC20260730001 算出需求数并显示库存够不够 |
| **M4 校验报表** | local_validator 加辅料一致性检查（库存=流水合计）+ 低库存预警上报表 + aux_type 扩展评估 | 校验器能抓住库存/流水不一致 |

M1+M2 是本次主体；M3a 顺手做（只读查询）；M3b 等合同录入页（F2.6）。

---

## 6. 待老板确认（开工前回答即可，都有默认值可先行）

| # | 问题 | 建议默认值 |
|---|------|-----------|
| Q1 | 标签纸用量规则：每卷产品固定 1 张？有没有一卷多张/一托一张的情况？ | 每卷 1 张 |
| Q2 | 库存计数单位：按"张"？采购按卷/包时怎么换算？ | 库存按张；pcs_per_unit 记录换算 |
| Q3 | 辅料仓库：单独建一个"辅料仓"，还是和成品同仓？ | warehouses 加 `AUX` 辅料仓 |
| Q4 | 辅料编码规则：沿用原 R/C 编号（LP-R02502）还是另起？ | LP-前缀+原编号，历史引用不断 |
| Q5 | 近期还有别的辅料要管吗（PE 膜/打包带/纸箱）？ | aux_type 预留 packaging/other |
| Q6 | 合同推送生产时只提示，还是直接预留扣减？ | 只提示不扣减，领用出库才扣 |
| ~~Q7~~ | ✅ **已定案（2026-08-01 老板）**：打线/米标/物料类型=工艺参数档案（不入库不管库存，米标=喷码后打印格式，纯工艺参数）；**用料=半成品原材料，后续开发独立模块管收发**，本模块只预留不做 | — |

**Q1-Q6 全部按默认执行（2026-08-01 老板确认）**：每卷 1 张标签 / 库存按张、pcs_per_unit 换算 /
warehouses 加 `AUX` 辅料仓 / 编码 LP-前缀+原编号 / aux_type 预留 packaging/other /
合同推送只提示不扣减、生产领用出库才扣。

---

## 7. 风险与注意

1. **schema 变更同步**：按项目规矩走"五处同步"——`sql/01_schema.sql` + 线上 ALTER 迁移脚本
   （`sql/migrations/2026-08-01_aux.sql`）+ DATA_MODEL.md + local_validator 表清单 + React 表单字段。
2. **NAS 部署**：附件目录 `data/attachments/` 要加进 compose 卷和备份清单（NAS_DEPLOY.md 同步）。
3. **历史不动**：products.label_paper 现有值不改，只新增 aux_materials 种子；两边编码靠 LP- 前缀映射。
4. **不外溢**：本模块不影响 16 步校验现有口径；M4 只新增检查项不改旧规则。

---

## 8. 初始数据与复测记录（2026-08-02）

- **初始数据**：`sql/migrations/2026-08-01_aux_seed.sql`（幂等）——AUX 辅料仓 + 3 个标签纸档案 + 全部在用辅料 × AUX 仓零库存行。收发存页开箱可见全部品种。
- **种子 bug 修正**：原种子先 DISTINCT 再 COUNT，把每个品种的产品引用数错算成 1；已改为直接 GROUP BY products（真实引用 R02502=2 / R02505=5 / R02506=5），两个迁移文件同步修正，存量档案 remark 已订正。
- **全流程复测（测试数据已清理）**：入库 1000 → 出库 300 → 余 700 → 超额出库拦截 ✓；非法来源类型拦截 ✓；label-demand 随库存联动 ✓；低库存预警 low_only ✓；附件上传/去重/下载 sha256 一致 ✓；新建档案+重复编码/非法类型拦截 ✓。
- **正式数据**：用户已上传首张真实标签样张 PDF（SELANG BENANG 28.9×11.6cm → LP-R02502），aux_attachments + data/attachments 勿删。
- **待老板补**：标签尺寸 width_mm/height_mm（老板指示可后补或不填）、min_stock 安全库存（填后低库存预警自动生效）、材质/默认供应商。
- **包装方式档案（M1c, 2026-08-02）**：products.package 全部 102 种历史包装种子进 aux_materials（PK-001..102 按引用频次冻结，纯档案不计量、不进收发存）；录入页"包装/标签纸"改辅料档案下拉（可手填新值）。手填新包装不自动建档，长期复用请在辅料档案页补建。

---

*文档版本：v1.1 | 创建：2026-08-01 | 更新：2026-08-02 | 状态：M1/M1b/M2/M3a 已上线，待 M3b(React 合同页)/M4(校验报表)*
