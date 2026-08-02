-- ============================================================
-- 迁移: 2026-08-02 辅料档案类型扩展 (一个档案库管全部手填值)
-- 背景: 老板要求 —— 标签纸/盘型/米标/用料/喷码/打线 手填新值也能
--       像包装一样自动建档, 一个开关统一管理 (M1c+)
-- 内容:
--   1) aux_materials.aux_type ENUM 扩展 5 个工艺档案类型
--      (纯档案不计量, 不进收发存 —— 与 Q7 定案一致)
--   2) name 加宽到 VARCHAR(255): 喷码全文可能超 64 字符, 防截断
-- 注意: 执行前先看 SHOW PROCESSLIST 有没有僵尸连接 (元数据锁教训)
-- 执行: docker exec -i inventory-db mysql -uinventory -p<pwd> inventory_db < sql/migrations/2026-08-02_aux_types.sql
-- ============================================================

ALTER TABLE aux_materials
    MODIFY aux_type ENUM('label_paper','packaging','spray_code','meter_mark',
                         'material_used','wire_pattern','coil_type','other')
        NOT NULL DEFAULT 'label_paper'
        COMMENT '辅料类型: 标签纸/包装/喷码/米标/用料/打线/盘型/其他 (除标签纸外均为纯档案不计量)';

ALTER TABLE aux_materials
    MODIFY name VARCHAR(255) NOT NULL DEFAULT '' COMMENT '名称 (喷码等长文本可达 200+ 字符)';
