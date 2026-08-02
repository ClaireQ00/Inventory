-- ============================================================
-- 迁移: 2026-08-01 物料类型档案 (老板: 物料类型下拉选择+档案管理,
--       成本指导价格预留, 后期关联单据利润核算)
-- 执行: docker exec -i inventory-db mysql -uinventory -p<pwd> inventory_db < sql/migrations/2026-08-01_material_type_profiles.sql
-- 幂等: CREATE IF NOT EXISTS + INSERT IGNORE, 可重复执行
-- ============================================================

CREATE TABLE IF NOT EXISTS material_type_profiles (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    type_code       VARCHAR(32)  NOT NULL UNIQUE    COMMENT '物料类型编码, 与 products.material_type 同值',
    name            VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '显示名(默认同编码)',
    guide_cost_price DECIMAL(12,2) DEFAULT NULL     COMMENT '成本指导价格(预留, 后期关联单据利润核算)',
    price_currency  VARCHAR(8)   NOT NULL DEFAULT 'CNY' COMMENT '指导价格币种(预留)',
    remark          VARCHAR(255) NOT NULL DEFAULT '',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料类型档案(成本指导价预留)';

-- 种子: 从 products.material_type 现有值归集 (历史不动, 档案先行)
INSERT IGNORE INTO material_type_profiles (type_code, name, remark)
SELECT mt, mt, CONCAT('种子迁移自 products.material_type (', COUNT(*), ' 条产品使用)')
FROM (SELECT DISTINCT material_type AS mt FROM products
      WHERE material_type IS NOT NULL AND material_type != '') t
GROUP BY mt;
