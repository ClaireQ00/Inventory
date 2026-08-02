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
        与 CSV 导入流水线同一套引擎，数据口径一致。
      </Paragraph>
      <Row gutter={16}>
        <Col span={8}>
          <Link to="/entry/product">
            <Card hoverable title="🧱 物料录入" size="small">
              <Text type="secondary">边填边算：厚度↔外径互推、米重/单重/规格实时派生，编码按客户自动建议</Text>
            </Card>
          </Link>
        </Col>
        <Col span={8}>
          <Card title="💰 收款录入（下一阶段）" size="small">
            <Text type="secondary">汇率按到账日期自动带出、金额自动折 CNY、超额拦截</Text>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="💱 汇率录入（下一阶段）" size="small">
            <Text type="secondary">汇率月固定，每月 1 号录一次</Text>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
