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

-- 3) 零库存行: 在用辅料 × AUX 仓 (库存行的唯一真相在 aux_inventory,
--    初始 0 张, 之后每一笔收发都由 aux_stock_move 单事务维护)
--    只给标签纸建行: 包装方式(PK-)是纯档案不计量, 不进收发存 (2026-08-02 定)
INSERT IGNORE INTO aux_inventory (aux_code, warehouse_code, quantity)
SELECT m.aux_code, 'AUX', 0
FROM aux_materials m
WHERE m.is_active = 1 AND m.aux_type = 'label_paper';

-- 4) 包装方式档案 (2026-08-02 老板要求: 物料数据里的包装种类灌进辅料库,
--    供录入页包装下拉使用; 纯档案不计量, unit 留空, 暂不纳入收发存)
--    编码 PK-001.. 按历史引用频次排序(冻结快照), 新包装方式以后走辅料档案页新增
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-001', 'packaging', '明包皮', '', '包装方式档案(种子自 products.package, 4018 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-002', 'packaging', '线膜', '', '包装方式档案(种子自 products.package, 3510 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-003', 'packaging', '内膜明皮', '', '包装方式档案(种子自 products.package, 1193 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-004', 'packaging', '透明膜', '', '包装方式档案(种子自 products.package, 1042 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-005', 'packaging', 'PE膜', '', '包装方式档案(种子自 products.package, 875 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-006', 'packaging', '绿包皮', '', '包装方式档案(种子自 products.package, 688 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-007', 'packaging', '无纺布', '', '包装方式档案(种子自 products.package, 403 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-008', 'packaging', '透明膜/专用合格证', '', '包装方式档案(种子自 products.package, 331 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-009', 'packaging', 'PE透明膜', '', '包装方式档案(种子自 products.package, 323 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-010', 'packaging', '内无纺布外透明膜', '', '包装方式档案(种子自 products.package, 101 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-011', 'packaging', '内膜/灰包皮', '', '包装方式档案(种子自 products.package, 101 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-012', 'packaging', '内膜明皮/不写字', '', '包装方式档案(种子自 products.package, 90 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-013', 'packaging', '内膜/蓝龙专用包皮', '', '包装方式档案(种子自 products.package, 79 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-014', 'packaging', '透明膜2层', '', '包装方式档案(种子自 products.package, 79 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-015', 'packaging', '内膜/白色不透明包皮', '', '包装方式档案(种子自 products.package, 78 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-016', 'packaging', '内膜/不透明白包皮', '', '包装方式档案(种子自 products.package, 75 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-017', 'packaging', '常规出口包装', '', '包装方式档案(种子自 products.package, 75 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-018', 'packaging', '不透明白包皮', '', '包装方式档案(种子自 products.package, 70 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-019', 'packaging', '内膜/黄包皮', '', '包装方式档案(种子自 products.package, 64 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-020', 'packaging', '无', '', '包装方式档案(种子自 products.package, 58 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-021', 'packaging', '透明膜／不透明白包皮', '', '包装方式档案(种子自 products.package, 58 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-022', 'packaging', '专用蓝龙PE膜', '', '包装方式档案(种子自 products.package, 56 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-023', 'packaging', '彩卡/热缩膜', '', '包装方式档案(种子自 products.package, 51 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-024', 'packaging', '透明膜两层', '', '包装方式档案(种子自 products.package, 51 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-025', 'packaging', '彩卡 /热缩膜/四件套', '', '包装方式档案(种子自 products.package, 38 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-026', 'packaging', '内PE膜外白色透明包皮', '', '包装方式档案(种子自 products.package, 35 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-027', 'packaging', '透明膜/彩卡', '', '包装方式档案(种子自 products.package, 35 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-028', 'packaging', '内膜/深蓝色包皮', '', '包装方式档案(种子自 products.package, 31 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-029', 'packaging', '内膜外不透明白包皮', '', '包装方式档案(种子自 products.package, 31 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-030', 'packaging', '内膜明皮/只写规格米数', '', '包装方式档案(种子自 products.package, 30 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-031', 'packaging', '热缩膜/合格证', '', '包装方式档案(种子自 products.package, 30 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-032', 'packaging', '内鳄鱼膜外磨砂PE膜', '', '包装方式档案(种子自 products.package, 29 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-033', 'packaging', '透明膜包装专用胶带', '', '包装方式档案(种子自 products.package, 29 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-034', 'packaging', '明包皮/只写规格米数', '', '包装方式档案(种子自 products.package, 28 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-035', 'packaging', '绿包皮/只写规格米数', '', '包装方式档案(种子自 products.package, 28 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-036', 'packaging', '黄包皮', '', '包装方式档案(种子自 products.package, 28 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-037', 'packaging', '内膜 绿包皮', '', '包装方式档案(种子自 products.package, 27 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-038', 'packaging', 'B20专用包皮', '', '包装方式档案(种子自 products.package, 23 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-039', 'packaging', 'PE膜/彩卡', '', '包装方式档案(种子自 products.package, 20 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-040', 'packaging', '编织布', '', '包装方式档案(种子自 products.package, 19 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-041', 'packaging', '内无纺布外PE透明膜', '', '包装方式档案(种子自 products.package, 18 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-042', 'packaging', 'PE膜 包两层', '', '包装方式档案(种子自 products.package, 16 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-043', 'packaging', '内膜外2层明包皮', '', '包装方式档案(种子自 products.package, 16 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-044', 'packaging', '老婆管专用彩卡', '', '包装方式档案(种子自 products.package, 16 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-045', 'packaging', '内膜外蓝包皮', '', '包装方式档案(种子自 products.package, 15 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-046', 'packaging', '本厂通用五星彩卡', '', '包装方式档案(种子自 products.package, 12 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-047', 'packaging', '内膜/红包皮', '', '包装方式档案(种子自 products.package, 10 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-048', 'packaging', '内膜/绿包皮', '', '包装方式档案(种子自 products.package, 10 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-049', 'packaging', '四条黄色打包带/两层透明膜', '', '包装方式档案(种子自 products.package, 10 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-050', 'packaging', '专用彩卡', '', '包装方式档案(种子自 products.package, 9 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-051', 'packaging', '内膜外红包皮', '', '包装方式档案(种子自 products.package, 9 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-052', 'packaging', '四条打包带/两层透明膜', '', '包装方式档案(种子自 products.package, 9 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-053', 'packaging', '包双层透明膜', '', '包装方式档案(种子自 products.package, 8 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-054', 'packaging', '带麦穗的彩卡', '', '包装方式档案(种子自 products.package, 8 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-055', 'packaging', '蓝色编织布', '', '包装方式档案(种子自 products.package, 8 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-056', 'packaging', '蓝龙水带专用纸', '', '包装方式档案(种子自 products.package, 7 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-057', 'packaging', '透明PE膜', '', '包装方式档案(种子自 products.package, 7 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-058', 'packaging', '内膜外绿包皮', '', '包装方式档案(种子自 products.package, 5 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-059', 'packaging', '彩卡-PE透明膜', '', '包装方式档案(种子自 products.package, 5 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-060', 'packaging', '绿包皮/只写规格', '', '包装方式档案(种子自 products.package, 5 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-061', 'packaging', '蓝色包皮/通用彩卡', '', '包装方式档案(种子自 products.package, 5 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-062', 'packaging', '三条打包带--透明膜', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-063', 'packaging', '内无纺布包装放彩卡后用透明膜', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-064', 'packaging', '内膜2层蓝包皮', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-065', 'packaging', '内膜外黄色编织布', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-066', 'packaging', '四条黄色专用打包带/一层PE膜', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-067', 'packaging', '明皮不要内膜/不写字', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-068', 'packaging', '线膜两层', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-069', 'packaging', '线膜用千峰纸卡', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-070', 'packaging', '绿包皮/不写字', '', '包装方式档案(种子自 products.package, 4 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-071', 'packaging', 'PE膜2层', '', '包装方式档案(种子自 products.package, 3 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-072', 'packaging', 'PVC膜', '', '包装方式档案(种子自 products.package, 3 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-073', 'packaging', '塑封机包装', '', '包装方式档案(种子自 products.package, 3 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-074', 'packaging', '用厚一点的透明膜包装', '', '包装方式档案(种子自 products.package, 3 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-075', 'packaging', '黄透明膜', '', '包装方式档案(种子自 products.package, 3 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-076', 'packaging', '专用蓝龙包皮（带蓝龙字）', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-077', 'packaging', '专用黑色绸布', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-078', 'packaging', '内膜/半透明塑料包皮', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-079', 'packaging', '内膜明皮/黄胶带穿心', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-080', 'packaging', '彩卡-三条打包带', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-081', 'packaging', '打纸盘', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-082', 'packaging', '标签/透明膜', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-083', 'packaging', '线膜/千峰彩卡', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-084', 'packaging', '线膜用盈盛纸卡', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-085', 'packaging', '蓝龙彩卡、合格证', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-086', 'packaging', '透明膜三层', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-087', 'packaging', '黄色透明膜', '', '包装方式档案(种子自 products.package, 2 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-088', 'packaging', '内膜/鳄鱼包皮', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-089', 'packaging', '彩卡/水枪/热缩膜  30米4件/箱', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-090', 'packaging', '彩卡/水枪/热缩膜 15米8件/箱', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-091', 'packaging', '打包带串上塑料卡/透明膜包装', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-092', 'packaging', '打包带串上塑料卡/透明膜包装 15米8件/箱', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-093', 'packaging', '打包带串上塑料卡/透明膜包装 30米4件/箱', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-094', 'packaging', '抽气盘管', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-095', 'packaging', '标签/四件套/热缩膜', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-096', 'packaging', '灰包皮', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-097', 'packaging', '绿包皮/只写规格重量', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-098', 'packaging', '装袋', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-099', 'packaging', '透明膜/合格证/装袋子5件', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-100', 'packaging', '透明膜/合格证/装袋子6件', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-101', 'packaging', '透明膜/橙色包皮', '', '包装方式档案(种子自 products.package, 1 条引用)');
INSERT IGNORE INTO aux_materials (aux_code, aux_type, name, unit, remark) VALUES ('PK-102', 'packaging', '黄色不透明编织布', '', '包装方式档案(种子自 products.package, 1 条引用)');
