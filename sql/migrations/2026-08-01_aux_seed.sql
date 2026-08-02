-- ============================================================
-- 种子: 2026-08-01 生产辅料模块·初始数据
-- 内容:
--   1) AUX 辅料仓 (若主迁移未跑也能独立生效)
--   2) 3 个标签纸档案 (与 2026-08-01_aux.sql 种子同口径, INSERT IGNORE 不覆盖)
--   3) 每个在用辅料 × AUX 仓 的零库存行
--      → 收发存页一打开就能看到全部品种, 不用等第一笔收发
-- 说明:
--   - min_stock(安全库存) 留 NULL: 等老板按实际采购周期确认后再填,
--     填了之后低库存预警(/api/aux/inventory?low_only=1) 自动生效
--   - width_mm/height_mm(标签尺寸) 留 NULL: 待老板提供标签样张/图纸后补,
--     附件上传接口已就绪
-- 执行: docker exec -i inventory-db mysql -uinventory -p<pwd> inventory_db < sql/migrations/2026-08-01_aux_seed.sql
-- 幂等: INSERT IGNORE, 可重复执行
-- ============================================================

-- 1) 辅料仓
INSERT IGNORE INTO warehouses (code, name) VALUES ('AUX', '辅料仓');

-- 2) 标签纸档案 (种子口径与 2026-08-01_aux.sql 一致: 来自 products.label_paper 真实引用)
--    注意: 引用计数必须直接在 products 上 GROUP BY, 不能先 DISTINCT 再 COUNT
--    (先 DISTINCT 会把每个品种的引用数错算成 1 —— 2026-08-02 修正)
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, shape, unit, remark)
SELECT CONCAT('LP-', lp), 'label_paper', CONCAT('长方形标签 ', lp), 'R', '张',
       CONCAT('种子迁移自 products.label_paper (', cnt, ' 条产品引用)')
FROM (SELECT label_paper AS lp, COUNT(*) AS cnt FROM products
      WHERE label_paper IS NOT NULL AND label_paper != ''
      GROUP BY label_paper) t;

-- 3) 零库存行: 所有在用辅料 × AUX 仓 (库存行的唯一真相在 aux_inventory,
--    初始 0 张, 之后每一笔收发都由 aux_stock_move 单事务维护)
INSERT IGNORE INTO aux_inventory (aux_code, warehouse_code, quantity)
SELECT m.aux_code, 'AUX', 0
FROM aux_materials m
WHERE m.is_active = 1;
