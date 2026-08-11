// 客户录入页 (2026-08-02) — 客户是单据链源头: 报价/合同/物料的品牌喷码下拉都依赖它
// 2026-08-11: 编号规则 = 字母(业务员)+4位数字(客户终身号, 首位=业务员数字编码);
//             先选业务员自动推荐编号, 新序列从 001 起; 可手改; 落库写审计
import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Input, Modal, Row, Select, Space, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api, type Salesperson } from '@/api/client'
import { selectFilter } from '@/lib/fuzzy'

const { Text, Title, Paragraph } = Typography

export default function CustomerEntry() {
  const { message } = App.useApp()
  const [form, setForm] = useState({
    code: '', name: '', contact_person: '', phone: '', address: '',
    bank_account: '', brand_name: '', company_profiles: '', billing_profiles: '', remark: '',
  })
  const [salespersons, setSalespersons] = useState<Salesperson[]>([])
  const [spLetter, setSpLetter] = useState<string>('Q')
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // 新增业务员小窗
  const [spOpen, setSpOpen] = useState(false)
  const [spForm, setSpForm] = useState({ code: '', name: '', digit: '', phone: '', remark: '' })

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const loadSalespersons = () => {
    api.salespersons().then(setSalespersons).catch(() => {})
  }
  const suggestCode = (letter?: string) => {
    const L = letter ?? spLetter
    api.suggestCustomerCode(L).then((r) => { if (r.code) set('code', r.code) }).catch(() => {})
  }
  useEffect(() => { loadSalespersons(); suggestCode('Q') }, [])

  const onSpChange = (letter: string) => {
    setSpLetter(letter)
    suggestCode(letter)  // 换业务员 → 按其字母+数字序列重荐编号
  }

  const onCreateSp = async () => {
    const r = await api.createSalesperson(spForm, operator || 'frontend-react')
    if (r.ok) {
      message.success(`业务员 ${r.code} 已建档`)
      setSpOpen(false)
      setSpForm({ code: '', name: '', digit: '', phone: '', remark: '' })
      loadSalespersons()
      if (r.code) onSpChange(r.code)  // 新业务员 → 空序列从 001 推荐
    } else {
      Modal.error({ title: '业务员建档被拒绝', content: r.errors.join('\n') })
    }
  }

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
      <Title level={4}>👤 客户录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>选业务员自动推荐编号 ｜ 品牌/开票资料一次建齐</Text></Title>
      <Paragraph type="secondary" style={{ fontSize: 12 }}>
        编号规则：字母（业务员）+ 4 位数字（客户终身号，首位=业务员数字编码）。客户换业务员只换字母、数字不变。
      </Paragraph>

      <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}><Text type="secondary">负责业务员 *（决定编号字母）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Select style={{ width: '100%' }} value={spLetter} onChange={onSpChange}
                showSearch filterOption={selectFilter}
                options={salespersons.map((s) => ({
                  value: s.code,
                  label: s.name ? `${s.code} - ${s.name}（${s.digit} 段）` : `${s.code}（${s.digit} 段，姓名待补）`,
                }))} />
              <Button onClick={() => setSpOpen(true)} title="新增业务员">＋</Button>
            </Space.Compact></Col>
          <Col span={8}><Text type="secondary">客户编号 *（按业务员自动建议，可改）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={form.code} onChange={(e) => set('code', e.target.value)} placeholder="如 Q0026" />
              <Button icon={<ReloadOutlined />} onClick={() => suggestCode()} title="重新建议" />
            </Space.Compact></Col>
          <Col span={8}><Text type="secondary">客户名称 *</Text>
            <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="公司或联系人常用称呼" /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={8}><Text type="secondary">默认品牌</Text>
            <Input value={form.brand_name} onChange={(e) => set('brand_name', e.target.value)} placeholder="如 PAGODA（物料录入下拉用）" /></Col>
          <Col span={8}><Text type="secondary">联系人</Text>
            <Input value={form.contact_person} onChange={(e) => set('contact_person', e.target.value)} /></Col>
          <Col span={8}><Text type="secondary">电话</Text>
            <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
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

      <Modal title="新增业务员" open={spOpen} onOk={onCreateSp} onCancel={() => setSpOpen(false)} okText="建档" cancelText="取消">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            代码 = 客户编码的首字母（1 个字母）；首位数字 = 该业务员的数字编码（其名下客户编号的第一位数字）。
            新业务员的客户序列自动从 001 起推荐。
          </Text>
          <Input placeholder="代码（1个字母，如 G）" value={spForm.code}
            onChange={(e) => setSpForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))} maxLength={1} />
          <Input placeholder="姓名" value={spForm.name}
            onChange={(e) => setSpForm((f) => ({ ...f, name: e.target.value }))} />
          <Input placeholder="首位数字（0-9）" value={spForm.digit}
            onChange={(e) => setSpForm((f) => ({ ...f, digit: e.target.value }))} maxLength={1} />
          <Input placeholder="电话（可空）" value={spForm.phone}
            onChange={(e) => setSpForm((f) => ({ ...f, phone: e.target.value }))} />
          <Input placeholder="备注（可空）" value={spForm.remark}
            onChange={(e) => setSpForm((f) => ({ ...f, remark: e.target.value }))} />
        </Space>
      </Modal>
    </div>
  )
}
