-- ============================================================
-- 迁移: 2026-08-01 生产辅料模块 (标签纸先行)
-- 背景: 老板需求 - 标签纸建原料库, 附件+收发存+合同需求提示
-- 计划: docs/AUX_MATERIALS_PLAN.md (Q1-Q7 已全部定案)
-- 执行: docker exec -i inventory-db mysql -uinventory -p<pwd> inventory_db < sql/migrations/2026-08-01_aux.sql
-- 幂等: CREATE IF NOT EXISTS + INSERT IGNORE, 可重复执行
-- ============================================================

-- 10.1 辅料主档
CREATE TABLE IF NOT EXISTS aux_materials (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '内部ID',
    aux_code        VARCHAR(32)  NOT NULL UNIQUE    COMMENT '辅料编码, 如 LP-R02502 (标签纸=LP-+原R/C编号)',
    aux_type        ENUM('label_paper','packaging','other')
                                 NOT NULL DEFAULT 'label_paper' COMMENT '辅料类型: 标签纸/包装/其他(预留)。用料=半成品原材料后续独立模块',
    name            VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '名称, 如 长方形标签 25×40',
    shape           VARCHAR(8)   NOT NULL DEFAULT '' COMMENT '形状: R=长方形/纸卡, C=圆环形',
    width_mm        DECIMAL(8,2) DEFAULT NULL        COMMENT '宽度(mm)',
    height_mm       DECIMAL(8,2) DEFAULT NULL        COMMENT '高度(mm)',
    material_desc   VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '材质描述',
    supplier_code   VARCHAR(32)  DEFAULT NULL        COMMENT '默认供应商',
    unit            VARCHAR(16)  NOT NULL DEFAULT '张' COMMENT '计量单位',
    pcs_per_unit    INT          DEFAULT NULL        COMMENT '每单位张数',
    min_stock       INT          DEFAULT NULL        COMMENT '安全库存',
    remark          VARCHAR(255) NOT NULL DEFAULT '',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_aux_supplier FOREIGN KEY (supplier_code) REFERENCES suppliers(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='生产辅料主档(标签纸等)';

-- 10.2 辅料当前库存
CREATE TABLE IF NOT EXISTS aux_inventory (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    aux_code        VARCHAR(32)  NOT NULL,
    warehouse_code  VARCHAR(32)  NOT NULL,
    quantity        INT          NOT NULL DEFAULT 0,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_aux_warehouse (aux_code, warehouse_code),
    CONSTRAINT fk_auxinv_aux       FOREIGN KEY (aux_code)       REFERENCES aux_materials(aux_code),
    CONSTRAINT fk_auxinv_warehouse FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料当前库存';

-- 10.3 辅料收发流水
CREATE TABLE IF NOT EXISTS aux_stock_moves (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    move_no         VARCHAR(32)  NOT NULL,
    aux_code        VARCHAR(32)  NOT NULL,
    warehouse_code  VARCHAR(32)  NOT NULL,
    direction       ENUM('in','out') NOT NULL,
    change_qty      INT          NOT NULL,
    after_qty       INT          NOT NULL,
    source_type     ENUM('purchase','production_use','adjust','scrap') NOT NULL,
    source_no       VARCHAR(32)  NOT NULL DEFAULT '',
    operator        VARCHAR(32)  NOT NULL DEFAULT '',
    move_date       DATE         NOT NULL,
    remark          VARCHAR(255) NOT NULL DEFAULT '',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_auxmv_aux       FOREIGN KEY (aux_code)       REFERENCES aux_materials(aux_code),
    CONSTRAINT fk_auxmv_warehouse FOREIGN KEY (warehouse_code) REFERENCES warehouses(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料收发流水';

CREATE INDEX idx_auxmv_aux_time ON aux_stock_moves(aux_code, move_date);
CREATE INDEX idx_auxmv_source   ON aux_stock_moves(source_type, source_no);

-- 10.4 辅料附件
CREATE TABLE IF NOT EXISTS aux_attachments (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    aux_code        VARCHAR(32)  NOT NULL,
    file_name       VARCHAR(128) NOT NULL,
    file_type       VARCHAR(16)  NOT NULL,
    file_path       VARCHAR(255) NOT NULL,
    file_size       INT          NOT NULL,
    sha256          CHAR(64)     NOT NULL,
    uploaded_by     VARCHAR(32)  NOT NULL DEFAULT '',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_auxat_aux FOREIGN KEY (aux_code) REFERENCES aux_materials(aux_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料附件(图纸/样张/规格书)';

-- ------------------------------------------------------------
-- 种子: AUX 辅料仓 (Q3 默认: 单独辅料仓)
-- ------------------------------------------------------------
INSERT IGNORE INTO warehouses (code, name) VALUES ('AUX', '辅料仓');

-- ------------------------------------------------------------
-- 种子: 现有 3 个标签纸品种 (来自 products.label_paper 真实引用, 历史不动)
-- R 开头 = 长方形标签/纸卡 (Q4 默认: LP-前缀+原编号)
-- 注意: 引用计数直接在 products 上 GROUP BY, 不能先 DISTINCT 再 COUNT (会错算成 1)
-- ------------------------------------------------------------
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, shape, unit, remark)
SELECT CONCAT('LP-', lp), 'label_paper', CONCAT('长方形标签 ', lp), 'R', '张',
       CONCAT('种子迁移自 products.label_paper (', cnt, ' 条产品引用)')
FROM (SELECT label_paper AS lp, COUNT(*) AS cnt FROM products
      WHERE label_paper IS NOT NULL AND label_paper != ''
      GROUP BY label_paper) t;
