-- ============================================================
-- 进销存管理系统 - 建库建表脚本 (MySQL)
-- 文件: sql/01_schema.sql
-- 说明: 创建数据库及所有表结构(共9张主表 + 若干明细表)
--
-- 整体架构:
--   基础资料: products(物料) / warehouses(仓库) / suppliers(供应商) / customers(客户)
--   采购模块: purchase_orders + purchase_order_items
--   销售模块: sales_contracts + sales_contract_items
--   库存模块: inventory(当前库存) / stock_in(入库) / stock_out(出库) / stock_logs(流水)
--   发货模块: delivery_orders + delivery_order_items
--
-- 设计原则:
--   1. 主表 + 明细表 拆分: 业务单据存单据级信息, 明细存物料级信息
--   2. 状态字段: draft/confirmed/completed/cancelled
--   3. 编号规则: 人类可读单号(如 PO20260726001) + 内部自增ID
--   4. 金额用 DECIMAL, 不用 FLOAT
--   5. 物料字典(products)不带价格, 价格跟业务单据走
--
-- products 表字段来源:
--   [S1] = 物料.xlsx 的 Sheet1 (物料台账)
--   [S2] = 物料.xlsx 的 WXSC-Quot-260424-2.3 (报价单)
--   [新] = 新增的计算列
--
-- 单位约定:
--   * 米重(weight_per_meter) 统一存 g/m
--   * 内径(inner_diameter)   统一存 mm 数值; 英寸另存 inner_diameter_inch
--   * 外径(outer_diameter)   = inner_diameter + thickness * 2   (单位 mm)
--   * 内径x外径(id_x_od)     = 字符串拼接, 如 "6.5x10.5"
-- ============================================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS inventory_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE inventory_db;

-- ============================================================
-- 模块一: 基础资料
-- ============================================================

