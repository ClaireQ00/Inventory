// 出库单录入页 (2026-08-02) — 销售/生产领用/报废出库
// 销售出库必须关联发货单; 负库存按项目约定不拦截(先做后补)但显著提示
import { useEffect, useState } from 'react'
import {
  App, Button, Card, Col, DatePicker, Input, Modal, Row, Select, Space, Statistic, Typography,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { api } from '@/api/client'
import StockItemsEditor, { newStockItem, type StockItem } from '@/components/StockItemsEditor'
import type { ProductOption } from '@/components/DocItemsEditor'

const { Text, Title } = Typography

export default function StockOutEntry() {
  const { message } = App.useApp()
  const [products, setProducts] = useState<ProductOption[]>([])
  const [warehouses, setWarehouses] = useState<{ code: string; name: string }[]>([])
  const [deliveries, setDeliveries] = useState<Record<string, unknown>[]>([])
  const [header, setHeader] = useState({
    out_no: '', out_type: 'sale', warehouse_code: null as string | null,
    delivery_no: null as string | null, out_date: dayjs(), remark: '',
  })
  const [items, setItems] = useState<StockItem[]>([newStockItem(1)])
  const [operator, setOperator] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.productsPicker().then((l) => setProducts(l as unknown as ProductOption[])).catch((e) => message.error(`物料加载失败: ${e.message}`))
    api.warehouses().then(setWarehouses).catch(() => {})
    api.deliveries().then(setDeliveries).catch(() => {})
    suggestNo()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const suggestNo = () => {
    api.suggestDocNo('stock_out').then((r) => setHeader((h) => ({ ...h, out_no: r.doc_no }))).catch(() => {})
  }
  const set = (k: string, v: unknown) => setHeader((h) => ({ ...h, [k]: v }))
  const validItems = items.filter((it) => it.material_id && it.quantity)

  const onSubmit = async () => {
    if (!header.out_no.trim()) return message.warning('请填出库单号')
    if (!header.warehouse_code) return message.warning('请选择仓库')
    if (header.out_type === 'sale' && !header.delivery_no) return message.warning('销售出库必须选择发货单')
    if (validItems.length === 0) return message.warning('至少一行完整明细（物料+数量）')
    setSubmitting(true)
    try {
      const r = await api.createDoc('stock-out', {
        out_no: header.out_no.trim(), out_type: header.out_type,
        warehouse_code: header.warehouse_code, delivery_no: header.delivery_no || '',
        out_date: header.out_date.format('YYYY-MM-DD'), remark: header.remark,
      }, validItems.map((it) => ({
        material_id: it.material_id, quantity: it.quantity, remark: it.remark,
      })), operator || 'frontend-react')
      if (r.ok) {
        const warns = r.warnings || []
        Modal[warns.length ? 'warning' : 'success']({
          title: `出库单 ${r.doc_no} 已出库（库存已扣减）`,
          content: warns.length ? `⚠️ 负库存提示（允许先做后补，请尽快补入库）：\n${warns.join('\n')}` : '库存结果表与流水已同步更新。',
        })
        setItems([newStockItem(1)])
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
    <div style={{ maxWidth: 980, margin: '0 auto' }}>
      <Title level={4}>📤 出库单录入 <Text type="secondary" style={{ fontSize: 14, fontWeight: 'normal' }}>销售/生产领用/报废 ｜ 落库即扣库存</Text></Title>

      <Card size="small" title="出库头" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}><Text type="secondary">出库单号 *（自动建议）</Text>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={header.out_no} onChange={(e) => set('out_no', e.target.value)} placeholder="OUT+日期+流水" />
              <Button icon={<ReloadOutlined />} onClick={suggestNo} title="重新建议" />
            </Space.Compact></Col>
          <Col span={5}><Text type="secondary">出库类型 *</Text>
            <Select style={{ width: '100%' }} value={header.out_type}
              onChange={(v) => { set('out_type', v); if (v !== 'sale') set('delivery_no', null) }}
              options={[
                { value: 'sale', label: '销售出库' },
                { value: 'production', label: '生产领用' },
                { value: 'scrap', label: '报废出库' },
              ]} /></Col>
          <Col span={5}><Text type="secondary">仓库 *</Text>
            <Select style={{ width: '100%' }} placeholder="选择仓库" value={header.warehouse_code}
              onChange={(v) => set('warehouse_code', v)}
              options={warehouses.map((w) => ({ value: w.code, label: `${w.code} - ${w.name}` }))} /></Col>
          <Col span={4}><Text type="secondary">出库日期 *</Text>
            <DatePicker style={{ width: '100%' }} value={header.out_date} onChange={(v) => v && set('out_date', v)} /></Col>
          <Col span={4}><Text type="secondary">备注</Text>
            <Input value={header.remark} onChange={(e) => set('remark', e.target.value)} /></Col>
        </Row>
        {header.out_type === 'sale' && (
          <Row gutter={16} style={{ marginTop: 12 }}>
            <Col span={8}><Text type="secondary">关联发货单 *</Text>
              <Select style={{ width: '100%' }} placeholder="选择发货单" value={header.delivery_no}
                onChange={(v) => set('delivery_no', v)}
                options={deliveries.map((d) => ({
                  value: d.delivery_no as string,
                  label: `${d.delivery_no} - ${d.customer_code}（${String(d.delivery_date).slice(0, 10)}）`,
                }))} /></Col>
          </Row>
        )}
      </Card>

      <Card size="small" title="出库明细" style={{ marginBottom: 16 }}>
        <StockItemsEditor products={products} items={items} onChange={setItems} />
      </Card>

      <Card size="small" style={{ marginBottom: 24 }}>
        <Row align="middle">
          <Col span={4}><Statistic title="明细行" value={validItems.length} /></Col>
          <Col span={5}><Statistic title="总数量(卷)" value={validItems.reduce((s, it) => s + (it.quantity || 0), 0)} /></Col>
          <Col span={15} style={{ textAlign: 'right' }}>
            <Space>
              <Input placeholder="操作人" style={{ width: 160 }} value={operator} onChange={(e) => setOperator(e.target.value)} />
              <Button type="primary" size="large" loading={submitting} onClick={onSubmit}>提交出库单</Button>
            </Space>
          </Col>
        </Row>
        <Text type="secondary" style={{ fontSize: 12 }}>提交即确认（confirmed）：库存结果表 + 出入库流水同步更新；出库超库存不拦截（先做后补约定），但会显著提示负库存。</Text>
      </Card>
    </div>
  )
}
