// 合同录入页 (F2.6) — 支持"从报价转入"预填 + M3b 标签需求提示
// 转入: 选报价单 → 头(条款/币种)和明细(单价=报价单价)自动带出, 可改
// M3b: 合同落库成功后自动算标签纸需求, 缺料 WARN 不阻止 (领用出库才扣库存)
import { useEffect, useState } from 'react'
import {
  Alert, App, AutoComplete, Button, Card, Col, DatePicker, Input, Modal, Row, Select, Space,
  Statistic, Tag, Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api, type Customer } from '@/api/client'
import DocItemsEditor, { newItem, itemCalc, type DocItem, type ProductOption } from '@/components/DocItemsEditor'

const { Text, Title } = Typography

interface LabelDemand {
  found: boolean
  all_sufficient: boolean | null
  lines: { aux_code: string; name: string; required: number; in_stock: number; shortage: number; profile_missing: boolean }[]
}

export default function ContractEntry() {
  const { message } = App.useApp()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [products, setProducts] = useState<ProductOption[]>([])
  const [quotes, setQuotes] = useState<Record<string, unknown>[]>([])
  const [sourceQuote, setSourceQuote] = useState<string | null>(null)
  const [header, setHeader] = useState({
    contract_no: '', customer_code: null as string | null,
    sign_date: dayjs(), delivery_deadline: null as dayjs.Dayjs | null,
    currency: 'USD', trade_terms: 'FOB', port_loading: '', port_discharge: '',
    payment_term: '', packing: '', remark: '',
  })
  const [paymentTermOpts, setPaymentTermOpts] = useState<string[]>([])
  const [packingOpts, setPackingOpts] = useState<string[]>([])
  const [items, setItems] = useState<DocItem[]>([newItem(1)])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [demand, setDemand] = useState<(LabelDemand & { contract_no: string }) | null>(null)

  useEffect(() => {
    api.customers().then(setCustomers).catch((e) => message.error(`客户加载失败: ${e.message}`))
    api.docHeaderTerms('payment_term').then(setPaymentTermOpts).catch(() => {})
    api.docHeaderTerms('packing').then(setPackingOpts).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const suggestNo = () => {
    api.suggestDocNo('contract').then((r) => setHeader((h) => ({ ...h, contract_no: r.doc_no }))).catch(() => {})
  }

  const onCustomer = (code: string) => {
    setHeader((h) => ({ ...h, customer_code: code }))
    setSourceQuote(null)
    api.productsPicker(code).then((list) => setProducts(list as unknown as ProductOption[])).catch(() => setProducts([]))
    api.quotationsList(code).then(setQuotes).catch(() => setQuotes([]))
    if (!header.contract_no) suggestNo()
  }

  // 从报价转入: 头条款+明细单价带出, 可再改
  const onPickQuote = async (quoteNo: string) => {
    setSourceQuote(quoteNo)
    try {
      const d = await api.docQuotation(quoteNo)
      if (!d.found || !d.header) return message.warning(`报价 ${quoteNo} 不存在`)
      const h = d.header
      setHeader((prev) => ({
        ...prev,
        currency: String(h.currency || prev.currency),
        trade_terms: String(h.trade_terms || prev.trade_terms),
        port_loading: String(h.port_loading || ''), port_discharge: String(h.port_discharge || ''),
        payment_term: String(h.payment_term || ''), packing: String(h.packing || ''),
        // 报价上有交货时长(天)时, 自动预填交期=签订日期+天数, 可再改
        delivery_deadline: h.delivery_days ? prev.sign_date.add(Number(h.delivery_days), 'day') : prev.delivery_deadline,
      }))
      setItems(d.items.map((it, i) => ({
        key: i + 1,
        item_no: String(it.item_no || String(i + 1).padStart(3, '0')),
        material_id: String(it.material_id),
        spec: String(it.spec || ''),
        weight_per_unit: it.weight_per_unit != null ? Number(it.weight_per_unit) : null,
        price_coefficient: null,
        unit_price: it.unit_price != null ? Number(it.unit_price) : null,
        quantity: it.quantity != null ? Number(it.quantity) : null,
        remark: String(it.remark || ''),
      })))
      message.success(`已从报价 ${quoteNo} 带入 ${d.items.length} 行明细（单价=报价单价，可改）`)
    } catch (e) {
      message.error(`报价读取失败: ${(e as Error).message}`)
    }
  }

  const set = (k: string, v: unknown) => setHeader((h) => ({ ...h, [k]: v }))
  const total = items.reduce((s, it) => s + itemCalc('contract', it).subtotal, 0)
  const validItems = items.filter((it) => it.material_id && it.quantity && it.unit_price)

  const onSubmit = async () => {
    if (!header.customer_code) return message.warning('请选择客户')
    if (!header.contract_no.trim()) return message.warning('请填合同号')
    if (validItems.length === 0) return message.warning('至少一行完整明细（物料+单价+数量）')
    setSubmitting(true)
    try {
      const r = await api.createDoc('contract', {
        contract_no: header.contract_no.trim(),
        customer_code: header.customer_code,
        sign_date: header.sign_date.format('YYYY-MM-DD'),
        delivery_deadline: header.delivery_deadline?.format('YYYY-MM-DD') || null,
        currency: header.currency, trade_terms: header.trade_terms,
        port_loading: header.port_loading, port_discharge: header.port_discharge,
        payment_term: header.payment_term, packing: header.packing,
        source_quote_no: sourceQuote, remark: header.remark,
      }, validItems.map((it) => ({
        item_no: it.item_no, material_id: it.material_id,
        unit_price: it.unit_price, quantity: it.quantity, remark: it.remark,
      })), operator || 'frontend-react')
      if (r.ok && r.doc_no) {
        message.success(`✅ 合同 ${r.doc_no} 已入库，总额 ${r.total_amount} ${header.currency}${sourceQuote ? `（报价 ${sourceQuote} 已标记转合同）` : ''}`)
        // M3b: 标签纸需求提示 —— 缺料 WARN 不阻止
        try {
          const d = await api.auxLabelDemand(r.doc_no)
          if (d.lines.length > 0) setDemand({ ...d, contract_no: r.doc_no } as LabelDemand & { contract_no: string })
        } catch { /* 提示失败不影响合同 */ }
        setItems([newItem(1)])
        setSourceQuote(null)
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
      <Title level={4}>📄 合同录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>可从报价转入 ｜ 落库后自动提示标签纸需求</Text></Title>

      <Card size="small" title="合同头" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}><Text type="secondary">客户 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择客户" value={header.customer_code} onChange={onCustomer}
              options={customers.map((c) => ({ value: c.code, label: `${c.code} - ${c.name}` }))} /></Col>
          <Col span={6}><Text type="secondary">合同号 *（按日期自动建议）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={header.contract_no} onChange={(e) => set('contract_no', e.target.value)} placeholder="SC+日期+流水" />
              <Button icon={<ReloadOutlined />} onClick={suggestNo} title="重新建议" />
            </Space.Compact></Col>
          <Col span={6}><Text type="secondary">从报价转入（可选，带入条款和单价）</Text>
            <Select
              style={{ width: '100%' }} allowClear placeholder={header.customer_code ? '选择报价单' : '先选客户'}
              value={sourceQuote} onChange={(v) => v && onPickQuote(v)}
              options={quotes.map((q) => ({
                value: String(q.quote_no),
                label: `${q.quote_no} · ${q.total_amount} ${q.currency}${q.status === 'converted' ? '（已转）' : ''}`,
                disabled: q.status === 'converted',
              }))}
            /></Col>
          <Col span={3}><Text type="secondary">签订日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={header.sign_date} onChange={(v) => v && set('sign_date', v)} /></Col>
          <Col span={3}><Text type="secondary">币种</Text>
            <Select style={{ width: '100%' }} value={header.currency} onChange={(v) => set('currency', v)}
              options={['USD', 'EUR', 'IDR', 'CNY'].map((c) => ({ value: c }))} /></Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 12 }}>
          <Col span={3}><Text type="secondary">贸易术语</Text>
            <Select style={{ width: '100%' }} value={header.trade_terms} onChange={(v) => set('trade_terms', v)}
              options={['FOB', 'CIF', 'CFR', 'EXW'].map((t) => ({ value: t }))} /></Col>
          <Col span={3}><Text type="secondary">装运港</Text>
            <Input value={header.port_loading} onChange={(e) => set('port_loading', e.target.value)} /></Col>
          <Col span={3}><Text type="secondary">卸货港</Text>
            <Input value={header.port_discharge} onChange={(e) => set('port_discharge', e.target.value)} /></Col>
          <Col span={4}><Text type="secondary">交货截止</Text>
            <DatePicker style={{ width: '100%' }} value={header.delivery_deadline} onChange={(v) => set('delivery_deadline', v)} /></Col>
          <Col span={6}><Text type="secondary">付款条件（可选手填）</Text>
            <AutoComplete style={{ width: '100%' }} value={header.payment_term}
              onChange={(v) => set('payment_term', v)}
              options={paymentTermOpts.map((t) => ({ value: t }))} /></Col>
          <Col span={5}><Text type="secondary">包装条款（可选手填）</Text>
            <AutoComplete style={{ width: '100%' }} value={header.packing}
              onChange={(v) => set('packing', v)}
              options={packingOpts.map((t) => ({ value: t }))} /></Col>
        </Row>
      </Card>

      <Card size="small" title="合同明细" style={{ marginBottom: 16 }}
        extra={sourceQuote ? <Tag color="green">已从 {sourceQuote} 转入，单价可改</Tag> : <Tag>手工录入或先从报价转入</Tag>}>
        <DocItemsEditor mode="contract" products={products} items={items} onChange={setItems} />
      </Card>

      {demand && (
        <Alert
          style={{ marginBottom: 16 }}
          type={demand.all_sufficient ? 'success' : 'warning'}
          message={`合同 ${demand.contract_no} 标签纸需求（只提示不扣库存，生产领用时才扣）`}
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {demand.lines.map((l) => (
                <li key={l.aux_code}>
                  {l.aux_code}（{l.name}）：需 <b>{l.required}</b> 张 / 库存 {l.in_stock} 张
                  {l.shortage > 0 && <Text type="danger"> → 缺 {l.shortage} 张，请提前采购</Text>}
                </li>
              ))}
            </ul>
          }
          closable onClose={() => setDemand(null)}
        />
      )}

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row align="middle">
          <Col span={4}><Statistic title="明细行" value={validItems.length} /></Col>
          <Col span={5}><Statistic title={`总额 (${header.currency})`} value={total} precision={2} /></Col>
          <Col span={15} style={{ textAlign: 'right' }}>
            <Space>
              <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
              <Button type="primary" size="large" loading={submitting} onClick={onSubmit}>提交合同</Button>
            </Space>
          </Col>
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>汇率按签订日当月固定汇率自动带出；物料换了规格请先"克隆建物料"再录入。</Text>
      </Card>
    </div>
  )
}
