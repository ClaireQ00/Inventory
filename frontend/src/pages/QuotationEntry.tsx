// 报价录入页 (F2.6) — 头+明细两段式落库
// ADR-0005 快照重量: 行上单重从物料带出可覆盖, 单价=单重×系数, 全部后端重算
import { useEffect, useState } from 'react'
import {
  App, Button, Card, Col, DatePicker, Input, Modal, Row, Select, Space,
  Statistic, Tag, Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type Customer } from '@/api/client'
import DocItemsEditor, { newItem, itemCalc, type DocItem, type ProductOption } from '@/components/DocItemsEditor'

const { Text, Title } = Typography

export default function QuotationEntry() {
  const { message } = App.useApp()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [products, setProducts] = useState<ProductOption[]>([])
  const [header, setHeader] = useState({
    quote_no: '', customer_code: null as string | null, quote_type: 'brief',
    quote_date: dayjs(), valid_until: null as dayjs.Dayjs | null,
    currency: 'USD', trade_terms: 'FOB', port_loading: '', port_discharge: '',
    payment_term: '', packing: '', remark: '',
  })
  const [items, setItems] = useState<DocItem[]>([newItem(1)])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => message.error(`客户加载失败: ${e.message}`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const suggestNo = () => {
    api.suggestDocNo('quotation').then((r) => setHeader((h) => ({ ...h, quote_no: r.doc_no }))).catch(() => {})
  }

  const onCustomer = (code: string) => {
    setHeader((h) => ({ ...h, customer_code: code }))
    api.productsPicker(code).then((list) => setProducts(list as unknown as ProductOption[])).catch(() => setProducts([]))
    if (!header.quote_no) suggestNo()
  }

  const set = (k: string, v: unknown) => setHeader((h) => ({ ...h, [k]: v }))
  const total = items.reduce((s, it) => s + itemCalc('quotation', it).subtotal, 0)

  const validItems = items.filter((it) => it.material_id && it.quantity && it.price_coefficient)

  const onSubmit = async () => {
    if (!header.customer_code) return message.warning('请选择客户')
    if (!header.quote_no.trim()) return message.warning('请填报价号')
    if (validItems.length === 0) return message.warning('至少一行完整明细（物料+系数+数量）')
    setSubmitting(true)
    try {
      const r = await api.createDoc('quotation', {
        quote_no: header.quote_no.trim(),
        customer_code: header.customer_code,
        quote_type: header.quote_type,
        quote_date: header.quote_date.format('YYYY-MM-DD'),
        valid_until: header.valid_until?.format('YYYY-MM-DD') || null,
        currency: header.currency, trade_terms: header.trade_terms,
        port_loading: header.port_loading, port_discharge: header.port_discharge,
        payment_term: header.payment_term, packing: header.packing, remark: header.remark,
      }, validItems.map((it) => ({
        item_no: it.item_no, material_id: it.material_id,
        weight_per_unit: it.weight_per_unit, price_coefficient: it.price_coefficient,
        quantity: it.quantity, remark: it.remark,
      })), operator || 'frontend-react')
      if (r.ok) {
        Modal.success({
          title: `✅ 报价单 ${r.doc_no} 已入库`,
          content: `总额 ${r.total_amount} ${header.currency}（汇率 ${r.exchange_rate}，折 CNY ${r.total_amount_cny}）。谈成后可到合同录入页"从报价转入"。`,
        })
        setItems([newItem(1)])
        suggestNo()
      } else {
        Modal.error({ title: '写入被拒绝（数据库未改动）', content: r.errors.join('\n') })
      }
    } catch (e) {
      message.error(`提交失败: ${(e as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto' }}>
      <Title level={4}>📋 报价录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>快照重量×报价系数定价 ｜ 谈成后转合同</Text></Title>

      <Card size="small" title="报价头" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}><Text type="secondary">客户 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择客户" value={header.customer_code} onChange={onCustomer}
              options={customers.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))} /></Col>
          <Col span={6}><Text type="secondary">报价号 *（按日期自动建议）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={header.quote_no} onChange={(e) => set('quote_no', e.target.value)} placeholder="QT+日期+流水" />
              <Button icon={<ReloadOutlined />} onClick={suggestNo} title="重新建议" />
            </Space.Compact></Col>
          <Col span={4}><Text type="secondary">类型</Text>
            <Select style={{ width: '100%' }} value={header.quote_type} onChange={(v) => set('quote_type', v)}
              options={[{ value: 'brief', label: '简要报价' }, { value: 'formal', label: '正式QT' }]} /></Col>
          <Col span={4}><Text type="secondary">报价日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={header.quote_date} onChange={(v) => v && set('quote_date', v)} /></Col>
          <Col span={4}><Text type="secondary">币种</Text>
            <Select style={{ width: '100%' }} value={header.currency} onChange={(v) => set('currency', v)}
              options={['USD', 'EUR', 'IDR', 'CNY'].map((c) => ({ value: c }))} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={4}><Text type="secondary">贸易术语</Text>
            <Select style={{ width: '100%' }} value={header.trade_terms} onChange={(v) => set('trade_terms', v)}
              options={['FOB', 'CIF', 'CFR', 'EXW'].map((t) => ({ value: t }))} /></Col>
          <Col span={4}><Text type="secondary">装运港</Text>
            <Input value={header.port_loading} onChange={(e) => set('port_loading', e.target.value)} placeholder="如 Qingdao" /></Col>
          <Col span={4}><Text type="secondary">卸货港</Text>
            <Input value={header.port_discharge} onChange={(e) => set('port_discharge', e.target.value)} placeholder="如 Jakarta" /></Col>
          <Col span={6}><Text type="secondary">有效期至</Text>
            <DatePicker style={{ width: '100%' }} value={header.valid_until} onChange={(v) => set('valid_until', v)} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={12}><Text type="secondary">付款条件</Text>
            <Input value={header.payment_term} onChange={(e) => set('payment_term', e.target.value)} placeholder="如 TT 30% AS DOWN PAYMENT..." /></Col>
          <Col span={12}><Text type="secondary">包装条款</Text>
            <Input value={header.packing} onChange={(e) => set('packing', e.target.value)} placeholder="如 PACKED IN WOVEN BAGS..." /></Col>
        </Row>
      </Card>

      <Card size="small" title="报价明细" style={{ marginBottom: 16 }}
        extra={<Tag color="blue">快照单重可改（谈价只改行快照，物料主数据不动）</Tag>}>
        <DocItemsEditor mode="quotation" products={products} items={items} onChange={setItems} />
      </Card>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row align="middle">
          <Col span={4}><Statistic title="明细行" value={validItems.length} /></Col>
          <Col span={5}><Statistic title={`总额 (${header.currency})`} value={total} precision={2} /></Col>
          <Col span={15} style={{ textAlign: 'right' }}>
            <Space>
              <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
              <Button type="primary" size="large" loading={submitting} onClick={onSubmit}>提交报价单</Button>
            </Space>
          </Col>
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>汇率按报价日期当月固定汇率自动带出，总额/折CNY由后端重算为准。</Text>
      </Card>
    </div>
  )
}
