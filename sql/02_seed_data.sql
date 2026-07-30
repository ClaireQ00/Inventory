-- ============================================================
-- 进销存管理系统 - 物料数据脚本 (MySQL)
-- 文件: sql/02_seed_data.sql
-- 说明: 从 物料.xlsx 的 Sheet1 读取并生成 INSERT 语句
--       外径(outer_diameter) = 内径 + 壁厚×2
--       米重(weight_per_meter) 已从 kg/m 换算成 g/m
-- 注意: 请在执行完 01_schema.sql 之后再执行本文件
-- ============================================================

USE inventory_db;

-- ------------------------------------------------------------
-- 物料主数据 (来自 Excel Sheet1, 共 6 条)
-- ------------------------------------------------------------
INSERT INTO products (material_id, customer_code, brand, product_category, material_type, spec, inner_diameter, inner_diameter_inch, outer_diameter, id_x_od, thickness, length, virtual_weight, virtual_length, wire_spacing, weight_per_meter, weight, appearance_inner, appearance_outer, appearance_height, volume, package, label_paper, material_used, wire_pattern, coil_type, pressure, spray_code, meter_mark, remark) VALUES
  ('M-W158-001', 'W158', NULL, '线管', NULL, '1-1/4"', 32, '1-1/4"', 40.36, '32x40.36', 4.18, 100, NULL, NULL, '32根', 640.000, 64, NULL, NULL, NULL, NULL, '线膜', NULL, NULL, '红蓝双线', '内径30高7层', NULL, 'REINFORCED　WATER　HOSE　1-1/4”→||←　－1m－100m　2020.10.29AB2', NULL, '500X3合股线,割米数,'),
  ('M-Q025-002', 'Q025', NULL, '线管', NULL, '6.8', 6.8, NULL, 10.60, '6.8x10.6', 1.9, 101, NULL, NULL, NULL, 69.000, 7, NULL, NULL, NULL, NULL, 'PE膜', NULL, 'A25橙', '红蓝黑三线', NULL, NULL, NULL, NULL, NULL),
  ('M-Q025-003', 'Q025', NULL, '线管', NULL, '9.1', 9.1, NULL, 12.90, '9.1x12.9', 1.9, 101, NULL, NULL, NULL, 89.000, 9, NULL, NULL, NULL, NULL, 'PE膜', NULL, 'A25橙', '红蓝黑三线', NULL, NULL, NULL, NULL, NULL),
  ('M-Q025-004', 'Q025', NULL, '线管', NULL, '23.8', 23.8, NULL, 29.80, '23.8x29.8', 3, 51, NULL, NULL, NULL, 333.000, 17, NULL, NULL, NULL, NULL, 'PE膜', NULL, 'A25橙', '红蓝黑三线', NULL, NULL, NULL, NULL, NULL),
  ('M-Q025-005', 'Q025', NULL, '线管', NULL, '38.5', 38.5, NULL, 46.30, '38.5x46.3', 3.9, 51, NULL, NULL, NULL, 686.000, 35, NULL, NULL, NULL, NULL, 'PE膜', NULL, 'A25橙', '红蓝黑三线', NULL, NULL, NULL, NULL, NULL),
  ('M-Q025-006', 'Q025', NULL, '线管', NULL, '48.2', 48.2, NULL, 57.20, '48.2x57.2', 4.5, 51, NULL, NULL, NULL, 1000.000, 51, NULL, NULL, NULL, NULL, 'PE膜', NULL, 'A25橙', '红蓝黑三线', NULL, NULL, NULL, NULL, NULL);

-- 完成
SELECT CONCAT('已写入 ', COUNT(*), ' 条物料') AS message FROM products;
