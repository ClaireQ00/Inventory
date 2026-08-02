// 首页 — 录入端导航
import { Card, Col, Row, Typography } from 'antd'
import { Link } from 'react-router'

const { Title, Paragraph, Text } = Typography

export default function Home() {
  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Title level={4}>录入中心</Title>
      <Paragraph type="secondary">
        所有写库操作走后端规则层（字段校验 → 公式派生 → 预览确认 → 落库 → 写后校验 → 审计留痕），
        与 CSV 导入流水线同一套引擎，数据口径一致。查询/报表/校验日志请用 Streamlit 工作台 (8501)。
      </Paragraph>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Link to="/entry/quotation">
            <Card hoverable title="📋 报价录入" size="small">
              <Text type="secondary">快照单重×报价系数定价，改重量只改行快照不动物料主数据</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Link to="/entry/contract">
            <Card hoverable title="📄 合同录入" size="small">
              <Text type="secondary">可从报价一键转入，落库自动提示标签纸需求（缺料预警）</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Link to="/entry/delivery">
            <Card hoverable title="🚚 发货录入" size="small">
              <Text type="secondary">按合同未发量发货，超发自动拦截，已发数自动回写合同</Text>
            </Card>
          </Link>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Link to="/entry/product">
            <Card hoverable title="🧱 物料录入" size="small">
              <Text type="secondary">边填边算：厚度↔外径互推、米重/单重/规格实时派生，编码按客户自动建议</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Link to="/entry/receipt">
            <Card hoverable title="💰 收款录入" size="small">
              <Text type="secondary">汇率按到账日期自动带出、金额自动折 CNY、超额收款回滚拦截</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Link to="/entry/rate">
            <Card hoverable title="💱 汇率录入" size="small">
              <Text type="secondary">汇率月固定，每月 1 号录一次，收款/合同按日期自动取当月汇率</Text>
            </Card>
          </Link>
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <Link to="/aux/materials">
            <Card hoverable title="🗂️ 辅料档案" size="small">
              <Text type="secondary">标签纸等生产辅料主档 + 图纸/样张附件（PDF/Word/图片）</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Link to="/aux/stock">
            <Card hoverable title="📦 辅料收发存" size="small">
              <Text type="secondary">入库/生产领用出库/库存计数/流水账，出库带合同需求参照</Text>
            </Card>
          </Link>
        </Col>
      </Row>
    </div>
  )
}
