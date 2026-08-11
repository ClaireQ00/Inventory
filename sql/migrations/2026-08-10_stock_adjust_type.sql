-- 2026-08-10 出入库类型扩展: 增加 adjust (期初/调整), 用于系统切换期初建账与历史货物出清
-- 背景: BL-2608 真实数据导入 —— 临沂仓 0726 期初库存无合同可挂(历史订单),
--       0808 装柜含历史期初货物(无合同/发货单锚点), 需要 adjust 类型承载
-- transfer 类型本就在 ENUM 里, 本次仅放开应用层闸门 (db_writer STOCK_IN/OUT_TYPES)
ALTER TABLE stock_in
    MODIFY COLUMN in_type ENUM('purchase','production','transfer','return','adjust')
    NOT NULL DEFAULT 'purchase' COMMENT '入库类型: 采购/生产/调拨/退货/期初调整';

ALTER TABLE stock_out
    MODIFY COLUMN out_type ENUM('sale','production','transfer','scrap','adjust')
    NOT NULL DEFAULT 'sale' COMMENT '出库类型: 销售/生产/调拨/报废/调整(期初历史货物出清)';
