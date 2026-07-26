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
    status          ENUM('draft','confirmed','received','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/已收货/已取消',
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
    total_amount    DECIMAL(14,2) NOT NULL DEFAULT 0.00 COMMENT '合同总金额(CNY)',
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
    status          ENUM('draft','confirmed','cancelled')
                                NOT NULL DEFAULT 'draft' COMMENT '状态: 草稿/已确认/已取消',
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
-- ------------------------------------------------------------
DROP TABLE IF EXISTS delivery_order_items;
CREATE TABLE delivery_order_items (
    id                  INT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    delivery_id         INT          NOT NULL           COMMENT '发货单ID',
    contract_item_id    INT          DEFAULT NULL       COMMENT '关联合同明细ID(回写已发数量用)',
    product_id          INT          NOT NULL           COMMENT '物料ID',
    quantity            INT          NOT NULL           COMMENT '发货数量(件/卷)',
    remark              VARCHAR(255) DEFAULT ''         COMMENT '备注',

    CONSTRAINT fk_doi_delivery     FOREIGN KEY (delivery_id)      REFERENCES delivery_orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_doi_contract_item FOREIGN KEY (contract_item_id) REFERENCES sales_contract_items(id),
    CONSTRAINT fk_doi_product      FOREIGN KEY (product_id)       REFERENCES products(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='发货单明细';

CREATE INDEX idx_doi_delivery      ON delivery_order_items(delivery_id);
CREATE INDEX idx_doi_contract_item ON delivery_order_items(contract_item_id);
CREATE INDEX idx_doi_product       ON delivery_order_items(product_id);
