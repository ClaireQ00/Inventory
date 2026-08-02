// 客户录入页 (2026-08-02) — 客户是单据链源头: 报价/合同/物料的品牌喷码下拉都依赖它
// 编号 Q+3位顺推自动建议 (Q024/Q025 → Q026), 可手改; 落库写审计
import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Input, Modal, Row, Space, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api } from '@/api/client'

const { Text, Title, Paragraph } = Typography

export default function CustomerEntry() {
  const { message } = App.useApp()
  const [form, setForm] = useState({
    code: '', name: '', contact_person: '', phone: '', address: '',
    bank_account: '', brand_name: '', company_profiles: '', billing_profiles: '', remark: '',
  })
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const suggestCode = () => {
    api.suggestCustomerCode().then((r) => set('code', r.code)).catch(() => {})
  }
  useEffect(() => { suggestCode() }, [])

  const onSubmit = async () => {
    if (!form.code.trim()) return message.warning('请填客户编号')
    if (!form.name.trim()) return message.warning('请填客户名称')
    setSubmitting(true)
    try {
      const r = await api.createCustomer(form, operator || 'frontend-react')
      if (r.ok) {
        Modal.success({
          title: `✅ 客户 ${r.code} 已建档`,
          content: `${form.name} 建档成功。现在可以在报价/合同/物料录入页选到这个客户了。`,
        })
        setForm({
          code: '', name: '', contact_person: '', phone: '', address: '',
          bank_account: '', brand_name: '', company_profiles: '', billing_profiles: '', remark: '',
        })
        suggestCode()
      } else {
        Modal.error({ title: '建档被拒绝（数据库未改动）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={4}>👤 客户录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>编号按序列自动建议 ｜ 品牌/开票资料一次建齐</Text></Title>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        客户是整条单据链的源头：报价、合同、收款都要先选客户；物料的品牌/喷码下拉也按客户过滤。
      </Paragraph>

      <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}><Text type="secondary">客户编号 *（自动建议，可改）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={form.code} onChange={(e) => set('code', e.target.value)} placeholder="如 Q026" />
              <Button icon={<ReloadOutlined />} onClick={suggestCode} title="重新建议" />
            </Space.Compact></Col>
          <Col span={8}><Text type="secondary">客户名称 *</Text>
            <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="公司或联系人常用称呼" /></Col>
          <Col span={8}><Text type="secondary">默认品牌</Text>
            <Input value={form.brand_name} onChange={(e) => set('brand_name', e.target.value)} placeholder="如 PAGODA（物料录入下拉用）" /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={8}><Text type="secondary">联系人</Text>
            <Input value={form.contact_person} onChange={(e) => set('contact_person', e.target.value)} /></Col>
          <Col span={8}><Text type="secondary">电话</Text>
            <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Col>
          <Col span={8}><Text type="secondary">地址</Text>
            <Input value={form.address} onChange={(e) => set('address', e.target.value)} /></Col>
        </Row>
      </Card>

      <Card size="small" title="商务资料（打单/收款用）" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={12}><Text type="secondary">银行账号</Text>
            <Input value={form.bank_account} onChange={(e) => set('bank_account', e.target.value)} placeholder="收款账户信息" /></Col>
          <Col span={12}><Text type="secondary">备注</Text>
            <Input value={form.remark} onChange={(e) => set('remark', e.target.value)} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={12}><Text type="secondary">公司资料（报价单/合同抬头用）</Text>
            <Input.TextArea rows={3} value={form.company_profiles} onChange={(e) => set('company_profiles', e.target.value)}
              placeholder="公司全称、注册地址、税号等，打单模板预留" /></Col>
          <Col span={12}><Text type="secondary">开票资料</Text>
            <Input.TextArea rows={3} value={form.billing_profiles} onChange={(e) => set('billing_profiles', e.target.value)}
              placeholder="开票抬头、税号、开户行等" /></Col>
        </Row>
      </Card>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row justify="end">
          <Space>
            <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
            <Button type="primary" size="large" loading={submitting} onClick={onSubmit}>建档</Button>
          </Space>
        </Row>
      </Card>
    </div>
  )
}
