-- 2026-08-02 报价单新增"交货时长(天)"字段
-- 背景: 老板要求报价录入页补充交货时长; 付款条件/包装条款改下拉(预置+历史值, 可手填)
-- 影响: quotations 表加列, 不动历史数据; sales_contracts 已有 delivery_deadline(date) 不加列
ALTER TABLE quotations
    ADD COLUMN delivery_days INT NULL COMMENT '交货时长(天): 从下单到可发货的预计天数' AFTER valid_until;