-- ------------------------------------------------------------
-- 1.1 商品/物料表 products
-- 类比: 货架上的商品目录, 这里是线管/管材的物料主数据
-- 注意: 本表只存"物料属性", 不存价格。价格在采购单/销售合同里。
-- ------------------------------------------------------------
DROP TABLE IF EXISTS products;
CREATE TABLE products (
    id                  INT AUTO_INCREMENT PRIMARY KEY COMMENT '内部ID',

    -- A. 标识与基本信息
    material_id         VARCHAR(32)  NOT NULL UNIQUE    COMMENT '物料编号(企业内部唯一) 如 M-001',
    customer_code       VARCHAR(32)  DEFAULT ''         COMMENT '客户编码 [S1] 如 W158/Q025',
    brand               VARCHAR(32)  DEFAULT ''         COMMENT '品牌 [S2] 如 华孚',
    product_category    VARCHAR(32)  DEFAULT ''         COMMENT '产品类别 [S1] 如 线管',
    material_type       VARCHAR(32)  DEFAULT ''         COMMENT '物料类型 [S2] 如 出口线管',
    spec                VARCHAR(32)  DEFAULT ''         COMMENT '规格 [S1] 如 1-1/4" 或 6.8',

    -- B. 尺寸参数
    inner_diameter      DECIMAL(8,2) DEFAULT NULL       COMMENT '内径(mm) [S1][S2] 统一毫米数值',
    inner_diameter_inch VARCHAR(16)  DEFAULT ''         COMMENT '内径(英寸) [S2] 如 1/4"',
    outer_diameter      DECIMAL(8,2) DEFAULT NULL       COMMENT '外径(mm) [新] = inner_diameter + thickness*2',
    id_x_od             VARCHAR(32)  DEFAULT ''         COMMENT '内径x外径 [S2][新] 如 6.5x10.5',
    thickness           DECIMAL(8,2) DEFAULT NULL       COMMENT '壁厚/厚度(mm) [S1][S2]',
    length              DECIMAL(10,2) DEFAULT NULL      COMMENT '长度(m) [S1][S2]',
    virtual_weight      DECIMAL(10,3) DEFAULT NULL      COMMENT '虚重(kg) [S1]',
    virtual_length      DECIMAL(10,2) DEFAULT NULL      COMMENT '虚米(m) [S1]',
    wire_spacing        VARCHAR(32)  DEFAULT ''         COMMENT '线距 [S1] 如 32根',

    -- C. 重量参数
    weight_per_meter    DECIMAL(10,3) DEFAULT NULL      COMMENT '米重(g/m) [S1][S2] 统一克/米',
    weight              DECIMAL(10,3) DEFAULT NULL      COMMENT '单件重量(kg) [S1][S2]',

    -- D. 外观与包装
    appearance_inner    DECIMAL(8,2) DEFAULT NULL       COMMENT '外观内径(mm) [S2]',
    appearance_outer    DECIMAL(8,2) DEFAULT NULL       COMMENT '外观外径(mm) [S2]',
    appearance_height   DECIMAL(8,2) DEFAULT NULL       COMMENT '外观高度(mm) [S2]',
    volume              DECIMAL(12,6) DEFAULT NULL      COMMENT '体积(原始值) [S2]',
    volume_subtotal     DECIMAL(12,6) DEFAULT NULL      COMMENT '体积小计(m³) [S2]',
    package             VARCHAR(32)  DEFAULT ''         COMMENT '包装 [S1] 如 PE膜',
    label_paper         VARCHAR(32)  DEFAULT ''         COMMENT '标签纸 [S2] 如 小(A)',
    material_used       VARCHAR(32)  DEFAULT ''         COMMENT '用料 [S1] 如 A25橙',
    wire_pattern        VARCHAR(32)  DEFAULT ''         COMMENT '打线 [S1] 如 红蓝双线',

    -- E. 盘型信息
    coil_type           VARCHAR(64)  DEFAULT ''         COMMENT '盘型 [S1] 如 内径30高7层',

    -- F. 其他
    pressure            DECIMAL(8,2) DEFAULT NULL       COMMENT '压力(Bar) [S2] 如 3/5/10',
    spray_code          VARCHAR(512) DEFAULT ''         COMMENT '喷码 [S1][S2] 喷在产品上的标识文字',
    meter_mark          VARCHAR(64)  DEFAULT ''         COMMENT '米标 [S2] 如 每1.02米一个循环米',
    remark              VARCHAR(512) DEFAULT ''         COMMENT '备注 [S1][S2]',

    -- G. 状态
    is_active           TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用(1启用/0停用)',
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料主数据';

CREATE INDEX idx_products_customer_code ON products(customer_code);
CREATE INDEX idx_products_category      ON products(product_category);
CREATE INDEX idx_products_spec          ON products(spec);

-- ------------------------------------------------------------
-- 1.2 仓库表 warehouses
-- 类比: 你有哪几个仓
-- ------------------------------------------------------------
DROP TABLE IF EXISTS warehouses;
CREATE TABLE warehouses (
    id           INT AUTO_INCREMENT PRIMARY KEY COMMENT '仓库内部ID',
    code         VARCHAR(32)  NOT NULL UNIQUE    COMMENT '仓库编号(如 WH-01)',
    name         VARCHAR(64)  NOT NULL           COMMENT '仓库名称',
    address      VARCHAR(255) DEFAULT ''         COMMENT '仓库地址',
    is_active    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用(1启用/0停用)',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓库目录';

-- ------------------------------------------------------------
-- 1.3 供应商表 suppliers
-- 类比: 进货的对方(卖原材料给你的厂家)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS suppliers;
CREATE TABLE suppliers (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '供应商内部ID',
    code            VARCHAR(32)  NOT NULL UNIQUE    COMMENT '供应商编号(如 SUP-001)',
    name            VARCHAR(128) NOT NULL           COMMENT '供应商名称',
    contact_person  VARCHAR(32)  DEFAULT ''         COMMENT '联系人',
    phone           VARCHAR(32)  DEFAULT ''         COMMENT '电话',
    address         VARCHAR(255) DEFAULT ''         COMMENT '地址',
    bank_account    VARCHAR(64)  DEFAULT ''         COMMENT '银行账号',
    company_profiles TEXT         DEFAULT NULL      COMMENT '供应商公司资料全文 (合同模板调取, 可多行, 含中文开票信息)',
    billing_profiles TEXT         DEFAULT NULL      COMMENT '供应商开票/收款资料全文 (合同模板调取, 可多行, 含外币账户信息)',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='供应商名录';

-- ------------------------------------------------------------
-- 1.4 客户表 customers
-- 类比: 卖货的对方(买你成品的客户)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '客户内部ID',
    code            VARCHAR(32)  NOT NULL UNIQUE    COMMENT '客户编号(如 C-001)',
    name            VARCHAR(128) NOT NULL           COMMENT '客户名称',
    contact_person  VARCHAR(32)  DEFAULT ''         COMMENT '联系人',
    phone           VARCHAR(32)  DEFAULT ''         COMMENT '电话',
    address         VARCHAR(255) DEFAULT ''         COMMENT '收货地址',
    bank_account    VARCHAR(64)  DEFAULT ''         COMMENT '银行账号',
    brand_name      VARCHAR(64)  DEFAULT ''         COMMENT '客户品牌名 (如 PAGODA), 用于产品/包装标识',
    company_profiles TEXT         DEFAULT NULL      COMMENT '客户公司资料全文 (合同模板调取, 可多行)',
    billing_profiles TEXT         DEFAULT NULL      COMMENT '客户开票/收款资料全文 (合同模板调取, 可多行)',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户名录';

-- ============================================================
-- 模块二: 采购管理
-- ============================================================

-- ------------------------------------------------------------
-- 2.1 采购单主表 purchase_orders
-- 类比: 跟供应商签的进货单
-- 一个采购单可以包含多种物料
-- ------------------------------------------------------------
DROP TABLE IF EXISTS purchase_orders;
CREATE TABLE purchase_orders (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '采购单内部ID',
    po_no           VARCHAR(32)  NOT NULL UNIQUE    COMMENT '采购单号(如 PO20260726001)',
    supplier_id     INT          NOT NULL           COMMENT '供应商ID',
    order_date      DATE         NOT NULL           COMMENT '下单日期',
    expected_date   DATE         DEFAULT NULL       COMMENT '预计到货日期',
    total_amount    DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '采购总金额(CNY)',
    status          ENUM('draft','confirmed','partial_received','received','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/部分到货/已全部到货/已取消',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采购单主表';

CREATE INDEX idx_po_no        ON purchase_orders(po_no);
CREATE INDEX idx_po_supplier  ON purchase_orders(supplier_id);
CREATE INDEX idx_po_status    ON purchase_orders(status);

-- ------------------------------------------------------------
-- 2.2 采购单明细表 purchase_order_items
-- 类比: 采购单的"商品行", 一行一种物料
-- ------------------------------------------------------------
DROP TABLE IF EXISTS purchase_order_items;
CREATE TABLE purchase_order_items (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    po_id           INT          NOT NULL           COMMENT '采购单ID',
    product_id      INT          NOT NULL           COMMENT '物料ID',
    quantity        INT          NOT NULL           COMMENT '采购数量(件/卷)',
    unit_price      DECIMAL(12,2) NOT NULL          COMMENT '采购单价(CNY/件)',
    subtotal        DECIMAL(14,2) NOT NULL          COMMENT '小计金额(CNY) = quantity*unit_price',
    volume_subtotal DECIMAL(10,4) DEFAULT 0.0000    COMMENT '体积小计(CBM) = 单件体积 × quantity',
    received_qty    INT          NOT NULL DEFAULT 0 COMMENT '已收货数量',
    remark          VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_poi_po      FOREIGN KEY (po_id)      REFERENCES purchase_orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_poi_product FOREIGN KEY (product_id) REFERENCES products(id),

    UNIQUE KEY uk_poi_po_product (po_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采购单明细';

CREATE INDEX idx_poi_po       ON purchase_order_items(po_id);
CREATE INDEX idx_poi_product  ON purchase_order_items(product_id);

-- ============================================================
-- 模块三: 销售合同管理
-- ============================================================

-- ------------------------------------------------------------
-- 3.1 销售合同主表 sales_contracts
-- 类比: 跟客户签的销售合同
-- 一个合同可以包含多种物料, 每种物料有约定的数量、单价、交期
-- ------------------------------------------------------------
DROP TABLE IF EXISTS sales_contracts;
CREATE TABLE sales_contracts (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '合同内部ID',
    contract_no     VARCHAR(32)  NOT NULL UNIQUE    COMMENT '合同号(如 SC20260726001)',
    customer_id     INT          NOT NULL           COMMENT '客户ID',
    sign_date       DATE         NOT NULL           COMMENT '签订日期',
    delivery_deadline DATE       DEFAULT NULL       COMMENT '交货截止日期',
    -- 金额 (外贸默认外币计价, 记账本位币 CNY)
    total_amount    DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '合同总金额(原币种)',
    currency        VARCHAR(3)   NOT NULL DEFAULT 'USD' COMMENT '币种(ISO 4217 三字母): USD/EUR/IDR...',
    exchange_rate   DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT '签约日汇率(原币种→CNY)',
    total_amount_cny DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '合同总金额(折算CNY) = total_amount × exchange_rate',
    -- 贸易术语 (Incoterms 2020)
    trade_terms     ENUM('FOB','CIF','CFR','EXW') NOT NULL DEFAULT 'FOB' COMMENT '贸易术语: FOB/CIF/CFR/EXW',
    port_loading    VARCHAR(64)  DEFAULT ''         COMMENT '装运港(如 Qingdao)',
    port_discharge  VARCHAR(64)  DEFAULT ''         COMMENT '卸货港(如 Jakarta)',
    freight         DECIMAL(12,2) NOT NULL DEFAULT 0.00 COMMENT '运费(CNY, 仅 CIF/CFR 有)',
    insurance       DECIMAL(12,2) NOT NULL DEFAULT 0.00 COMMENT '保险费(CNY, 仅 CIF 有)',
    -- 状态
    status          ENUM('draft','confirmed','delivering','completed','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/发货中/已完成/已取消',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_sc_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售合同主表';

CREATE INDEX idx_sc_no        ON sales_contracts(contract_no);
CREATE INDEX idx_sc_customer  ON sales_contracts(customer_id);
CREATE INDEX idx_sc_status    ON sales_contracts(status);

-- ------------------------------------------------------------
-- 3.2 销售合同明细表 sales_contract_items
-- 类比: 合同的"商品行"
-- 重点字段: quantity(合同数) / delivered_qty(已发数) / pending_qty(未发数)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS sales_contract_items;
CREATE TABLE sales_contract_items (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    contract_id     INT          NOT NULL           COMMENT '合同ID',
    product_id      INT          NOT NULL           COMMENT '物料ID',
    quantity        INT          NOT NULL           COMMENT '合同数量(件/卷)',
    unit_price      DECIMAL(12,2) NOT NULL          COMMENT '合同单价(CNY/件)',
    subtotal        DECIMAL(14,2) NOT NULL          COMMENT '小计金额(CNY) = quantity*unit_price',
    volume_subtotal DECIMAL(10,4) DEFAULT 0.0000    COMMENT '体积小计(CBM) = 单件体积 × quantity',
    delivered_qty   INT          NOT NULL DEFAULT 0 COMMENT '已发货数量(由发货单回写)',
    remark          VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_sci_contract FOREIGN KEY (contract_id) REFERENCES sales_contracts(id) ON DELETE CASCADE,
    CONSTRAINT fk_sci_product  FOREIGN KEY (product_id)  REFERENCES products(id),

    UNIQUE KEY uk_sci_contract_product (contract_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='销售合同明细';

CREATE INDEX idx_sci_contract ON sales_contract_items(contract_id);
CREATE INDEX idx_sci_product  ON sales_contract_items(product_id);

-- ============================================================
-- 模块四: 库存管理
-- ============================================================

-- ------------------------------------------------------------
-- 4.1 当前库存表 inventory
-- 类比: 账本上"现在某仓某物料还剩多少"
-- 一个物料 + 一个仓库 = 一行记录
-- ------------------------------------------------------------
DROP TABLE IF EXISTS inventory;
CREATE TABLE inventory (
    id           INT AUTO_INCREMENT PRIMARY KEY COMMENT '库存记录ID',
    product_id   INT          NOT NULL COMMENT '物料ID',
    warehouse_id INT          NOT NULL COMMENT '仓库ID',
    quantity     INT          NOT NULL DEFAULT 0 COMMENT '当前库存数量(件/卷)',
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',

    UNIQUE KEY uk_product_warehouse (product_id, warehouse_id),

    CONSTRAINT fk_inv_product   FOREIGN KEY (product_id)   REFERENCES products(id),
    CONSTRAINT fk_inv_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='当前库存';

CREATE INDEX idx_inv_product   ON inventory(product_id);
CREATE INDEX idx_inv_warehouse ON inventory(warehouse_id);

-- ------------------------------------------------------------
-- 4.2 入库单主表 stock_in
-- 类比: 货物实际进仓的凭证
-- 来源可能是: 采购到货 / 生产入库 / 调拨入库 / 退货入库
-- ------------------------------------------------------------
DROP TABLE IF EXISTS stock_in;
CREATE TABLE stock_in (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '入库单内部ID',
    in_no           VARCHAR(32)  NOT NULL UNIQUE    COMMENT '入库单号(如 IN20260726001)',
    in_type         ENUM('purchase','production','transfer','return')
                                NOT NULL DEFAULT 'purchase' COMMENT '入库类型: 采购/生产/调拨/退货',
    warehouse_id    INT          NOT NULL           COMMENT '入库仓库ID',
    po_id           INT          DEFAULT NULL       COMMENT '关联采购单ID(采购入库时填)',
    operator        VARCHAR(32)  DEFAULT ''         COMMENT '操作人',
    in_date         DATE         NOT NULL           COMMENT '入库日期',
    status          ENUM('draft','confirmed','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/已取消',
    transfer_ref    VARCHAR(32)  DEFAULT NULL       COMMENT '调拨关联号(调拨入库时填, 跟配对的 stock_out 同一个号, 如 TR20260729001)',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_si_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    CONSTRAINT fk_si_po        FOREIGN KEY (po_id)        REFERENCES purchase_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='入库单主表';

CREATE INDEX idx_si_no        ON stock_in(in_no);
CREATE INDEX idx_si_warehouse ON stock_in(warehouse_id);
CREATE INDEX idx_si_po        ON stock_in(po_id);
CREATE INDEX idx_si_transfer  ON stock_in(transfer_ref);

-- ------------------------------------------------------------
-- 4.3 入库单明细表 stock_in_items
-- ------------------------------------------------------------
DROP TABLE IF EXISTS stock_in_items;
CREATE TABLE stock_in_items (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    stock_in_id     INT          NOT NULL           COMMENT '入库单ID',
    product_id      INT          NOT NULL           COMMENT '物料ID',
    quantity        INT          NOT NULL           COMMENT '入库数量(件/卷)',
    remark          VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_sii_si      FOREIGN KEY (stock_in_id) REFERENCES stock_in(id) ON DELETE CASCADE,
    CONSTRAINT fk_sii_product FOREIGN KEY (product_id)  REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='入库单明细';

CREATE INDEX idx_sii_si      ON stock_in_items(stock_in_id);
CREATE INDEX idx_sii_product ON stock_in_items(product_id);

-- ------------------------------------------------------------
-- 4.4 出库单主表 stock_out
-- 类比: 货物实际出仓的凭证
-- 来源可能是: 销售发货 / 生产领料 / 调拨出库 / 报废
-- ------------------------------------------------------------
DROP TABLE IF EXISTS stock_out;
CREATE TABLE stock_out (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '出库单内部ID',
    out_no          VARCHAR(32)  NOT NULL UNIQUE    COMMENT '出库单号(如 OUT20260726001)',
    out_type        ENUM('sale','production','transfer','scrap')
                                NOT NULL DEFAULT 'sale' COMMENT '出库类型: 销售/生产/调拨/报废',
    warehouse_id    INT          NOT NULL           COMMENT '出库仓库ID',
    delivery_id     INT          DEFAULT NULL       COMMENT '关联发货单ID(销售出库时填)',
    operator        VARCHAR(32)  DEFAULT ''         COMMENT '操作人',
    out_date        DATE         NOT NULL           COMMENT '出库日期',
    status          ENUM('draft','confirmed','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/已取消',
    transfer_ref    VARCHAR(32)  DEFAULT NULL       COMMENT '调拨关联号(调拨出库时填, 跟配对的 stock_in 同一个号, 如 TR20260729001)',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_so_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    CONSTRAINT fk_so_delivery FOREIGN KEY (delivery_id)   REFERENCES delivery_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单主表';

CREATE INDEX idx_so_no        ON stock_out(out_no);
CREATE INDEX idx_so_warehouse ON stock_out(warehouse_id);
CREATE INDEX idx_so_delivery  ON stock_out(delivery_id);
CREATE INDEX idx_so_transfer  ON stock_out(transfer_ref);

-- ------------------------------------------------------------
-- 4.5 出库单明细表 stock_out_items
-- ------------------------------------------------------------
DROP TABLE IF EXISTS stock_out_items;
CREATE TABLE stock_out_items (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    stock_out_id    INT          NOT NULL           COMMENT '出库单ID',
    product_id      INT          NOT NULL           COMMENT '物料ID',
    quantity        INT          NOT NULL           COMMENT '出库数量(件/卷)',
    remark          VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_soi_so      FOREIGN KEY (stock_out_id) REFERENCES stock_out(id) ON DELETE CASCADE,
    CONSTRAINT fk_soi_product FOREIGN KEY (product_id)   REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出库单明细';

CREATE INDEX idx_soi_so      ON stock_out_items(stock_out_id);
CREATE INDEX idx_soi_product ON stock_out_items(product_id);

-- ------------------------------------------------------------
-- 4.6 出入库流水表 stock_logs
-- 类比: 统一的流水账本
-- 所有入库/出库操作都会自动往这里写一条, 用于对账和追溯
-- inventory 表是"结果", stock_logs 表是"原因"
-- ------------------------------------------------------------
DROP TABLE IF EXISTS stock_logs;
CREATE TABLE stock_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '流水ID',
    product_id      INT          NOT NULL COMMENT '物料ID',
    warehouse_id    INT          NOT NULL COMMENT '仓库ID',
    change_qty      INT          NOT NULL COMMENT '变动数量(入库为正,出库为负)',
    after_qty       INT          NOT NULL COMMENT '变动后该仓该物料库存',
    source_type     ENUM('stock_in','stock_out','adjust')
                                NOT NULL COMMENT '来源类型: 入库单/出库单/盘点调整',
    source_id       INT          DEFAULT NULL COMMENT '来源单据ID(关联stock_in/stock_out的主键)',
    source_no       VARCHAR(32)  DEFAULT ''  COMMENT '来源单号(冗余, 方便查询)',
    remark          VARCHAR(255) DEFAULT ''  COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发生时间',

    CONSTRAINT fk_log_product   FOREIGN KEY (product_id)   REFERENCES products(id),
    CONSTRAINT fk_log_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='出入库流水';

CREATE INDEX idx_log_product_warehouse_time ON stock_logs(product_id, warehouse_id, created_at);
CREATE INDEX idx_log_source                ON stock_logs(source_type, source_id);

-- ============================================================
-- 模块五: 发货管理
-- ============================================================

-- ------------------------------------------------------------
-- 5.1 发货单主表 delivery_orders
-- 类比: 给客户送货的凭证
-- 一次发货可能对应多个合同明细(同一客户多个合同的货一起发)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS delivery_orders;
CREATE TABLE delivery_orders (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '发货单内部ID',
    delivery_no     VARCHAR(32)  NOT NULL UNIQUE    COMMENT '发货单号(如 DN20260726001)',
    customer_id     INT          NOT NULL           COMMENT '客户ID',
    delivery_date   DATE         NOT NULL           COMMENT '发货日期',
    receiver        VARCHAR(32)  DEFAULT ''         COMMENT '收货人',
    receiver_phone  VARCHAR(32)  DEFAULT ''         COMMENT '收货电话',
    receiver_address VARCHAR(255) DEFAULT ''        COMMENT '收货地址',
    transport_no    VARCHAR(64)  DEFAULT ''         COMMENT '物流单号',
    status          ENUM('draft','confirmed','shipped','delivered','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/已装船/客户已签收/已取消',
    remark          VARCHAR(512) DEFAULT ''         COMMENT '备注',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_do_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='发货单主表';

CREATE INDEX idx_do_no       ON delivery_orders(delivery_no);
CREATE INDEX idx_do_customer ON delivery_orders(customer_id);
CREATE INDEX idx_do_status   ON delivery_orders(status);

-- ------------------------------------------------------------
-- 5.2 发货单明细表 delivery_order_items
-- 类比: 发货单的"商品行"
-- 每行关联一个合同明细, 发货后回写合同明细的 delivered_qty
--
-- ⚠️ 短装/超装设计 (2026-07 升级):
--   quantity         = 商务承诺数 (合同数, 不改)
--   actual_quantity  = 实际装柜数 (装柜后填, 默认=quantity)
--   short_qty        = 数据库自动算 (quantity - actual_quantity)
--
-- 两套账机制详见 .claude/skills/trade-documents/SKILL.md
-- ------------------------------------------------------------
DROP TABLE IF EXISTS delivery_order_items;
CREATE TABLE delivery_order_items (
    id                  INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    delivery_id         INT          NOT NULL           COMMENT '发货单ID',
    contract_item_id    INT          DEFAULT NULL       COMMENT '关联合同明细ID(回写已发数量用)',
    product_id          INT          NOT NULL           COMMENT '物料ID',
    quantity            INT          NOT NULL           COMMENT '计划发货数量(件/卷, 商务承诺)',
    actual_quantity     INT          NOT NULL DEFAULT 0 COMMENT '实际发货数量(装柜后填, 默认=quantity, 短装时<quantity)',
    short_qty           INT          GENERATED ALWAYS AS (quantity - actual_quantity) STORED COMMENT '短装数(自动算=计划-实际, 正=短装, 负=超装)',
    volume_subtotal     DECIMAL(10,4) DEFAULT 0.0000    COMMENT '体积小计(CBM) = 单件体积 × actual_quantity',
    remark              VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_doi_delivery     FOREIGN KEY (delivery_id)      REFERENCES delivery_orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_doi_contract_item FOREIGN KEY (contract_item_id) REFERENCES sales_contract_items(id),
    CONSTRAINT fk_doi_product      FOREIGN KEY (product_id)       REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='发货单明细';

CREATE INDEX idx_doi_delivery      ON delivery_order_items(delivery_id);
CREATE INDEX idx_doi_contract_item ON delivery_order_items(contract_item_id);
CREATE INDEX idx_doi_product       ON delivery_order_items(product_id);

-- ============================================================
-- 模块六: 报关 (外贸出口专用)
-- ============================================================
-- 设计原则: "两套并行账"
--   合同账 (delivery_orders): 承诺值, 给客户/财务看
--   报关账 (shipping_records): 实际值, 给海关/银行看
-- 两套账允许 ±5% 差异 (UCP600 国际惯例), 用 credit_notes 衔接
-- 详见 .claude/skills/trade-documents/SKILL.md
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 6.1 报关单据主表 shipping_records
-- 用途: 装柜后记录实际报关数据, 跟发货单解耦
-- 一张发货单可以分多次装船 (partial shipment), 每次一条 shipping_record
-- 数据源: 装柜后仓管/报关员按实际填, 是 Packing List + Commercial Invoice 的数据源
-- ------------------------------------------------------------
DROP TABLE IF EXISTS shipping_records;
CREATE TABLE shipping_records (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    shipping_no      VARCHAR(32)   NOT NULL UNIQUE  COMMENT '报关单号(SH2026-001)',
    delivery_id      INT           NOT NULL         COMMENT '关联发货单ID',
    shipping_date    DATE          NOT NULL         COMMENT '装船日期',
    container_no     VARCHAR(32)   DEFAULT ''       COMMENT '集装箱号',
    seal_no          VARCHAR(32)   DEFAULT ''       COMMENT '封条号',
    vessel           VARCHAR(64)   DEFAULT ''       COMMENT '船名/航次',
    -- 报关核心数据 (按实际装柜填)
    total_pkgs       INT           NOT NULL DEFAULT 0  COMMENT '实际总件数',
    total_gross_wt   DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '总毛重(kg)',
    total_net_wt     DECIMAL(10,2) NOT NULL DEFAULT 0  COMMENT '总净重(kg)',
    total_cbm        DECIMAL(10,4) NOT NULL DEFAULT 0  COMMENT '总体积(CBM)',
    -- CI 金额四件套 (原币种 + 当期汇率 + 折算 CNY)
    total_amount     DECIMAL(12,2) NOT NULL DEFAULT 0  COMMENT 'CI总额(原币种, 一般与合同同币种)',
    currency         VARCHAR(3)   NOT NULL DEFAULT 'USD' COMMENT '币种(ISO 4217): USD/EUR/IDR...',
    exchange_rate    DECIMAL(10,4) NOT NULL DEFAULT 0  COMMENT '当期汇率(按 shipping_date 所在月查 exchange_rates)',
    total_amount_cny DECIMAL(12,2) NOT NULL DEFAULT 0  COMMENT 'CI总额(折算CNY) = total_amount × exchange_rate',
    -- 状态
    status           ENUM('draft','customs_cleared','closed','cancelled')
                     NOT NULL DEFAULT 'draft'         COMMENT '状态: 草稿/已报关/已结关/已取消',
    remark           VARCHAR(512)  DEFAULT ''       COMMENT '备注',
    created_at       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_sr_delivery FOREIGN KEY (delivery_id) REFERENCES delivery_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报关单据主表(实际装柜数据)';

CREATE INDEX idx_sr_no       ON shipping_records(shipping_no);
CREATE INDEX idx_sr_delivery ON shipping_records(delivery_id);
CREATE INDEX idx_sr_status   ON shipping_records(status);

-- ------------------------------------------------------------
-- 6.2 报关单据明细表 shipping_record_items
-- 用途: 报关清单 (Packing List + Commercial Invoice 数据源)
-- 关键字段: 唛头/毛重/净重/件数/体积/单价 - 报关必备
-- ------------------------------------------------------------
DROP TABLE IF EXISTS shipping_record_items;
CREATE TABLE shipping_record_items (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    shipping_id      INT          NOT NULL          COMMENT '报关单ID',
    product_id       INT          NOT NULL          COMMENT '物料ID',
    -- 计划 vs 实际
    planned_qty      INT          NOT NULL DEFAULT 0 COMMENT '计划数量(从发货单带过来)',
    actual_qty       INT          NOT NULL DEFAULT 0 COMMENT '实际装柜数量(必填)',
    -- 报关必备字段
    shipping_mark    VARCHAR(128) DEFAULT ''        COMMENT '唛头(包装外标识)',
    gross_weight_per DECIMAL(8,2) DEFAULT 0         COMMENT '单件毛重(kg, 含包装)',
    net_weight_per   DECIMAL(8,2) DEFAULT 0         COMMENT '单件净重(kg, 不含包装)',
    unit_volume      DECIMAL(10,4) DEFAULT 0        COMMENT '单件体积(CBM)',
    -- 金额 (Commercial Invoice 需要)
    unit_price_usd   DECIMAL(10,2) DEFAULT 0        COMMENT '单价(USD/件)',
    subtotal_usd     DECIMAL(12,2) DEFAULT 0        COMMENT '小计(USD) = actual_qty × unit_price_usd',
    remark           VARCHAR(255) DEFAULT ''        COMMENT '备注',

    CONSTRAINT fk_sri_shipping FOREIGN KEY (shipping_id) REFERENCES shipping_records(id) ON DELETE CASCADE,
    CONSTRAINT fk_sri_product  FOREIGN KEY (product_id)  REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报关单据明细(Packing List + CI 数据源)';

CREATE INDEX idx_sri_shipping ON shipping_record_items(shipping_id);
CREATE INDEX idx_sri_product  ON shipping_record_items(product_id);

-- ------------------------------------------------------------
-- 6.3 贷记单/差异处理主表 credit_notes
-- 用途: 处理短装/超装差异, 衔接"合同账"与"报关账"
-- 4 种 resolution: pending(待定) / replenish(下次补发) / refund(退款) / writeoff(注销)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS credit_notes;
CREATE TABLE credit_notes (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    cn_no            VARCHAR(32)   NOT NULL UNIQUE  COMMENT '贷记单号(CN2026-001)',
    shipping_id      INT           NOT NULL         COMMENT '关联报关单',
    contract_item_id INT           NOT NULL         COMMENT '关联合同明细',
    product_id       INT           NOT NULL         COMMENT '物料ID',
    -- 差异金额四件套
    diff_qty         INT           NOT NULL         COMMENT '差异数量(正=短装, 负=超装)',
    diff_amount      DECIMAL(12,2) NOT NULL         COMMENT '差异金额(原币种)',
    currency         VARCHAR(3)   NOT NULL DEFAULT 'USD' COMMENT '币种(跟合同一致)',
    exchange_rate    DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT '当期汇率(按报关单 shipping_date 所在月)',
    diff_amount_cny  DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '差异金额(折算CNY) = diff_amount × exchange_rate',
    -- 处理方式
    resolution       ENUM('pending','replenish','refund','writeoff')
                     NOT NULL DEFAULT 'pending'     COMMENT '处理: 待定/补发/退款/注销',
    resolved_at      DATE          DEFAULT NULL     COMMENT '处理日期',
    remark           VARCHAR(512)  DEFAULT ''       COMMENT '备注',
    created_at       DATETIME      DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_cn_shipping      FOREIGN KEY (shipping_id)      REFERENCES shipping_records(id),
    CONSTRAINT fk_cn_contract_item FOREIGN KEY (contract_item_id) REFERENCES sales_contract_items(id),
    CONSTRAINT fk_cn_product       FOREIGN KEY (product_id)       REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='贷记单/差异处理单';

CREATE INDEX idx_cn_no         ON credit_notes(cn_no);
CREATE INDEX idx_cn_shipping   ON credit_notes(shipping_id);
CREATE INDEX idx_cn_resolution ON credit_notes(resolution);

-- ============================================================
-- 模块七: 应收账款 (外贸财务阶段一 - 最小可用骨架)
-- ============================================================
-- 设计原则:
--   1. 记账本位币 CNY, 业务发生按原币种记, 系统自动折算 CNY
--   2. 汇率按月固定 (月初录入一条, 整月用同一汇率)
--   3. 当前只做"客户收款", 对供应商付款留阶段二
-- 详见 .claude/skills/payment-receivable/SKILL.md
-- ------------------------------------------------------------

-- 7.1 汇率表 exchange_rates
-- 用途: 每月初录入一次, 整月用同一汇率折算外币
-- 规则: 1 原币种 = rate_to_cny 人民币 (如 USD=7.20 表示 1 USD = 7.20 CNY)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS exchange_rates;
CREATE TABLE exchange_rates (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    currency        VARCHAR(3)   NOT NULL          COMMENT '币种(ISO 4217): USD/EUR/IDR...',
    rate_to_cny     DECIMAL(10,4) NOT NULL         COMMENT '汇率(1 原币种 = ? CNY)',
    effective_date  DATE         NOT NULL          COMMENT '生效日期(每月1号)',
    source          VARCHAR(32)  DEFAULT 'manual'  COMMENT '来源: 中国银行中间价/manual',
    remark          VARCHAR(255) DEFAULT ''        COMMENT '备注',
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_currency_effective (currency, effective_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='汇率表(按月维护)';

CREATE INDEX idx_er_currency_date ON exchange_rates(currency, effective_date);

-- 7.2 收款单 receipts
-- 用途: 客户每次付款记一笔, 系统按 paid_date 自动查汇率折算 CNY
-- 关联: 可关联合同/报关单/发货单 (按业务场景选)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS receipts;
CREATE TABLE receipts (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    receipt_no      VARCHAR(32)  NOT NULL UNIQUE   COMMENT '收款单号(如 RC20260815001)',
    customer_id     INT          NOT NULL          COMMENT '客户ID',
    contract_id     INT          DEFAULT NULL      COMMENT '关联合同ID(可空, 预收款时无合同)',
    shipping_id     INT          DEFAULT NULL      COMMENT '关联报关单ID(可空)',
    delivery_id     INT          DEFAULT NULL      COMMENT '关联发货单ID(可空)',
    -- 金额
    amount          DECIMAL(14,2) NOT NULL         COMMENT '收款金额(原币种)',
    currency        VARCHAR(3)   NOT NULL DEFAULT 'USD' COMMENT '币种',
    exchange_rate   DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT '汇率(按 paid_date 查表自动填)',
    amount_cny      DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '折算CNY = amount × exchange_rate',
    -- 收款信息
    paid_date       DATE         NOT NULL          COMMENT '实际到账日期',
    pay_method      ENUM('T/T','L/C','D/P','D/A','other')
                    NOT NULL DEFAULT 'T/T'         COMMENT '付款方式',
    bank_ref        VARCHAR(64)  DEFAULT ''        COMMENT '银行水单号/参考号',
    -- 状态
    status          ENUM('draft','confirmed','cancelled')
                    NOT NULL DEFAULT 'draft'       COMMENT '状态: 草稿/已确认/已取消',
    remark          VARCHAR(512) DEFAULT ''        COMMENT '备注',
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_rc_customer  FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT fk_rc_contract  FOREIGN KEY (contract_id) REFERENCES sales_contracts(id),
    CONSTRAINT fk_rc_shipping  FOREIGN KEY (shipping_id) REFERENCES shipping_records(id),
    CONSTRAINT fk_rc_delivery  FOREIGN KEY (delivery_id) REFERENCES delivery_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='收款单(客户付款)';

CREATE INDEX idx_rc_no         ON receipts(receipt_no);
CREATE INDEX idx_rc_customer   ON receipts(customer_id);
CREATE INDEX idx_rc_contract   ON receipts(contract_id);
CREATE INDEX idx_rc_paid_date  ON receipts(paid_date);
CREATE INDEX idx_rc_status     ON receipts(status);

-- ============================================================
-- 模块八: 审计日志 (阶段一空壳, 阶段二接业务)
-- ============================================================
-- 用途: 追溯谁在什么时候改了什么数据
-- 阶段一: 只建表, 不写入 (业务逻辑后期补)
-- 阶段二: 给所有敏感表加 INSERT/UPDATE/DELETE 拦截, 写入本表
-- ------------------------------------------------------------
DROP TABLE IF EXISTS audit_logs;
CREATE TABLE audit_logs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
    table_name      VARCHAR(64) NOT NULL              COMMENT '被改的表名',
    record_id       INT         NOT NULL              COMMENT '被改的记录ID',
    action          ENUM('INSERT','UPDATE','DELETE') NOT NULL COMMENT '操作类型',
    old_values      TEXT        DEFAULT NULL          COMMENT '旧值(JSON)',
    new_values      TEXT        DEFAULT NULL          COMMENT '新值(JSON)',
    operator        VARCHAR(32) DEFAULT ''            COMMENT '操作人',
    created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',

    INDEX idx_audit_table_record (table_name, record_id),
    INDEX idx_audit_operator_time (operator, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计日志(阶段一空壳)';

-- ============================================================
-- 模块九: 报价管理 (单价 = 单卷重量 KG × 报价系数 USD/KG)
-- ============================================================
-- 流程: 简要报价(brief) → 正式 QT form → 销售合同 PI(转单后回填)
-- 遵循 R1 金额四件套 (amount + currency + exchange_rate + amount_cny)
-- 遵循 R10 报价定价铁律 (price_coefficient 是定价基准, 不存绝对价)
-- 详见 docs/BUSINESS_RULES.md R10
-- ------------------------------------------------------------

-- 9.1 报价参数表 quotation_params (全局键值对)
-- 用途: 存全局参数, 如默认汇率/默认币种/报价有效期天数
-- ------------------------------------------------------------
DROP TABLE IF EXISTS quotation_params;
CREATE TABLE quotation_params (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '参数ID',
    param_key       VARCHAR(64)  NOT NULL UNIQUE   COMMENT '参数键(如 exchange_rate/default_currency/valid_days)',
    param_value     VARCHAR(128) NOT NULL          COMMENT '参数值',
    description     VARCHAR(255) DEFAULT ''        COMMENT '说明',
    effective_date  DATE         DEFAULT NULL      COMMENT '生效日期',
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价参数表(全局键值对)';

CREATE INDEX idx_qp_key ON quotation_params(param_key);

-- 9.2 报价主表 quotations (简要报价 + 正式 QT 共用, 状态区分)
-- 关键字段: quote_type(brief/formal) / version(简要报价多版本) / parent_quote_id(派生源)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS quotations;
CREATE TABLE quotations (
    id                  INT AUTO_INCREMENT PRIMARY KEY COMMENT '报价内部ID',
    quote_no            VARCHAR(32)  NOT NULL UNIQUE   COMMENT '报价号(如 QT20260729001)',
    customer_id         INT          NOT NULL          COMMENT '客户ID',
    quote_type          ENUM('brief','formal') NOT NULL DEFAULT 'brief' COMMENT '类型: brief简要报价/formal正式QT',
    parent_quote_id     INT          DEFAULT NULL      COMMENT '派生源(正式QT从哪个简要报价派生)',
    version             INT          NOT NULL DEFAULT 1 COMMENT '版本(简要报价多版本)',
    quote_date          DATE         NOT NULL          COMMENT '报价日期',
    valid_until         DATE         DEFAULT NULL      COMMENT '报价有效期至',
    -- 金额四件套(R1)
    total_amount        DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '报价总金额(原币种)',
    currency            VARCHAR(3)   NOT NULL DEFAULT 'USD' COMMENT '币种(ISO 4217): USD/EUR/IDR...',
    exchange_rate       DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT '汇率(原币种→CNY)',
    total_amount_cny    DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '报价总金额(折算CNY) = total_amount × exchange_rate',
    status              ENUM('draft','sent','confirmed','converted','cancelled')
                        NOT NULL DEFAULT 'draft'      COMMENT '状态: 草稿/已发/已确认/已转合同/已取消',
    converted_contract_id INT        DEFAULT NULL      COMMENT '转成的销售合同ID(转后回填)',
    remark              VARCHAR(512) DEFAULT ''        COMMENT '备注',
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    CONSTRAINT fk_quo_customer FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT fk_quo_parent   FOREIGN KEY (parent_quote_id) REFERENCES quotations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价主表(简要报价+正式QT)';

CREATE INDEX idx_quo_no       ON quotations(quote_no);
CREATE INDEX idx_quo_customer ON quotations(customer_id);
CREATE INDEX idx_quo_type     ON quotations(quote_type);
CREATE INDEX idx_quo_status   ON quotations(status);

-- 9.3 报价明细表 quotation_items
-- 定价公式: unit_price = weight_per_unit × price_coefficient (USD/KG)
-- 派生字段(total_weight/unit_price/subtotal/total_volume)下一步 DERIVED_RULES 实现, 本步先建列
-- ------------------------------------------------------------
DROP TABLE IF EXISTS quotation_items;
CREATE TABLE quotation_items (
    id                  INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    quote_id            INT          NOT NULL           COMMENT '报价ID',
    product_id          INT          NOT NULL           COMMENT '物料ID(关联products带出重量/体积)',
    group_code          VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '分组码(同组共用报价系数, 如 A组-1.112)',
    price_coefficient   DECIMAL(10,4) NOT NULL          COMMENT '报价系数(USD/KG)',
    weight_per_unit     DECIMAL(10,3) NOT NULL          COMMENT '单卷重量(KG, 从products.weight带出可覆盖)',
    quantity            INT          NOT NULL           COMMENT '数量(卷)',
    -- 派生字段(下一步DERIVED_RULES实现, 本步先建列)
    total_weight        DECIMAL(14,3) NOT NULL DEFAULT 0 COMMENT '派生:总重KG = weight_per_unit × quantity',
    unit_price          DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '派生:单卷价 = weight_per_unit × price_coefficient',
    subtotal            DECIMAL(14,2) NOT NULL DEFAULT 0 COMMENT '派生:小计 = unit_price × quantity',
    volume              DECIMAL(12,6) DEFAULT 0.000000   COMMENT '单件体积(从products查或手填)',
    total_volume        DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '派生:总体积 = volume × quantity',
    remark              VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_qi_quote   FOREIGN KEY (quote_id)   REFERENCES quotations(id) ON DELETE CASCADE,
    CONSTRAINT fk_qi_product FOREIGN KEY (product_id) REFERENCES products(id),

    UNIQUE KEY uk_qi_quote_product (quote_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报价明细';

CREATE INDEX idx_qi_quote ON quotation_items(quote_id);
CREATE INDEX idx_qi_group ON quotation_items(group_code);
