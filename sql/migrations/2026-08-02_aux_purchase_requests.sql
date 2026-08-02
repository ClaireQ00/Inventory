-- 2026-08-02 辅料采购需求表
-- 背景: 合同录入缺料提示可"下推采购需求单" (老板 2026-08-02)
-- 只登记需求不联动库存; 到货后走 aux_stock_moves(source_type='purchase') 入库消化,
-- 状态人工流转 pending→ordered→received
CREATE TABLE IF NOT EXISTS aux_purchase_requests (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '内部ID',
    req_no          VARCHAR(32)  NOT NULL UNIQUE    COMMENT '采购需求单号: PR+日期+3位流水, 如 PR20260802001',
    aux_code        VARCHAR(32)  NOT NULL           COMMENT '辅料编码(关联 aux_materials.aux_code)',
    quantity        INT          NOT NULL           COMMENT '需求数量(张/单位)',
    source_type     ENUM('contract_label','manual') NOT NULL DEFAULT 'manual' COMMENT '来源: 合同标签缺料下推/手工登记',
    source_no       VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '来源单号(如合同号 SC20260802001)',
    status          ENUM('pending','ordered','received','cancelled') NOT NULL DEFAULT 'pending'
                                                  COMMENT '状态: 待采购/已下单/已到货/已取消',
    remark          VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    operator        VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '操作人',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_auxpr_aux FOREIGN KEY (aux_code) REFERENCES aux_materials(aux_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='辅料采购需求单(缺料下推/手工登记)';

CREATE INDEX idx_auxpr_status ON aux_purchase_requests(status);
CREATE INDEX idx_auxpr_source ON aux_purchase_requests(source_no);
