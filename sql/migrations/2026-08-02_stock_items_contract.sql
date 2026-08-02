-- 2026-08-02 成品出入库明细挂合同 (老板: "入库单的主物料应该关联合同, 跟发货单一样, 还有出库单")
-- 设计:
--   - 生产入库: 录入页单头选合同, 后端盖到每行; 闸门=物料必须在该合同明细里
--   - 销售出库: 只选发货单, 后端按 (delivery_no, material_id) 从发货明细自动反解合同号
--   - 采购/退货入库、生产领用/报废出库: 与合同无关, 留 NULL
--   - inventory 库存表刻意不挂合同 (物理结果, 合同维度走流水聚合查询)
ALTER TABLE stock_in_items
    ADD COLUMN contract_no VARCHAR(32) DEFAULT NULL COMMENT '关联合同号(生产入库时填)' AFTER material_id,
    ADD CONSTRAINT fk_sii_contract FOREIGN KEY (contract_no) REFERENCES sales_contracts(contract_no);
CREATE INDEX idx_sii_contract ON stock_in_items(contract_no);

ALTER TABLE stock_out_items
    ADD COLUMN contract_no VARCHAR(32) DEFAULT NULL COMMENT '关联合同号(销售出库时由发货单自动反解)' AFTER material_id,
    ADD CONSTRAINT fk_soi_contract FOREIGN KEY (contract_no) REFERENCES sales_contracts(contract_no);
CREATE INDEX idx_soi_contract ON stock_out_items(contract_no);
